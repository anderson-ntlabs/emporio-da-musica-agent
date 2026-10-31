import json

import pytest

from emporio_agent.agent import FALLBACK_REPLY, MAX_USER_TURNS, Agent
from emporio_agent.tools import ToolContext, dispatch, now_in_store, store_hours


class ScriptedClient:
    """Fake LLM: returns pre-baked assistant messages and records what it saw."""

    def __init__(self, messages):
        self.messages = list(messages)
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(messages)
        return self.messages.pop(0)


def tool_call(name, args, call_id="c1"):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


@pytest.fixture
def agent(tmp_path):
    def make(script):
        return Agent(ScriptedClient(script), clock_override="2026-11-03T10:00:00",
                     complaints_path=tmp_path / "complaints.jsonl")
    return make


def test_tool_result_is_fed_back_and_final_reply_returned(agent):
    a = agent([tool_call("get_product", {"name": "Takamine GD20"}),
               {"role": "assistant", "content": "O Takamine GD20 sai por R$ 2.199,00."}])
    turn = a.send("Quanto custa o Takamine GD20?")
    assert turn.reply == "O Takamine GD20 sai por R$ 2.199,00."
    assert [t.name for t in turn.tools] == ["get_product"]
    tool_msg = a.history[2]
    assert tool_msg["role"] == "tool" and "2199" in tool_msg["content"]


def test_system_prompt_carries_clock_and_toc(agent):
    a = agent([{"role": "assistant", "content": "Oi!"}])
    a.send("oi")
    system = a.client.seen[0][0]["content"]
    assert "03/11/2026 10:00 (terça-feira)" in system
    assert "4. Política de Trocas e Devoluções" in system


def test_provider_error_degrades_gracefully(agent):
    class Boom:
        def complete(self, messages, tools):
            raise RuntimeError("timeout")
    a = agent([])
    a.client = Boom()
    assert a.send("oi").reply == FALLBACK_REPLY


def test_bad_tool_arguments_do_not_crash(agent):
    a = agent([{"role": "assistant", "content": "", "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "check_order", "arguments": "{not json"}}]},
        {"role": "assistant", "content": "Me passa o número do pedido?"}])
    turn = a.send("cadê meu pedido")
    assert "erro" in turn.tools[0].result


def test_context_window_cuts_at_user_turns(agent):
    a = agent([{"role": "assistant", "content": "ok"}] * (MAX_USER_TURNS + 3))
    for i in range(MAX_USER_TURNS + 3):
        a.send(f"msg {i}")
    window = a.context_window()
    assert window[0]["role"] == "user"
    assert sum(m["role"] == "user" for m in window) == MAX_USER_TURNS


def test_session_round_trip(agent, tmp_path):
    a = agent([{"role": "assistant", "content": "oi"}])
    a.send("oi")
    a.save(tmp_path / "s.json")
    b = agent([])
    b.load(tmp_path / "s.json")
    assert b.history == a.history


def test_register_complaint_writes_protocol(agent, tmp_path):
    a = agent([])
    result = dispatch(a.ctx, "register_complaint",
                      {"summary": "violão chegou com trinca", "customer_name": "Ana", "contact": "ana@x.com"})
    assert result["protocolo"].startswith("EM-20261103-")
    assert (tmp_path / "complaints.jsonl").read_text(encoding="utf-8").count("trinca") == 1


def test_unknown_tool(agent):
    assert "erro" in dispatch(agent([]).ctx, "hack", {})


@pytest.mark.parametrize(
    ("when", "is_open", "next_open"),
    [
        ("2026-11-03T10:00:00", True, None),                       # Tuesday morning
        ("2026-10-31T14:00:00", False, "terça-feira 03/11"),        # Saturday afternoon; Monday 02/11 is Finados
        ("2026-11-01T10:00:00", False, "terça-feira 03/11"),        # Sunday, next Monday is Finados
        ("2026-11-03T07:30:00", False, "terça-feira 03/11 às 09:00"),
    ],
)
def test_store_hours(when, is_open, next_open):
    result = store_hours(now_in_store(when))
    assert result["aberta_agora"] is is_open
    if next_open:
        assert result["proxima_abertura"].startswith(next_open)


def test_simulate_payment_uses_promotional_price():
    from emporio_agent.policies import default_policy_book
    from emporio_agent.store import Store
    ctx = ToolContext(store=Store(), policies=default_policy_book())
    result = dispatch(ctx, "simulate_payment", {"product_name": "Ohana CK-20"})
    assert result["valor"] == pytest.approx(439.2)
    assert "sem desconto extra" in result["pix"]["observacao"]


def test_prompt_pins_store_contacts(agent):
    a = agent([{"role": "assistant", "content": "Oi!"}])
    a.send("oi")
    system = a.client.seen[0][0]["content"]
    assert "(67) 3341-4444" in system
    assert "3321-4500" not in system
