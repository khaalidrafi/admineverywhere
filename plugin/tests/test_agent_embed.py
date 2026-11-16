"""The agent-embedding seam (admineverywhere[agent], spec 014 on the
slave-agent side).

The live path needs the slave-agent package installed (the [agent]
extra); these tests verify the SEAM without it: configuration law,
persona precedence, and the import-guard contract. A stub stands in for
the core so the wiring is exercised, not skipped.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from admineverywhere.agent_embed import (AgentConfigurationError,
                                         AgentUnavailable, EmbeddedAssistant)

BLOCK = {"base_url": "http://127.0.0.1:30000/v1", "model": "test-model",
         "api_key_env": "ASSISTANT_API_KEY"}


@pytest.fixture
def persona_stub(monkeypatch, tmp_path):
    """A fake persona package: compile mirrors the real contract's shape."""
    persona = types.ModuleType("persona")

    def load_persona(path):
        p = Path(path)
        if not p.exists():
            raise ValueError(f"{path}: no such persona file")
        import json
        return json.loads(p.read_text())

    def compile_persona(data):
        identity = data.get("identity") or {}
        return f"You are {identity.get('assistant')}."

    persona.load_persona = load_persona
    persona.compile_persona = compile_persona
    monkeypatch.setitem(sys.modules, "persona", persona)

    artifact = tmp_path / "acme.json"
    artifact.write_text('{"identity": {"assistant": "Dot"}}', encoding="utf-8")
    return artifact


@pytest.fixture
def core_stub(monkeypatch):
    """A fake run_agent.AIAgent recording what the seam sends it."""
    run_agent = types.ModuleType("run_agent")
    calls: list[dict] = []

    class AIAgent:
        def __init__(self, **kw):
            calls.append({"init": kw})

        def run_conversation(self, text, ephemeral_system_prompt=None):
            calls.append({"turn": text, "system": ephemeral_system_prompt})
            return f"echo: {text}"

    run_agent.AIAgent = AIAgent
    monkeypatch.setitem(sys.modules, "run_agent", run_agent)
    return calls


class TestConfigurationLaw:
    def test_missing_base_url_names_the_field(self):
        with pytest.raises(AgentConfigurationError, match="base_url"):
            EmbeddedAssistant({"model": "m"})

    def test_an_api_key_value_is_rejected_not_stored(self):
        with pytest.raises(AgentConfigurationError, match="ENV VAR NAME"):
            EmbeddedAssistant({**BLOCK, "api_key_env": "sk-not-a-name"})

    def test_a_non_dict_block_is_named(self):
        with pytest.raises(AgentConfigurationError, match="dict"):
            EmbeddedAssistant(["nope"])


class TestSeam:
    def test_turn_runs_through_the_core_with_persona_prepended(
            self, persona_stub, core_stub):
        assistant = EmbeddedAssistant(BLOCK, persona_file=str(persona_stub))
        reply = assistant.run_turn([{"role": "user", "content": "hello"}])
        assert reply == "echo: hello"
        assert core_stub[-1]["system"] == "You are Dot."

    def test_a_request_system_message_beats_the_persona(
            self, persona_stub, core_stub):
        assistant = EmbeddedAssistant(BLOCK, persona_file=str(persona_stub))
        assistant.run_turn([
            {"role": "system", "content": "You are the night shift."},
            {"role": "user", "content": "who are you"},
        ])
        assert core_stub[-1]["system"] == "You are the night shift."

    def test_no_persona_no_system(self, core_stub):
        assistant = EmbeddedAssistant(BLOCK)
        assistant.run_turn([{"role": "user", "content": "hi"}])
        assert core_stub[-1]["system"] is None

    def test_a_turn_needs_a_user_message(self, persona_stub, core_stub):
        assistant = EmbeddedAssistant(BLOCK, persona_file=str(persona_stub))
        with pytest.raises(AgentConfigurationError, match="user message"):
            assistant.run_turn([{"role": "assistant", "content": "hi"}])


def test_the_extra_is_the_documented_escape_hatch():
    """Without the core importable, the error names the install, not a traceback."""
    try:
        import run_agent  # noqa: F401
        pytest.skip("slave-agent core installed; the guard path is not reachable")
    except ImportError:
        pass
    assistant = EmbeddedAssistant(BLOCK)
    with pytest.raises(AgentUnavailable, match="admineverywhere\\[agent\\]"):
        assistant.run_turn([{"role": "user", "content": "hi"}])
