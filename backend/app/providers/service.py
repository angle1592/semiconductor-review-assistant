from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.providers.anthropic import AnthropicAdapter
from app.providers.contracts import ProviderAdapter
from app.providers.credentials import SecretStore, credential_key
from app.providers.endpoints import resolve_endpoints
from app.providers.errors import ProviderError
from app.providers.models import AIProviderProfile, ModelProfile
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.providers.probes import probe_model, required_probes_passed, reset_probe_states
from app.providers.schemas import (
    ModelProfileCreate,
    ModelProfileRead,
    ProviderProfileCreate,
    ProviderProfileRead,
    ProviderProfileUpdate,
)
from app.shared.errors import NotFoundError


AdapterFactory = Callable[[AIProviderProfile, str], ProviderAdapter]


def default_adapter_factory(profile: AIProviderProfile, api_key: str) -> ProviderAdapter:
    endpoints = resolve_endpoints(profile.protocol, profile.base_url)
    if profile.protocol == "anthropic":
        return AnthropicAdapter(endpoints, api_key)
    return OpenAICompatibleAdapter(endpoints, api_key)


class ProviderProfileService:
    def __init__(self, engine, secrets: SecretStore, adapter_factory: AdapterFactory = default_adapter_factory):
        self.engine = engine
        self.secrets = secrets
        self.adapter_factory = adapter_factory

    def _read(self, profile: AIProviderProfile) -> ProviderProfileRead:
        return ProviderProfileRead(**profile.model_dump(), api_key_configured=self.secrets.get(credential_key(profile.id)) is not None)

    def _model_read(self, model: ModelProfile) -> ModelProfileRead:
        return ModelProfileRead(**model.model_dump())

    def _get(self, session: Session, profile_id: str) -> AIProviderProfile:
        profile = session.get(AIProviderProfile, profile_id)
        if profile is None:
            raise NotFoundError("provider", profile_id)
        return profile

    def _get_model(self, session: Session, profile_id: str, model_profile_id: str) -> ModelProfile:
        model = session.get(ModelProfile, model_profile_id)
        if model is None or model.provider_id != profile_id:
            raise NotFoundError("model", model_profile_id)
        return model

    def _adapter(self, profile: AIProviderProfile) -> ProviderAdapter:
        api_key = self.secrets.get(credential_key(profile.id))
        if not api_key:
            raise ProviderError(code="upstream_auth_failed", message="请先填写 API Key。", status_code=422)
        return self.adapter_factory(profile, api_key)

    def create(self, payload: ProviderProfileCreate) -> ProviderProfileRead:
        endpoints = resolve_endpoints(payload.protocol, payload.base_url)
        profile = AIProviderProfile(name=payload.name.strip(), protocol=payload.protocol, base_url=endpoints.base_url)
        with Session(self.engine) as session:
            session.add(profile)
            session.commit()
            session.refresh(profile)
        if payload.api_key:
            self.secrets.set(credential_key(profile.id), payload.api_key)
        return self._read(profile)

    def list(self) -> list[ProviderProfileRead]:
        with Session(self.engine) as session:
            profiles = session.exec(select(AIProviderProfile).order_by(AIProviderProfile.created_at)).all()
            return [self._read(profile) for profile in profiles]

    def get(self, profile_id: str) -> ProviderProfileRead:
        with Session(self.engine) as session:
            return self._read(self._get(session, profile_id))

    def update(self, profile_id: str, payload: ProviderProfileUpdate) -> ProviderProfileRead:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            changed_endpoint = payload.base_url is not None or payload.protocol is not None
            if payload.name is not None:
                profile.name = payload.name.strip()
            if payload.protocol is not None:
                profile.protocol = payload.protocol
            if payload.base_url is not None or payload.protocol is not None:
                profile.base_url = resolve_endpoints(profile.protocol, payload.base_url or profile.base_url).base_url
            if payload.api_key:
                self.secrets.set(credential_key(profile.id), payload.api_key)
                changed_endpoint = True
            if changed_endpoint:
                profile.credential_generation += 1
                profile.enabled = False
                profile.models_fetched_at = None
                for model in session.exec(select(ModelProfile).where(ModelProfile.provider_id == profile.id)):
                    reset_probe_states(model)
                    session.add(model)
            profile.updated_at = datetime.now(UTC)
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return self._read(profile)

    def replace_key(self, profile_id: str, value: str) -> ProviderProfileRead:
        return self.update(profile_id, ProviderProfileUpdate(api_key=value))

    def delete(self, profile_id: str) -> None:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            for model in session.exec(select(ModelProfile).where(ModelProfile.provider_id == profile_id)):
                session.delete(model)
            session.delete(profile)
            session.commit()
        self.secrets.delete(credential_key(profile_id))

    def list_models(self, profile_id: str) -> list[ModelProfileRead]:
        with Session(self.engine) as session:
            self._get(session, profile_id)
            models = session.exec(select(ModelProfile).where(ModelProfile.provider_id == profile_id).order_by(ModelProfile.display_name)).all()
            return [self._model_read(model) for model in models]

    def add_model(self, profile_id: str, payload: ModelProfileCreate) -> ModelProfileRead:
        with Session(self.engine) as session:
            self._get(session, profile_id)
            existing = session.exec(select(ModelProfile).where(ModelProfile.provider_id == profile_id, ModelProfile.model_id == payload.model_id)).first()
            if existing:
                return self._model_read(existing)
            model = ModelProfile(provider_id=profile_id, model_id=payload.model_id.strip(), display_name=payload.display_name.strip())
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._model_read(model)

    async def refresh_models(self, profile_id: str, force: bool = False) -> list[ModelProfileRead]:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            fetched_at = profile.models_fetched_at
            if fetched_at and fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)
            if not force and fetched_at and datetime.now(UTC) - fetched_at < timedelta(minutes=15):
                return self.list_models(profile_id)
            remote_models = await self._adapter(profile).list_models()
            for remote in remote_models:
                existing = session.exec(select(ModelProfile).where(ModelProfile.provider_id == profile_id, ModelProfile.model_id == remote.id)).first()
                if existing:
                    existing.display_name = remote.display_name
                    session.add(existing)
                else:
                    session.add(ModelProfile(provider_id=profile_id, model_id=remote.id, display_name=remote.display_name))
            profile.models_fetched_at = datetime.now(UTC)
            session.add(profile)
            session.commit()
        return self.list_models(profile_id)

    async def probe(self, profile_id: str, model_profile_id: str) -> ModelProfileRead:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            model = self._get_model(session, profile_id, model_profile_id)
            await probe_model(self._adapter(profile), profile.protocol, model)
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._model_read(model)

    def enable(self, profile_id: str) -> ProviderProfileRead:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            models = session.exec(select(ModelProfile).where(ModelProfile.provider_id == profile_id)).all()
            if not any(required_probes_passed(model) for model in models):
                raise ProviderError(code="provider_not_validated", message="请先选择模型并完成三项能力校验。", status_code=409)
            profile.enabled = True
            if not session.exec(select(AIProviderProfile).where(AIProviderProfile.is_default == True)).first():  # noqa: E712
                profile.is_default = True
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return self._read(profile)

    def disable(self, profile_id: str) -> ProviderProfileRead:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            profile.enabled = False
            profile.is_default = False
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return self._read(profile)

    def set_default(self, profile_id: str) -> ProviderProfileRead:
        with Session(self.engine) as session:
            selected = self._get(session, profile_id)
            if not selected.enabled:
                raise ProviderError(code="provider_not_enabled", message="请先校验并启用此服务。", status_code=409)
            for profile in session.exec(select(AIProviderProfile)):
                profile.is_default = profile.id == profile_id
                session.add(profile)
            session.commit()
            session.refresh(selected)
            return self._read(selected)

    def setup_ready(self) -> bool:
        with Session(self.engine) as session:
            return session.exec(select(AIProviderProfile).where(AIProviderProfile.enabled == True, AIProviderProfile.is_default == True)).first() is not None  # noqa: E712

    def diagnostic_summary(self) -> dict:
        with Session(self.engine) as session:
            profiles = session.exec(select(AIProviderProfile)).all()
            models = session.exec(select(ModelProfile)).all()
        models_by_provider: dict[str, list[dict]] = {}
        for model in models:
            models_by_provider.setdefault(model.provider_id, []).append(
                {
                    "model_id": model.model_id,
                    "text_status": model.text_status,
                    "structured_status": model.structured_status,
                    "vision_status": model.vision_status,
                    "prompt_cache_status": model.prompt_cache_status,
                    "safe_error_code": model.safe_error_code,
                }
            )
        return {
            "providers": [
                {
                    "protocol": profile.protocol,
                    "host": urlsplit(profile.base_url).hostname,
                    "enabled": profile.enabled,
                    "is_default": profile.is_default,
                    "models": models_by_provider.get(profile.id, []),
                }
                for profile in profiles
            ]
        }

    def diagnostic_secret_values(self) -> tuple[str, ...]:
        with Session(self.engine) as session:
            profile_ids = session.exec(select(AIProviderProfile.id)).all()
        return tuple(
            value
            for profile_id in profile_ids
            if (value := self.secrets.get(credential_key(profile_id)))
        )
