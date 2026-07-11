from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class LearningSource:
    kind: str
    source_id: str
    source_ref: str
    title: str
    text: str
    image_path: str | None = None
    page_number: int | None = None


@dataclass(frozen=True)
class LearningGenerationRequest:
    lesson_id: str
    title: str
    notes: str
    target_minutes: int
    sources: tuple[LearningSource, ...]
    max_items: int = 8


class LearningProvider(Protocol):
    def capabilities(self) -> Any: ...

    def generate_learning_items(
        self, request: LearningGenerationRequest
    ) -> Sequence[Any]: ...


class ProviderFactory(Protocol):
    def __call__(self) -> LearningProvider: ...
