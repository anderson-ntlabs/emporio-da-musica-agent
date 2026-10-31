"""Policy manual: PDF -> numbered sections the agent can read on demand.

Why not embeddings: the manual has 10 numbered sections (~2.5k tokens). A
vector index would add an embedding model and a chunking strategy to solve a
problem the document's own structure already solves. The agent sees the table
of contents in its system prompt and reads whole sections through a tool, so
it never gets half a rule (e.g. the 3.1 installment tiers split across chunks).

Extraction note: pypdf's default mode returns one word per line for this file
(it was exported from Google Docs); the layout mode keeps lines and tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

from .store import DATA_DIR, normalize

POLICY_PDF = DATA_DIR / "politicas_da_loja.pdf"

_NOISE = (
    re.compile(r"^Empório da Música Manual de Políticas e Procedimentos$"),
    re.compile(r"^Página \d+$"),
)
_SECTION = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
_SUBSECTION = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\S.*)$")

# Inconsistencies found in the manual, resolved once here and disclosed in the
# README, so the agent does not improvise a different answer each time.
CURATION_NOTES = {
    "1": "Nota de curadoria: o e-mail aparece como 'contato@empóriodamusica.com.br' na tabela 1.2, "
         "com acento, o que não é um endereço válido. Use contato@emporiodamusica.com.br (capa do manual).",
    "7": "Nota de curadoria: a seção 7 cita o WhatsApp (67) 3321-4500, mas a capa e a tabela 1.2 dão "
         "(67) 3341-4444 como telefone e WhatsApp. Informe o (67) 3341-4444 e, se perguntarem pelo "
         "WhatsApp, diga que é o mesmo número da loja.",
    "3": "Nota de curadoria: a tabela fala em parcela mínima de R$ 100,00 no crédito, mas a 3.1 detalha "
         "faixas (até 3x: mínimo R$ 50; 4x-6x: R$ 80; 7x-12x: R$ 100). Vale a regra detalhada da 3.1; "
         "use a ferramenta simular_pagamento em vez de calcular.",
}


@dataclass
class Section:
    number: str
    title: str
    lines: list[str] = field(default_factory=list)
    subsections: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        body = "\n".join(self.lines).strip()
        note = CURATION_NOTES.get(self.number)
        return f"{self.number}. {self.title}\n{body}" + (f"\n\n{note}" if note else "")


def _clean_line(line: str) -> str:
    line = line.replace("​", "").strip()
    # table columns are separated by long runs of spaces in layout mode
    line = re.sub(r"\s{3,}", " | ", line)
    line = re.sub(r"\s+", " ", line)
    return line.replace("• | ", "• ")


def parse_policy(pdf_path: Path = POLICY_PDF) -> tuple[str, list[Section]]:
    reader = PdfReader(pdf_path)
    raw = "\n".join(page.extract_text(extraction_mode="layout") for page in reader.pages)
    cover: list[str] = []
    sections: list[Section] = []
    for raw_line in raw.splitlines():
        line = _clean_line(raw_line)
        if not line or any(p.match(line) for p in _NOISE):
            continue
        sub = _SUBSECTION.match(line)
        top = _SECTION.match(line)
        if top and not sub and len(top.group(2)) < 60 and "|" not in line:
            sections.append(Section(number=top.group(1), title=top.group(2)))
            continue
        if not sections:
            cover.append(line)
            continue
        if sub:
            sections[-1].subsections.append(f"{sub.group(1)} {sub.group(2)}")
            line = f"\n{sub.group(1)} {sub.group(2)}"
        sections[-1].lines.append(line)
    return "\n".join(cover), sections


class PolicyBook:
    def __init__(self, pdf_path: Path = POLICY_PDF) -> None:
        self.cover, sections = parse_policy(pdf_path)
        self.sections = {s.number: s for s in sections}

    def table_of_contents(self) -> str:
        lines = []
        for s in self.sections.values():
            subs = f" ({'; '.join(s.subsections)})" if s.subsections else ""
            lines.append(f"- {s.number}. {s.title}{subs}")
        return "\n".join(lines)

    def read(self, section: str) -> dict:
        key = section.strip().split(".")[0].split()[0] if section.strip() else ""
        if key in self.sections:
            return {"secao": key, "conteudo": self.sections[key].text}
        target = normalize(section)
        for s in self.sections.values():
            haystack = normalize(f"{s.title} {' '.join(s.subsections)}")
            if target and target in haystack:
                return {"secao": s.number, "conteudo": s.text}
        return {"erro": f"Seção '{section}' não encontrada.", "secoes": self.table_of_contents()}


@lru_cache(maxsize=1)
def default_policy_book() -> PolicyBook:
    return PolicyBook()
