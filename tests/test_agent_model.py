"""Model/provider selection — construction only, no LLM calls."""

import pytest

from parkrun_agent.agent.agent import build_model


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_model(provider="banana")


def test_anthropic_backend(monkeypatch):
    pytest.importorskip("langchain_anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")
    model = build_model(model="claude-haiku-5-5", provider="anthropic")
    assert type(model).__name__ == "ChatAnthropic"


def test_ollama_backend():
    pytest.importorskip("langchain_ollama")
    model = build_model(model="llama3.1", provider="ollama")
    assert type(model).__name__ == "ChatOllama"


def test_provider_from_env(monkeypatch):
    pytest.importorskip("langchain_ollama")
    monkeypatch.setenv("PARKRUN_LLM_PROVIDER", "ollama")
    model = build_model()
    assert type(model).__name__ == "ChatOllama"
