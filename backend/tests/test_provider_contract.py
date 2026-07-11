from app.ai.schemas import (
    AnswerAssessment,
    GeneratedLearningItem,
    ProviderCapabilities,
    LearningGenerationRequest,
)


def test_provider_schemas_reject_missing_source_reference():
    try:
        GeneratedLearningItem(
            topic="光刻",
            question="光刻的主要目的是什么？",
            reference_answer="把掩膜图形转移到光刻胶。",
            explanation="用于后续选择性加工。",
            source_refs=[],
        )
    except ValueError:
        return
    raise AssertionError("source_refs must not be empty")


def test_provider_contract_has_explicit_capabilities_and_verdict():
    capabilities = ProviderCapabilities(text=True, vision=False, structured_output=True)
    assessment = AnswerAssessment(
        verdict="partial",
        missing_points=["未说明图形转移"],
        feedback="方向正确，但还缺少图形转移的对象。",
    )

    assert capabilities.vision is False
    assert assessment.verdict == "partial"


def test_generation_request_accepts_notebook_text_without_pages():
    request = LearningGenerationRequest(pages=[], notebook_text="NotebookLM 学习指南")

    assert request.notebook_text.startswith("NotebookLM")
