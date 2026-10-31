# Preço, promoção encerrada e formas de pagamento

**Objetivo do cenário:** Consulta de preço, transparência sobre promoção que acabou (7.3), PIX e parcelas pela política 3.1.

*Relógio da loja congelado em 2026-11-03T15:40:00 (America/Campo_Grande) · modelo `sabia-4`*

**Cliente:** Quanto custa o Takamine GD20? Vi que ele tava com desconto

<details><summary>Ferramentas chamadas</summary>

- `get_product({"name": "Takamine GD20"})`
  → `{"encontrado": true, "produto": {"id": 95, "nome": "Takamine GD20 Dreadnought Natural", "categoria": "Violões", "situacao": "disponível no catálogo", "em_estoque": 5, "disponivel_para_venda": true, "preco_tabela": 2199.0, "preco_no_pix": 2089.05, "promocoes_encerradas": ["Oferta Especial"], "descricao": "Violão dreadnought Takamine com tampo sólido em cedro. Excelente para fingerstyle com timbre quente e definido.", "especificacoes": {"top": "Cedro Sólido", "back_sides": "Sapele", "neck": "Mogno", "strings": "steel", "scale": "650mm", "electronics": "no", "color": "Natural"}}}`

</details>

**Lia:** O Takamine GD20 Dreadnought Natural está R$ 2.199,00. No PIX, sai por R$ 2.089,05 (5% de desconto).

A promoção que você viu (“Oferta Especial”) já encerrou, então o preço atual é esse mesmo. 

Quer que eu simule alguma forma de pagamento ou te mostre outras opções de violão?

**Cliente:** Entendi. E se eu pagar no pix fica quanto? Ou dá pra parcelar em quantas vezes?

<details><summary>Ferramentas chamadas</summary>

- `simulate_payment({"product_name": "Takamine GD20 Dreadnought Natural"})`
  → `{"produto": "Takamine GD20 Dreadnought Natural", "quantidade": 1, "disponivel_para_venda": true, "valor": 2199.0, "cartao_credito": {"max_parcelas_sem_juros": 12, "exemplos": [{"parcelas": 1, "valor_parcela": 2199.0}, {"parcelas": 2, "valor_parcela": 1099.5}, {"parcelas": 3, "valor_parcela": 733.0}, {"parcelas": 6, "valor_parcela": 366.5}, {"parcelas": 10, "valor_parcela": 219.9}, {"parcelas": 12, "valor_parcela": 183.25}]}, "debito_e_boleto": {"valor": 2199.0, "observacao": "boleto compensa em até 3 dias úteis"}, "combinar_formas": true, "pix": {"valor": 2089.05, "desconto": "5%"}}`

</details>

**Lia:** No PIX, o Takamine GD20 fica R$ 2.089,05 (5% de desconto).

No cartão de crédito, dá pra parcelar em até 12 vezes sem juros:
- 2x de R$ 1.099,50
- 3x de R$ 733,00
- 6x de R$ 366,50
- 10x de R$ 219,90
- 12x de R$ 183,25

Também dá pra combinar formas de pagamento, se quiser. Precisa de mais alguma coisa?
