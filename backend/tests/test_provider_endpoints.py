import pytest

from app.providers.endpoints import resolve_endpoints


@pytest.mark.parametrize(
    ("protocol", "entered", "models", "inference"),
    [
        ("openai_compatible", "https://host.test", "https://host.test/v1/models", "https://host.test/v1/chat/completions"),
        ("openai_compatible", "https://host.test/v1/", "https://host.test/v1/models", "https://host.test/v1/chat/completions"),
        ("anthropic", "https://host.test", "https://host.test/v1/models", "https://host.test/v1/messages"),
        ("anthropic", "https://host.test/v1", "https://host.test/v1/models", "https://host.test/v1/messages"),
    ],
)
def test_resolved_endpoints(protocol, entered, models, inference):
    resolved = resolve_endpoints(protocol, entered)
    assert resolved.models_url == models
    assert resolved.inference_url == inference


@pytest.mark.parametrize("entered", ["ftp://host.test", "https://user:pass@host.test", "https://host.test?v=1", "https://host.test/#x", "https:///v1"])
def test_rejects_unsafe_or_ambiguous_base_url(entered):
    with pytest.raises(ValueError):
        resolve_endpoints("openai_compatible", entered)
