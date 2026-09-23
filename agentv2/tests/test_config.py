from __future__ import annotations

from agentv2 import config
from agentv2.model import build_model


def test_thinking_goes_to_the_chat_template_only_when_set(root, monkeypatch):
    assert "extra_body" not in (build_model(config.load(root).llm).settings or {})
    monkeypatch.setenv("AGENTV2_LLM_THINKING", "false")
    settings = config.load(root)
    assert settings.llm.thinking is False
    assert (build_model(settings.llm).settings or {}).get("extra_body") == {"chat_template_kwargs": {"enable_thinking": False}}
    monkeypatch.setenv("AGENTV2_LLM_THINKING", "")
    assert config.load(root).llm.thinking is None
