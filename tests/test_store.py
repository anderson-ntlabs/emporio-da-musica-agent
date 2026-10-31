import pytest

from emporio_agent import payments
from emporio_agent.store import Store, normalize


@pytest.fixture(scope="module")
def store() -> Store:
    return Store()


def test_loads_all_tables(store):
    assert len(store.products) == 65
    assert len(store.orders) == 20
    assert len(store.customers) == 50
    assert len(store.categories) == 9


def test_normalize_strips_accents():
    assert normalize("Violão Elétrico!") == "violao eletrico"


def test_takamine_gd20_price_ignores_expired_promotion(store):
    result = store.product_details("Takamine GD20")
    product = result["produto"]
    assert product["nome"] == "Takamine GD20 Dreadnought Natural"
    assert product["preco_tabela"] == 2199
    assert "promocao_ativa" not in product
    assert product["promocoes_encerradas"] == ["Oferta Especial"]
    assert product["preco_no_pix"] == pytest.approx(2089.05)


def test_active_promotion_disables_pix_discount(store):
    product = store.product_details("Crafter HT-100")["produto"]
    assert product["promocao_ativa"]["desconto_percentual"] == 18
    assert product["promocao_ativa"]["preco_promocional"] == pytest.approx(1967.18)
    assert "preco_no_pix" not in product


def test_out_of_stock_product_gets_alternatives(store):
    product = store.product_details("Giannini GF-3D")["produto"]
    assert product["disponivel_para_venda"] is False
    assert product["alternativas_semelhantes"]
    assert all(a["disponivel_para_venda"] for a in product["alternativas_semelhantes"])


def test_discontinued_product_with_stock_is_not_sellable(store):
    product = store.product_details("Ibanez Bass 2X")["produto"]
    assert product["situacao"] == "descontinuado"
    assert product["em_estoque"] == 0
    assert product["disponivel_para_venda"] is False


def test_search_violoes_up_to_1000_only_sellable_and_sorted(store):
    result = store.search(category="violões", max_price=1000)
    prices = [r["promocao_ativa"]["preco_promocional"] if "promocao_ativa" in r else r["preco_tabela"]
              for r in result["resultados"]]
    assert prices == sorted(prices)
    assert all(p <= 1000 for p in prices)
    names = {r["nome"] for r in result["resultados"]}
    assert "Giannini GF-3D Dreadnought Sunburst" not in names  # stock 0
    assert "Shelby SN-7C 7 Cordas Nylon Natural" not in names  # discontinued


def test_search_unknown_category(store):
    assert store.search(category="amplificadores")["resultados"] == []


def test_empty_category_is_reported(store):
    result = store.search(category="sopro")
    assert result["total_encontrado"] == 0
    assert "avisos" in result


def test_order_requires_identity(store):
    assert store.order_status(8)["autorizado"] is False


def test_order_with_wrong_email_does_not_reveal_existence(store):
    wrong = store.order_status(8, email="someone@else.com")
    missing = store.order_status(999, email="someone@else.com")
    assert wrong == missing


def test_order_with_matching_email(store):
    result = store.order_status(8, email="AnaCarol.Ferreira@coldmail.com")
    assert result["autorizado"] is True
    assert result["status"] == "enviado"
    assert result["codigo_rastreamento"] == "BRJL5544332BR"
    assert result["cliente_primeiro_nome"] == "Ana"


def test_order_with_matching_phone(store):
    result = store.order_status(8, phone="67 99654 7821")
    assert result["autorizado"] is True


def test_cancelled_order_shows_reason(store):
    customer = store.customers[store.orders[18].customer_id]
    result = store.order_status(18, email=customer.email)
    assert result["status"] == "cancelado"
    assert "fora de estoque" in result["observacao"]


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(120, 2), (150, 3), (480, 6), (1000, 10), (1199, 11), (2199, 12), (40, 1)],
)
def test_max_installments_follow_tiers(amount, expected):
    assert payments.max_installments(amount) == expected


def test_simulate_pix_and_combination():
    sim = payments.simulate(2199)
    assert sim["pix"]["valor"] == pytest.approx(2089.05)
    assert sim["combinar_formas"] is True
    promo = payments.simulate(1967.18, promotional=True)
    assert promo["pix"]["valor"] == pytest.approx(1967.18)
