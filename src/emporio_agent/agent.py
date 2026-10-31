"""The agent loop: plain function calling over any OpenAI-compatible endpoint.

No framework on purpose. The loop is ~60 lines, every step is visible and
testable with a fake client, and swapping providers is an environment variable
(OpenAI, Maritaca, Ollama, Groq, OpenRouter all speak this protocol).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .policies import PolicyBook, default_policy_book
from .prompt import build_system_prompt
from .store import Store
from .tools import TOOL_SCHEMAS, ToolContext, dispatch, now_in_store

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1-mini"
MAX_TOOL_ROUNDS = 6
MAX_USER_TURNS = 12
FALLBACK_REPLY = ("Desculpe, tive um problema para consultar o sistema agora. Pode tentar de novo em instantes? "
                  "Se preferir, fale com a equipe pelo (67) 3341-4444.")


class ChatClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


class OpenAIChatClient:
    """Thin adapter so the loop does not depend on the SDK's response objects."""

    def __init__(self, model: str | None = None, temperature: float = 0.3) -> None:
        from openai import OpenAI

        self.client = OpenAI()  # reads OPENAI_API_KEY and OPENAI_BASE_URL
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.temperature = temperature

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, tools=tools, temperature=self.temperature,
        )
        msg = response.choices[0].message
        out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            out["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in msg.tool_calls
            ]
        return out


@dataclass
class ToolTrace:
    name: str
    arguments: dict
    result: dict


@dataclass
class Turn:
    reply: str
    tools: list[ToolTrace] = field(default_factory=list)


class Agent:
    def __init__(self, client: ChatClient, store: Store | None = None, policies: PolicyBook | None = None,
                 clock_override: str | None = None, complaints_path: Path | None = None) -> None:
        self.client = client
        self.ctx = ToolContext(
            store=store or Store(),
            policies=policies or default_policy_book(),
            clock_override=clock_override if clock_override is not None else os.getenv("EMPORIO_NOW"),
            complaints_path=complaints_path or Path("complaints.jsonl"),
        )
        self.history: list[dict] = []

    def system_message(self) -> dict:
        now = now_in_store(self.ctx.clock_override)
        return {"role": "system", "content": build_system_prompt(self.ctx.policies, now)}

    def context_window(self) -> list[dict]:
        """Last MAX_USER_TURNS user turns, cut at a user message so a tool result
        is never sent without the assistant call that produced it."""
        user_idx = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        start = user_idx[-MAX_USER_TURNS] if len(user_idx) > MAX_USER_TURNS else 0
        return self.history[start:]

    def send(self, user_text: str) -> Turn:
        self.history.append({"role": "user", "content": user_text})
        traces: list[ToolTrace] = []
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                message = self.client.complete([self.system_message(), *self.context_window()], TOOL_SCHEMAS)
            except Exception:  # provider/network error: degrade, do not crash the chat
                log.exception("LLM call failed; answering with the fallback message")
                self.history.append({"role": "assistant", "content": FALLBACK_REPLY})
                return Turn(FALLBACK_REPLY, traces)
            self.history.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                return Turn(message.get("content", "").strip(), traces)
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(self.ctx, name, args) if isinstance(args, dict) else {"erro": "argumentos"}
                traces.append(ToolTrace(name, args, result))
                self.history.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps(result, ensure_ascii=False)})
        reply = "Essa ficou complexa para mim. Vou pedir para alguém da equipe te responder, tudo bem?"
        self.history.append({"role": "assistant", "content": reply})
        return Turn(reply, traces)

    # ------------------------------------------------------------- persistence

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.history, ensure_ascii=False, indent=1), encoding="utf-8")

    def load(self, path: Path) -> None:
        if path.exists():
            self.history = json.loads(path.read_text(encoding="utf-8"))
