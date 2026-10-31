from emporio_agent.policies import default_policy_book


def test_all_ten_sections_parsed():
    book = default_policy_book()
    assert list(book.sections) == [str(n) for n in range(1, 11)]
    assert book.sections["4"].title == "Política de Trocas e Devoluções"
    assert "4.1 Direito de Arrependimento (Compras Online)" in book.sections["4"].subsections


def test_page_headers_and_footers_removed():
    text = "\n".join(s.text for s in default_policy_book().sections.values())
    assert "Página " not in text
    assert "Manual de Políticas e Procedimentos" not in text


def test_read_by_number_and_by_title():
    book = default_policy_book()
    assert book.read("4")["secao"] == "4"
    assert book.read("4.1")["secao"] == "4"
    assert book.read("garantia")["secao"] == "8"
    assert book.read("Código de Rastreamento")["secao"] == "5"
    assert "erro" in book.read("cashback")


def test_rules_survive_extraction():
    book = default_policy_book()
    assert "7 (sete) dias corridos" in book.read("4")["conteudo"]
    assert "Sábado | 09:00 às 13:00" in book.read("2")["conteudo"]
    assert "não se aplica sobre" in book.read("6")["conteudo"]


def test_curation_notes_attached():
    book = default_policy_book()
    assert "3341-4444" in book.read("7")["conteudo"].split("Nota de curadoria")[1]
    assert "Nota de curadoria" in book.read("3")["conteudo"]
