from datetime import UTC, datetime

from sqlmodel import Session

from app.providers.credentials import SecretStore, credential_key
from app.providers.models import AIProviderProfile
from app.providers.schemas import ProviderProfileCreate, ProviderProfileRead
from app.shared.errors import NotFoundError


class ProviderProfileService:
    def __init__(self, engine, secrets: SecretStore):
        self.engine = engine
        self.secrets = secrets

    def _read(self, profile: AIProviderProfile) -> ProviderProfileRead:
        return ProviderProfileRead(
            **profile.model_dump(),
            api_key_configured=self.secrets.get(credential_key(profile.id)) is not None,
        )

    def _get(self, session: Session, profile_id: str) -> AIProviderProfile:
        profile = session.get(AIProviderProfile, profile_id)
        if profile is None:
            raise NotFoundError("provider", profile_id)
        return profile

    def create(self, payload: ProviderProfileCreate) -> ProviderProfileRead:
        profile = AIProviderProfile(
            name=payload.name.strip(),
            protocol=payload.protocol,
            base_url=payload.base_url.rstrip("/"),
        )
        with Session(self.engine) as session:
            session.add(profile)
            session.commit()
            session.refresh(profile)
        if payload.api_key:
            self.secrets.set(credential_key(profile.id), payload.api_key)
        return self._read(profile)

    def replace_key(self, profile_id: str, value: str) -> ProviderProfileRead:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            self.secrets.set(credential_key(profile.id), value)
            profile.credential_generation += 1
            profile.updated_at = datetime.now(UTC)
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return self._read(profile)

    def delete(self, profile_id: str) -> None:
        with Session(self.engine) as session:
            profile = self._get(session, profile_id)
            session.delete(profile)
            session.commit()
        self.secrets.delete(credential_key(profile_id))
