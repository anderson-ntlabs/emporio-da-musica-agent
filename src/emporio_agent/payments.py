"""Payment conditions from section 3 of the policy manual, as code.

Assumption (documented in the README): the summary table says "parcela mínima
de R$ 100,00" for credit card, while 3.1 gives tiered minimums. The detailed
rule (3.1) is treated as authoritative and the table as the 7x-12x case. The
phrase "sem valor mínimo de parcela (exceto abaixo de R$ 50,00)" in the 1x-3x
tier is read as "each installment must be at least R$ 50,00".
"""

from __future__ import annotations

from .store import money

PIX_DISCOUNT = 0.05
COMBINATION_THRESHOLD = 2000.00

# (max installments in tier, minimum installment value)
TIERS = ((3, 50.00), (6, 80.00), (12, 100.00))


def min_installment(n: int) -> float:
    for max_n, minimum in TIERS:
        if n <= max_n:
            return minimum
    raise ValueError("A loja parcela em no máximo 12x.")


def max_installments(amount: float) -> int:
    """Largest n (1-12) whose installment respects its tier minimum."""
    best = 1
    for n in range(1, 13):
        if amount / n >= min_installment(n):
            best = n
    return best


def simulate(amount: float, promotional: bool = False) -> dict:
    amount = money(amount)
    n_max = max_installments(amount)
    options = []
    for n in (1, 2, 3, 6, 10, 12):
        if n <= n_max:
            options.append({"parcelas": n, "valor_parcela": money(amount / n)})
    if n_max not in (o["parcelas"] for o in options):
        options.append({"parcelas": n_max, "valor_parcela": money(amount / n_max)})
    result: dict = {
        "valor": amount,
        "cartao_credito": {
            "max_parcelas_sem_juros": n_max,
            "exemplos": sorted(options, key=lambda o: o["parcelas"]),
        },
        "debito_e_boleto": {"valor": amount, "observacao": "boleto compensa em até 3 dias úteis"},
        "combinar_formas": amount > COMBINATION_THRESHOLD,
    }
    if promotional:
        result["pix"] = {"valor": amount,
                         "observacao": "sem desconto extra: o desconto de PIX não acumula com promoção"}
    else:
        result["pix"] = {"valor": money(amount * (1 - PIX_DISCOUNT)), "desconto": "5%"}
    return result
