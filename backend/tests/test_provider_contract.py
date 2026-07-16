from typing import runtime_checkable

from app.providers.contracts import ProviderAdapter
from app.providers.anthropic import AnthropicAdapter
from app.providers.endpoints import resolve_endpoints
from app.providers.openai_compatible import OpenAICompatibleAdapter


def test_production_adapters_implement_common_contract():
    adapters = [
        OpenAICompatibleAdapter(resolve_endpoints("openai_compatible", "https://x.test"), "secret"),
        AnthropicAdapter(resolve_endpoints("anthropic", "https://x.test"), "secret"),
    ]
    assert runtime_checkable(ProviderAdapter)
    for adapter in adapters:
        assert isinstance(adapter, ProviderAdapter)
