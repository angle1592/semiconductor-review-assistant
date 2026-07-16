from pathlib import Path

from app.analysis.cache import AIResultCache, analysis_cache_key
from app.analysis.schemas import AnalysisBatchResult, KeyPointCandidate
from app.analysis.service import clear_analysis_caches


BASE_KEY = {
    "protocol": "anthropic",
    "provider_config_generation": 3,
    "model": "review-model",
    "content_hash": "content-a",
    "prompt_hash": "prompt-a",
    "schema_version": "candidate-v1",
    "pipeline_version": "analysis-v1",
    "parameters": {"temperature": 0, "max_tokens": 2048},
}


def sample_result() -> AnalysisBatchResult:
    return AnalysisBatchResult(
        candidates=[
            KeyPointCandidate(
                title="带隙定义",
                explanation="价带顶与导带底之间的能量差。",
                importance="core",
                source_block_ids=["block-a"],
                evidence_quotes=["带隙是价带顶与导带底的能量差"],
                rationale="基础定义",
            )
        ],
        source_questions=[],
    )


def test_exact_cache_key_is_canonical_and_every_semantic_change_misses():
    first = analysis_cache_key(**BASE_KEY)
    reordered = analysis_cache_key(
        **{**BASE_KEY, "parameters": {"max_tokens": 2048, "temperature": 0}}
    )
    assert first == reordered

    variations = [
        {"prompt_hash": "prompt-b"},
        {"model": "other-model"},
        {"provider_config_generation": 4},
        {"schema_version": "candidate-v2"},
        {"pipeline_version": "analysis-v2"},
        {"content_hash": "selected-other-blocks"},
        {"parameters": {"temperature": 0.2, "max_tokens": 2048}},
    ]
    assert all(analysis_cache_key(**{**BASE_KEY, **change}) != first for change in variations)


def test_only_successful_results_are_cached_and_survive_restart(tmp_path: Path):
    root = tmp_path / "Runtime" / "ai-cache"
    key = analysis_cache_key(**BASE_KEY)
    cache = AIResultCache(root)

    for status in ("failed", "partial", "cancelled"):
        assert (
            cache.store(key, sample_result(), status=status, metadata={"model": "review-model"})
            is False
        )
        assert cache.load(key) is None

    assert cache.store(
        key,
        sample_result(),
        status="succeeded",
        metadata={
            "protocol": "anthropic",
            "model": "review-model",
            "prompt_hash": "must-not-be-indexed",
        },
    )
    restarted = AIResultCache(root)
    loaded = restarted.load(key)
    assert loaded == sample_result()
    assert (root / key[:2] / f"{key}.json").is_file()

    diagnostic = (root / "index" / f"{key}.json").read_text(encoding="utf-8")
    assert "review-model" in diagnostic
    assert "prompt_hash" not in diagnostic
    assert "带隙" not in diagnostic


def test_cache_clear_removes_only_parse_and_ai_cache(tmp_path: Path):
    runtime = tmp_path / "Runtime"
    (runtime / "parse-cache" / "entry").mkdir(parents=True)
    (runtime / "parse-cache" / "entry" / "manifest.json").write_text("{}")
    (runtime / "ai-cache" / "entry").mkdir(parents=True)
    (runtime / "ai-cache" / "entry" / "result.json").write_text("{}")
    (runtime / "deletion-trash").mkdir(parents=True)
    keep = runtime / "deletion-trash" / "keep.txt"
    keep.write_text("keep")

    clear_analysis_caches(runtime)

    assert (runtime / "parse-cache").is_dir()
    assert list((runtime / "parse-cache").iterdir()) == []
    assert (runtime / "ai-cache").is_dir()
    assert list((runtime / "ai-cache").iterdir()) == []
    assert keep.read_text() == "keep"
