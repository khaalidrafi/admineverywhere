"""In-process assistant embedding: the admineverywhere[agent] extra.

The panel embeds the slave-agent core as a Python library (Owner
architecture decision 2026-11-05; slave-agent specs/014): import the
core, construct it with the persona/brand configuration, run turns,
read results. No subprocess, no socket, no endpoint is required for the
embedding — this module is the stable seam the spec promises.

Every slave-agent import is lazy on purpose: a server that installed
the plugin without the [agent] extra boots normally and only an actual
assistant call reports how to enable it.

Configuration (Django settings):

    ADMINEEVERYWHERE_AGENT = {
        "persona_file": "/srv/personas/acme.json",   # optional
        "base_url": "http://model-host:30000/v1",    # model endpoint
        "model": "my-model",
        "api_key_env": "ASSISTANT_API_KEY",          # env var NAME, never a value
    }

Secrets ride env var names (the slave-agent purity law): a value in
settings raises ``AgentConfigurationError`` naming the field.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class AgentUnavailable(RuntimeError):
    """The slave-agent core is not importable; install the [agent] extra."""

    INSTALL_HINT = (
        "pip install 'admineverywhere[agent]' "
        "(slave-agent from github.com/khaalidrafi/slave-agent, branch ai/slave-agent)"
    )


class AgentConfigurationError(ValueError):
    """The assistant settings block names the field that is wrong."""


def _require_block(settings_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    block = settings_dict or {}
    if not isinstance(block, dict):
        raise AgentConfigurationError(
            "ADMINEVERYWHERE_AGENT must be a dict; got " + type(block).__name__)
    key = block.get("api_key_env")
    if key is not None and (not isinstance(key, str) or not key.isidentifier()):
        raise AgentConfigurationError(
            "api_key_env must be an ENV VAR NAME (an identifier), never a value")
    if not block.get("base_url"):
        raise AgentConfigurationError(
            "ADMINEVERYWHERE_AGENT.base_url is required (the model endpoint)")
    return block


class EmbeddedAssistant:
    """One assistant instance per configuration; cheap to keep, not free to make.

    The persona compiles once (fail-fast on a malformed artifact, per the
    slave-agent contract); turns run through the core's ``AIAgent``.
    """

    def __init__(self, settings_dict: Optional[Dict[str, Any]] = None,
                 persona_file: Optional[str] = None):
        self._config = _require_block(settings_dict)
        self._persona_file = persona_file or self._config.get("persona_file")
        self._agent = None
        self._persona: Optional[Dict[str, Any]] = None
        if self._persona_file:
            self._persona = self._load_persona(self._persona_file)

    @staticmethod
    def _load_persona(path: str) -> Dict[str, Any]:
        try:
            from persona import load_persona
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise AgentUnavailable(AgentUnavailable.INSTALL_HINT) from exc
        return load_persona(path)

    @property
    def system_prompt(self) -> str:
        """The compiled deployment persona; empty when none is configured.

        A request-level system message always wins over this (the
        slave-agent precedence law); the panel decides what to send.
        """
        if not self._persona:
            return ""
        from persona import compile_persona
        return compile_persona(self._persona)

    def _core(self):
        if self._agent is None:
            try:
                from run_agent import AIAgent
            except ImportError as exc:
                raise AgentUnavailable(AgentUnavailable.INSTALL_HINT) from exc
            api_key = ""
            env_name = self._config.get("api_key_env")
            if env_name:
                api_key = os.environ.get(env_name, "")
            self._agent = AIAgent(
                base_url=self._config["base_url"],
                model=self._config.get("model", ""),
                api_key=api_key or None,
            )
        return self._agent

    def run_turn(self, messages: List[Dict[str, str]]) -> str:
        """Run one turn: messages in (role/content dicts), the reply text out.

        The persona system prompt is prepended only when the caller sent
        no system message of its own.
        """
        core = self._core()
        has_system = any(m.get("role") == "system" for m in messages)
        prompt_messages = list(messages)
        if not has_system and self.system_prompt:
            prompt_messages = [{"role": "system", "content": self.system_prompt},
                               *prompt_messages]
        # AIAgent's conversation entry point takes the user text; history is
        # its own session state. Flatten to the last user message for the
        # turn, which is the panel's chat shape (the panel owns history).
        user_text = next((m["content"] for m in reversed(prompt_messages)
                          if m.get("role") == "user"), "")
        if not user_text:
            raise AgentConfigurationError("run_turn needs at least one user message")
        system = next((m["content"] for m in prompt_messages if m.get("role") == "system"), None)
        reply = core.run_conversation(user_text, ephemeral_system_prompt=system)
        return reply if isinstance(reply, str) else str(reply)


def get_assistant() -> EmbeddedAssistant:
    """The configured assistant from Django settings (one per process)."""
    from django.conf import settings
    return EmbeddedAssistant(getattr(settings, "ADMINEVERYWHERE_AGENT", None))
