from pathlib import Path

import pytest

from app.ai.schemas import (
    AnswerAssessment,
    GeneratedLearningItem,
    GeneratedLearningItems,
    ProviderCapabilities,
)
from app.learning.ai_adapter import LearningAIAdapter
from app.learning.provider import LearningGenerationRequest, LearningSource


class FakeAIProvider:
    def __init__(self):
        self.generation_request = None

    def capabilities(self):
        return ProviderCapabilities(text=True, vision=True, structured_output=True)

    async def generate_learning_items(self, request):
        self.generation_request = request
        return GeneratedLearningItems(
            items=[
                GeneratedLearningItem(
                    topic="刻蚀",
                    question="刻蚀选择比表示什么？",
                    reference_answer="目标材料与掩膜材料刻蚀速率之比。",
                    explanation="用于衡量掩膜保护能力。",
                    source_refs=[request.pages[0].source_ref],
                )
            ]
        )

    async def assess_answer(self, request):
        return AnswerAssessment(verdict="partial", missing_points=["速率之比"], feedback="还差定义。")


@pytest.mark.asyncio
async def test_learning_adapter_maps_selected_sources_and_assessment(tmp_path: Path):
    provider = FakeAIProvider()
    adapter = LearningAIAdapter(provider)
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    request = LearningGenerationRequest(
        lesson_id="lesson",
        title="刻蚀课",
        notes="老师强调：选择比",
        target_minutes=10,
        sources=(
            LearningSource("page", "p1", "page:p1", "课件", "正文", str(image), 3),
            LearningSource("notebook", "n1", "notebook:n1", "指南", "补充原文"),
        ),
    )

    generated = await adapter.generate_learning_items(request)
    assessment = await adapter.assess("问题", "参考", "我的回答", ["page:p1"])

    assert len(generated.items) == 1
    assert provider.generation_request.pages[0].page_number == 3
    assert provider.generation_request.notebook_text == "来源 notebook:n1（指南）\n补充原文"
    assert assessment.verdict == "partial"
