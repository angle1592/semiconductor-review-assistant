from pathlib import Path

from app.ai.provider import AIProvider
from app.ai.schemas import (
    AnswerAssessment,
    AnswerAssessmentRequest,
    LearningGenerationRequest as AILearningGenerationRequest,
    LearningSourcePage,
)
from app.learning.provider import LearningGenerationRequest


class LearningAIAdapter:
    """Translate the learning domain request into the selected AI provider contract."""

    def __init__(self, provider: AIProvider):
        self.provider = provider

    def capabilities(self):
        return self.provider.capabilities()

    async def generate_learning_items(self, request: LearningGenerationRequest):
        pages = [
            LearningSourcePage(
                source_ref=source.source_ref,
                page_number=source.page_number or 1,
                extracted_text=source.text,
                image_path=Path(source.image_path) if source.image_path else None,
            )
            for source in request.sources
            if source.kind == "page"
        ]
        notebook_text = "\n\n".join(
            f"来源 {source.source_ref}（{source.title}）\n{source.text}"
            for source in request.sources
            if source.kind == "notebook"
        )
        return await self.provider.generate_learning_items(
            AILearningGenerationRequest(
                pages=pages,
                teacher_emphasis=request.notes,
                notebook_text=notebook_text,
                item_count=min(8, request.max_items),
            )
        )

    async def assess(
        self,
        question: str,
        reference_answer: str,
        user_answer: str,
        source_refs: list[str],
    ) -> AnswerAssessment:
        return await self.provider.assess_answer(
            AnswerAssessmentRequest(
                question=question,
                reference_answer=reference_answer,
                user_answer=user_answer,
                source_refs=source_refs,
            )
        )
