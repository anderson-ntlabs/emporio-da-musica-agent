"""Store data: loading, cleaning and the business rules that depend on it.

Every number the agent tells a customer (price, stock, discount, order status)
comes from here, never from the model. The model decides *what* to look up;
this module decides *what is true*.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

PIX_DISCOUNT = 0.05

PRODUCT_STATUS_PT = {
    "active": "disponível no catálogo",
    "discontinued": "descontinuado",
    "coming_soon": "lançamento em breve (ainda não vendido)",
}

ORDER_STATUS_PT = {
    "pending": "aguardando pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

PAYMENT_PT = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto",
}


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return " ".join(cleaned.split())


def digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def payment_label(method: str) -> str:
    if method.startswith("credit_"):
        return f"cartão de crédito em {method.removeprefix('credit_')}"
    return PAYMENT_PT.get(method, method)


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    category: str
    description: str
    price: float
    stock: int
    status: str
    specs: dict = field(default_factory=dict)

    @property
    def sellable(self) -> bool:
        return self.status == "active" and self.stock > 0


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    percent: float
    description: str
    active: bool


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    date: str
    status: str
    total: float
    payment_method: str
    tracking_code: str
    estimated_delivery: str
    notes: str
    items: tuple[OrderItem, ...]


def _read(name: str, data_dir: Path) -> list[dict[str, str]]:
    with open(data_dir / f"{name}.csv", encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


class Store:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        categories = {int(r["category_id"]): r for r in _read("categories", data_dir)}
        self.categories = {cid: r["name"] for cid, r in categories.items()}
        self.category_descriptions = {cid: r["description"] for cid, r in categories.items()}

        self.products: dict[int, Product] = {}
        for r in _read("products", data_dir):
            cid = int(r["category_id"])
            try:
                specs = json.loads(r["specs"]) if r["specs"] else {}
            except json.JSONDecodeError:
                specs = {}
            self.products[int(r["product_id"])] = Product(
                id=int(r["product_id"]),
                name=r["name"],
                category_id=cid,
                category=self.categories.get(cid, "Outros"),
                description=r["description"],
                price=float(r["price_brl"]),
                stock=int(r["stock_quantity"] or 0),
                status=r["status"],
                specs=specs,
            )

        self.promotions = [
            Promotion(
                id=int(r["promotion_id"]),
                product_id=int(r["product_id"]),
                percent=float(r["discount_percent"]),
                description=r["description"],
                active=r["is_active"] == "1",
            )
            for r in _read("promotions", data_dir)
        ]

        self.customers = {
            int(r["customer_id"]): Customer(
                id=int(r["customer_id"]),
                name=r["name"],
                phone=r["phone"],
                email=r["email"].lower(),
                city=r["city"],
            )
            for r in _read("customers", data_dir)
        }

        items: dict[int, list[OrderItem]] = {}
        for r in _read("order_items", data_dir):
            items.setdefault(int(r["order_id"]), []).append(
                OrderItem(product_id=int(r["product_id"]), quantity=int(r["quantity"]))
            )
        self.orders = {
            int(r["order_id"]): Order(
                id=int(r["order_id"]),
                customer_id=int(r["customer_id"]),
                date=r["order_date"],
                status=r["status"],
                total=float(r["total_brl"]),
                payment_method=r["payment_method"],
                tracking_code=r["tracking_code"],
                estimated_delivery=r["estimated_delivery"],
                notes=r["notes"],
                items=tuple(items.get(int(r["order_id"]), [])),
            )
            for r in _read("orders", data_dir)
        }

    # ------------------------------------------------------------------ pricing

    def active_promotion(self, product_id: int) -> Promotion | None:
        """Best active promotion for a product. Expired ones are never applied."""
        active = [p for p in self.promotions if p.product_id == product_id and p.active]
        return max(active, key=lambda p: p.percent, default=None)

    def expired_promotions(self, product_id: int) -> list[Promotion]:
        return [p for p in self.promotions if p.product_id == product_id and not p.active]

    def price_info(self, product: Product) -> dict:
        """Price view following policy 6.2: promo price shown with the original and
        the percentage; the 5% PIX discount applies only when there is no promotion."""
        promo = self.active_promotion(product.id)
        info: dict = {"preco_tabela": round(product.price, 2)}
        if promo:
            info["promocao_ativa"] = {
                "nome": promo.description,
                "desconto_percentual": promo.percent,
                "preco_promocional": round(product.price * (1 - promo.percent / 100), 2),
            }
            info["pix"] = "desconto de 5% no PIX NÃO se aplica sobre preço promocional"
        else:
            info["preco_no_pix"] = round(product.price * (1 - PIX_DISCOUNT), 2)
        expired = self.expired_promotions(product.id)
        if expired:
            info["promocoes_encerradas"] = sorted({p.description for p in expired})
        return info

    # ----------------------------------------------------------------- products

    def product_view(self, product: Product, detailed: bool = False) -> dict:
        view = {
            "id": product.id,
            "nome": product.name,
            "categoria": product.category,
            "situacao": PRODUCT_STATUS_PT.get(product.status, product.status),
            "em_estoque": product.stock if product.status == "active" else 0,
            "disponivel_para_venda": product.sellable,
            **self.price_info(product),
        }
        if detailed:
            view["descricao"] = product.description
            view["especificacoes"] = product.specs
        return view

    def _name_score(self, query: str, product: Product) -> float:
        q, name = normalize(query), normalize(product.name)
        if not q:
            return 0.0
        if q in name:
            return 1.0
        q_tokens, n_tokens = set(q.split()), set(name.split())
        overlap = len(q_tokens & n_tokens) / len(q_tokens)
        return max(overlap, SequenceMatcher(None, q, name).ratio())

    def find_products(self, query: str, limit: int = 5, min_score: float = 0.5) -> list[Product]:
        scored = [(self._name_score(query, p), p) for p in self.products.values()]
        scored = [(s, p) for s, p in scored if s >= min_score]
        scored.sort(key=lambda sp: (-sp[0], sp[1].price))
        return [p for _, p in scored[:limit]]

    def category_id(self, name: str) -> int | None:
        target = normalize(name)
        for cid, cname in self.categories.items():
            ncname = normalize(cname)
            if target and (target in ncname or ncname in target):
                return cid
        # singular/plural and common synonyms
        synonyms = {
            "violao": 5, "guitarra": 1, "baixo": 2, "contrabaixo": 2, "bateria": 3,
            "percussao": 3, "teclado": 4, "piano": 4, "sintetizador": 4, "ukulele": 9,
            "sopro": 6, "metais": 7, "violino": 8, "cello": 8, "violoncelo": 8,
        }
        for key, cid in synonyms.items():
            if key in target:
                return cid
        return None

    def search(
        self,
        text: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
        only_available: bool = True,
        limit: int = 10,
    ) -> dict:
        products = list(self.products.values())
        notes: list[str] = []
        if category:
            cid = self.category_id(category)
            if cid is None:
                return {"resultados": [], "aviso": f"Categoria '{category}' não existe no catálogo.",
                        "categorias": list(self.categories.values())}
            products = [p for p in products if p.category_id == cid]
            if not products:
                notes.append(f"A categoria {self.categories[cid]} está sem itens cadastrados no momento.")
        if text:
            terms = normalize(text).split()
            products = [
                p for p in products
                if all(t in normalize(f"{p.name} {p.description} {' '.join(map(str, p.specs.values()))}")
                       for t in terms)
            ]
        if only_available:
            hidden = [p for p in products if not p.sellable]
            products = [p for p in products if p.sellable]
            if hidden:
                notes.append(
                    f"{len(hidden)} item(ns) fora de estoque, descontinuado(s) ou em pré-lançamento omitido(s)."
                )

        def effective(p: Product) -> float:
            promo = self.active_promotion(p.id)
            return p.price * (1 - promo.percent / 100) if promo else p.price

        if max_price is not None:
            products = [p for p in products if effective(p) <= max_price]
        if min_price is not None:
            products = [p for p in products if effective(p) >= min_price]
        products.sort(key=effective)
        total = len(products)
        result = {
            "total_encontrado": total,
            "resultados": [self.product_view(p) for p in products[:limit]],
        }
        if total > limit:
            result["observacao"] = f"Mostrando os {limit} mais baratos de {total}."
        if notes:
            result["avisos"] = notes
        return result

    def alternatives(self, product: Product, limit: int = 3) -> list[dict]:
        """Sellable products in the same category, closest in price."""
        pool = [p for p in self.products.values()
                if p.category_id == product.category_id and p.sellable and p.id != product.id]
        pool.sort(key=lambda p: abs(p.price - product.price))
        return [self.product_view(p) for p in pool[:limit]]

    def product_details(self, name: str) -> dict:
        matches = self.find_products(name, limit=4)
        if not matches:
            return {"encontrado": False,
                    "mensagem": f"Nenhum produto parecido com '{name}' no catálogo."}
        best = matches[0]
        view = self.product_view(best, detailed=True)
        if not best.sellable:
            view["alternativas_semelhantes"] = self.alternatives(best)
        result = {"encontrado": True, "produto": view}
        if len(matches) > 1 and self._name_score(name, best) < 1.0:
            result["outros_parecidos"] = [p.name for p in matches[1:]]
        return result

    # ------------------------------------------------------------------- orders

    def order_status(self, order_id: int, email: str | None = None, phone: str | None = None) -> dict:
        """Order lookup with identity check (policy section 9, LGPD).

        The order is only disclosed when the e-mail or the phone matches the
        customer who placed it. A failed check answers the same way whether the
        order exists or not, so the tool cannot be used to enumerate orders."""
        denied = {"autorizado": False,
                  "mensagem": "Não foi possível confirmar esse pedido com os dados informados. "
                              "Peça ao cliente para conferir o número do pedido e o e-mail ou "
                              "telefone usados na compra."}
        if not email and not phone:
            return {"autorizado": False,
                    "mensagem": "Para consultar um pedido é preciso o número do pedido e o e-mail "
                                "ou telefone usados na compra."}
        order = self.orders.get(order_id)
        if order is None:
            return denied
        customer = self.customers.get(order.customer_id)
        if customer is None:
            return denied
        ok_email = bool(email) and email.strip().lower() == customer.email
        ok_phone = bool(phone) and digits(phone)[-8:] == digits(customer.phone)[-8:] \
            and len(digits(phone)) >= 8
        if not (ok_email or ok_phone):
            return denied

        result = {
            "autorizado": True,
            "pedido": order.id,
            "cliente_primeiro_nome": customer.name.split()[0],
            "data_do_pedido": order.date,
            "status": ORDER_STATUS_PT.get(order.status, order.status),
            "pagamento": payment_label(order.payment_method),
            "total_pago": order.total,
            "itens": [
                {"produto": self.products[i.product_id].name if i.product_id in self.products
                 else f"produto {i.product_id}", "quantidade": i.quantity}
                for i in order.items
            ],
        }
        if order.tracking_code:
            result["codigo_rastreamento"] = order.tracking_code
        if order.estimated_delivery:
            result["previsao_entrega"] = order.estimated_delivery
        if order.notes:
            result["observacao"] = order.notes
        return result
