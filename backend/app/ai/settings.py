from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel

from app.ai.codex import CodexProvider
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.ai.provider import AIProvider
from app.ai.schemas import ConnectionTestResult
from app.ai.secrets import SecretStore

API_KEY_SECRET = "openai_compatible_api_key"


class AISettingsRecord(SQLModel, table=True):
    __tablename__ = "ai_settings"

    id: int = SQLField(default=1, primary_key=True)
    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    vision_enabled: bool = True


class AISettingsInput(BaseModel):
    provider: Literal["openai_compatible", "codex"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    vision_enabled: bool = True
    api_key: str | None = Field(default=None, exclude=True)
    clear_api_key: bool = False


class AISettingsResponse(BaseModel):
    provider: Literal["openai_compatible", "codex"]
    base_url: str
    model: str
    api_key_configured: bool
    vision_enabled: bool


ProviderFactory = Callable[[AISettingsInput, str | None, Path], AIProvider]


def default_provider_factory(
    settings: AISettingsInput, api_key: str | None, data_dir: Path
) -> AIProvider:
    if settings.provider == "codex":
        return CodexProvider(
            model=settings.model,
            data_dir=data_dir,
            vision_enabled=settings.vision_enabled,
        )
    return OpenAICompatibleProvider(
        base_url=settings.base_url,
        api_key=api_key,
        model=settings.model,
        vision_enabled=settings.vision_enabled,
    )


class AISettingsService:
    def __init__(
        self,
        engine,
        data_dir: Path,
        secret_store: SecretStore,
        provider_factory: ProviderFactory = default_provider_factory,
    ):
        self.engine = engine
        self.data_dir = data_dir
        self.secret_store = secret_store
        self.provider_factory = provider_factory

    def _record(self) -> AISettingsRecord:
        with Session(self.engine) as session:
            record = session.get(AISettingsRecord, 1)
            if record is None:
                record = AISettingsRecord()
                session.add(record)
                session.commit()
                session.refresh(record)
            return record

    def get(self) -> AISettingsResponse:
        record = self._record()
        return AISettingsResponse(
            provider=record.provider,
            base_url=record.base_url,
            model=record.model,
            vision_enabled=record.vision_enabled,
            api_key_configured=self.secret_store.get(API_KEY_SECRET) is not None,
        )

    def save(self, settings: AISettingsInput) -> AISettingsResponse:
        with Session(self.engine) as session:
            record = session.get(AISettingsRecord, 1) or AISettingsRecord()
            record.provider = settings.provider
            record.base_url = settings.base_url.rstrip("/")
            record.model = settings.model
            record.vision_enabled = settings.vision_enabled
            session.add(record)
            session.commit()
        if settings.clear_api_key:
            self.secret_store.delete(API_KEY_SECRET)
        elif settings.api_key:
            self.secret_store.set(API_KEY_SECRET, settings.api_key)
        return self.get()

    async def test(self, settings: AISettingsInput) -> ConnectionTestResult:
        api_key = settings.api_key or self.secret_store.get(API_KEY_SECRET)
        if settings.provider == "codex":
            api_key = None
        provider = self.provider_factory(settings, api_key, self.data_dir)
        return await provider.test_connection()

    def create_provider(self) -> AIProvider:
        record = self._record()
        settings = AISettingsInput(
            provider=record.provider,
            base_url=record.base_url,
            model=record.model,
            vision_enabled=record.vision_enabled,
        )
        api_key = None
        if settings.provider == "openai_compatible":
            api_key = self.secret_store.get(API_KEY_SECRET)
        return self.provider_factory(settings, api_key, self.data_dir)
