"""Tools exposed to the model (OpenAI function-calling schema) and their dispatch.

Typed tools instead of a SQL agent: the customers table holds names, phones
and e-mails. Letting the model write free SQL would make the privacy rule
(policy 9) a prompt instruction; here it is a code path the model cannot skip.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import payments
from .policies import PolicyBook
from .store import Store

STORE_TZ = ZoneInfo("America/Campo_Grande")

# Section 2 of the manual.
OPENING_HOURS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}
WEEKDAYS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

# National holidays (fixed dates + movable ones for 2026/2027). Municipal ones are not covered.
HOLIDAYS = {
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 4, 21),
    date(2026, 5, 1), date(2026, 6, 4), date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 2),
    date(2026, 11, 15), date(2026, 11, 20), date(2026, 12, 25), date(2027, 1, 1), date(2027, 2, 8),
    date(2027, 2, 9), date(2027, 3, 26), date(2027, 4, 21), date(2027, 5, 1), date(2027, 5, 27),
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Busca instrumentos no catálogo por categoria, texto livre e faixa de preço. "
                           "Retorna apenas itens à venda, ordenados do mais barato, com preço, promoção ativa e estoque. "
                           "Use para perguntas como 'quais violões até R$ 1000?' ou 'tem ukulele elétrico?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Categoria, ex.: violões, guitarras, ukuleles, baixos"},
                    "text": {"type": "string", "description": "Palavras que devem aparecer no nome, descrição ou "
                                                              "especificações, ex.: 'nylon', 'elétrico', '7 cordas', 'Yamaha'"},
                    "max_price": {"type": "number", "description": "Preço máximo em reais (considera promoção ativa)"},
                    "min_price": {"type": "number", "description": "Preço mínimo em reais"},
                    "include_unavailable": {"type": "boolean", "description": "Incluir itens sem estoque ou "
                                                                              "descontinuados (padrão: false)"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Detalhes de um produto pelo nome (aceita nome parcial, ex.: 'Takamine GD20'): preço, "
                           "promoção ativa, promoções encerradas, estoque, situação, descrição e especificações. "
                           "Se não estiver à venda, traz alternativas.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_payment",
            "description": "Calcula as condições de pagamento (PIX com ou sem desconto, parcelas no crédito pelas "
                           "faixas da política, se pode combinar formas). Informe o nome do produto (usa o preço "
                           "vigente, com promoção) ou um valor em reais.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1},
                    "amount": {"type": "number", "description": "Valor em reais, quando não for um produto só"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_policy",
            "description": "Lê uma seção inteira do manual de políticas da loja (número ou título). Consulte antes de "
                           "responder sobre trocas, devoluções, garantia, frete, pagamento, horários, promoções, "
                           "contato ou privacidade.",
            "parameters": {
                "type": "object",
                "properties": {"section": {"type": "string", "description": "Ex.: '4' ou 'Trocas e Devoluções'"}},
                "required": ["section"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_order",
            "description": "Status de um pedido. Exige o número do pedido e o e-mail OU o telefone usado na compra; "
                           "peça esses dados ao cliente antes de chamar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_hours_now",
            "description": "Diz se a loja está aberta agora e quando abre/fecha, pelo horário de Campo Grande.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "register_complaint",
            "description": "Registra uma reclamação ou pedido que precisa de um atendente humano (troca, devolução, "
                           "defeito, problema com entrega) e devolve um protocolo. Use depois de entender o caso e "
                           "ter nome e um contato do cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Resumo objetivo do caso"},
                    "customer_name": {"type": "string"},
                    "contact": {"type": "string", "description": "Telefone ou e-mail para retorno"},
                    "order_id": {"type": "integer"},
                },
                "required": ["summary", "customer_name", "contact"],
                "additionalProperties": False,
            },
        },
    },
]


def now_in_store(override: str | None = None) -> datetime:
    if override:
        parsed = datetime.fromisoformat(override)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=STORE_TZ)
    return datetime.now(STORE_TZ)


def store_hours(now: datetime) -> dict:
    def hours_for(day: date) -> tuple[int, int] | None:
        if day in HOLIDAYS:
            return None
        return OPENING_HOURS.get(day.weekday())

    today = hours_for(now.date())
    is_open = bool(today) and today[0] <= now.hour < today[1]
    result: dict = {
        "agora": now.strftime("%Y-%m-%d %H:%M"),
        "dia_da_semana": WEEKDAYS_PT[now.weekday()],
        "aberta_agora": is_open,
        "feriado_hoje": now.date() in HOLIDAYS,
    }
    if is_open:
        result["fecha_hoje_as"] = f"{today[1]:02d}:00"
    else:
        for offset in range(0, 8):
            day = now.date() + timedelta(days=offset)
            hours = hours_for(day)
            if hours and (offset > 0 or now.hour < hours[0]):
                result["proxima_abertura"] = f"{WEEKDAYS_PT[day.weekday()]} {day:%d/%m} às {hours[0]:02d}:00"
                break
    return result


@dataclass
class ToolContext:
    store: Store
    policies: PolicyBook
    complaints_path: Path = Path("complaints.jsonl")
    clock_override: str | None = None
    complaints: list[dict] = field(default_factory=list)


def _simulate(ctx: ToolContext, product_name: str | None = None, quantity: int = 1,
              amount: float | None = None) -> dict:
    if product_name:
        details = ctx.store.product_details(product_name)
        if not details["encontrado"]:
            return details
        product = details["produto"]
        promo = product.get("promocao_ativa")
        unit = promo["preco_promocional"] if promo else product["preco_tabela"]
        sim = payments.simulate(unit * max(quantity, 1), promotional=bool(promo))
        return {"produto": product["nome"], "quantidade": max(quantity, 1),
                "disponivel_para_venda": product["disponivel_para_venda"], **sim}
    if amount is None or amount <= 0:
        return {"erro": "Informe product_name ou amount."}
    return payments.simulate(amount)


def _register(ctx: ToolContext, summary: str, customer_name: str, contact: str,
              order_id: int | None = None) -> dict:
    protocol = f"EM-{now_in_store(ctx.clock_override):%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    record = {"protocolo": protocol, "resumo": summary, "cliente": customer_name,
              "contato": contact, "pedido": order_id,
              "registrado_em": now_in_store(ctx.clock_override).isoformat()}
    ctx.complaints.append(record)
    with open(ctx.complaints_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"protocolo": protocol, "prazo_retorno": "até 24 horas úteis (política 7.3)"}


def dispatch(ctx: ToolContext, name: str, arguments: dict) -> dict:
    """Run a tool. Errors come back as data so the model can recover in the next turn."""
    try:
        match name:
            case "search_products":
                return ctx.store.search(
                    text=arguments.get("text"), category=arguments.get("category"),
                    max_price=arguments.get("max_price"), min_price=arguments.get("min_price"),
                    only_available=not arguments.get("include_unavailable", False),
                )
            case "get_product":
                return ctx.store.product_details(arguments["name"])
            case "simulate_payment":
                return _simulate(ctx, arguments.get("product_name"), arguments.get("quantity", 1),
                                 arguments.get("amount"))
            case "read_policy":
                return ctx.policies.read(str(arguments["section"]))
            case "check_order":
                return ctx.store.order_status(int(arguments["order_id"]), arguments.get("email"),
                                              arguments.get("phone"), today=now_in_store(ctx.clock_override).date())
            case "store_hours_now":
                return store_hours(now_in_store(ctx.clock_override))
            case "register_complaint":
                return _register(ctx, arguments["summary"], arguments["customer_name"], arguments["contact"],
                                 arguments.get("order_id"))
            case _:
                return {"erro": f"Ferramenta desconhecida: {name}"}
    except (KeyError, ValueError, TypeError) as exc:
        return {"erro": f"Argumentos inválidos para {name}: {exc}"}
