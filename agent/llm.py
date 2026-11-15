"""Chat models by ROLE, from agent/config.yaml (never hard-coded in nodes).

    chat_model("strong")            -> profile's strong model (Writer, Critic, Liaison)
    chat_model_for_node("writer")   -> looks up nodes.writer -> role -> model
Env overrides for local runs: GIGBID_<ROLE>_PROVIDER / GIGBID_<ROLE>_MODEL
(e.g. GIGBID_STRONG_PROVIDER=ollama GIGBID_STRONG_MODEL=qwen2.5:3b).
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

from agent.marketplace_port import load_config


class ModelNotConfigured(RuntimeError):
    pass


def resolve(role: str, config: dict | None = None) -> tuple[str, str]:
    cfg = config or load_config()
    prof = cfg["profiles"][cfg["profile"]].get(role)
    if prof is None:
        raise ModelNotConfigured(f"no model role {role!r} in profile {cfg['profile']!r}")
    provider = os.environ.get(f"GIGBID_{role.upper()}_PROVIDER") or prof["provider"]
    model = os.environ.get(f"GIGBID_{role.upper()}_MODEL") or prof["model"]
    return provider, model


def chat_model(role: str, config: dict | None = None, temperature: float = 0.0) -> BaseChatModel:
    provider, model = resolve(role, config)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=model, temperature=temperature, base_url=base_url)
    if provider == "groq":
        if not os.environ.get("GROQ_API_KEY"):
            raise ModelNotConfigured("GROQ_API_KEY is not set (or override the provider via env)")
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, temperature=temperature)
    raise ModelNotConfigured(f"provider {provider!r} is not wired yet")


def chat_model_for_node(node: str, config: dict | None = None) -> BaseChatModel:
    cfg = config or load_config()
    return chat_model(cfg["nodes"][node], cfg)
