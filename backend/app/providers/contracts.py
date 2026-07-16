from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


T = TypeVar("T")


@dataclass(frozen=True)
class RemoteModel:
    id: str
    display_name: str


@dataclass(frozen=True)
class TextRequest:
    model: str
    prompt: str
    system: str = ""
    images: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredRequest(Generic[T]):
    model: str
    prompt: str
    output_type: type[BaseModel]
    system: str = ""
    images: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    value: T
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    request_id: str | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    async def list_models(self) -> list[RemoteModel]: ...
    async def generate_json(self, request: StructuredRequest[Any]) -> ProviderResult[Any]: ...
    async def generate_text(self, request: TextRequest) -> ProviderResult[str]: ...
