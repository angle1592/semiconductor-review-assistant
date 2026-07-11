from typing import Protocol

from app.ai.schemas import (
    AnswerAssessment,
    AnswerAssessmentRequest,
    ConnectionTestResult,
    GeneratedLearningItems,
    LearningGenerationRequest,
    ProviderCapabilities,
)


class AIProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...

    async def test_connection(self) -> ConnectionTestResult: ...

    async def generate_learning_items(
        self, request: LearningGenerationRequest
    ) -> GeneratedLearningItems: ...

    async def assess_answer(self, request: AnswerAssessmentRequest) -> AnswerAssessment: ...
