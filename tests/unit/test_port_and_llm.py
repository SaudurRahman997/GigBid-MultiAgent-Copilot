"""Marketplace port selection by config, Upwork stub behaviour, LLM role resolution."""

import pytest

from agent.llm import ModelNotConfigured, chat_model, resolve
from agent.marketplace_port import MarketplaceError, MarketplacePort, get_marketplace
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter


def test_config_switch_selects_adapter():
    assert isinstance(get_marketplace({"marketplace": "gigsim"}), GigSimAdapter)
    assert isinstance(get_marketplace({"marketplace": "upwork_live"}), UpworkLiveAdapter)
    with pytest.raises(ValueError):
        get_marketplace({"marketplace": "ebay"})


def test_both_adapters_satisfy_the_port():
    assert isinstance(GigSimAdapter(), MarketplacePort)
    assert isinstance(UpworkLiveAdapter(), MarketplacePort)


@pytest.mark.anyio
async def test_upwork_stub_fails_loudly():
    with pytest.raises(MarketplaceError, match="Phase 10"):
        await UpworkLiveAdapter().search_jobs("u", None, None, None, 5)
    assert await UpworkLiveAdapter().health() is False


@pytest.fixture
def anyio_backend():
    return "asyncio"


CFG = {
    "profile": "open",
    "profiles": {
        "open": {
            "strong": {"provider": "groq", "model": "big"},
            "small": {"provider": "ollama", "model": "qwen3:8b"},
        }
    },
    "nodes": {"writer": "strong"},
}


def test_resolve_uses_config_and_env_override(monkeypatch):
    monkeypatch.delenv("GIGBID_STRONG_PROVIDER", raising=False)
    monkeypatch.delenv("GIGBID_STRONG_MODEL", raising=False)
    assert resolve("strong", CFG) == ("groq", "big")
    monkeypatch.setenv("GIGBID_STRONG_PROVIDER", "ollama")
    monkeypatch.setenv("GIGBID_STRONG_MODEL", "qwen2.5:3b")
    assert resolve("strong", CFG) == ("ollama", "qwen2.5:3b")
    monkeypatch.setenv("GIGBID_STRONG_PROVIDER", "")  # empty .env line must not override
    assert resolve("strong", CFG)[0] == "groq"


def test_groq_without_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GIGBID_STRONG_PROVIDER", raising=False)
    with pytest.raises(ModelNotConfigured, match="GROQ_API_KEY"):
        chat_model("strong", CFG)
