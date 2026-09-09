"""Leitura da tabela "Histórico de Alteração da Bula" que a maioria das empresas inclui no fim do PDF.

A tabela tem 10 colunas em três grupos (submissão eletrônica, petição que altera a bula, alterações):
data e nº do expediente, assunto, data/nº/assunto da petição, data de aprovação, itens de bula alterados,
versões (VP/VPS) e apresentações. Linhas de continuação (sem data) pertencem à linha anterior.
Requer o extra `tables` (pdfplumber).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bulario.extract import HISTORY_RE

COLUMNS = (
    "data",
    "expediente",
    "assunto",
    "pet_data",
    "pet_expediente",
    "pet_assunto",
    "aprovacao",
    "itens",
    "versoes",
    "apresentacoes",
)
DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")
SECTION_RE = re.compile(r"\b(\d{1,2})\s*[.)]|\b(III|II|I)\s*[-–]|(DIZERES LEGAIS)", re.I)


@dataclass
class HistoryEntry:
    data: str
    expediente: str
    assunto: str
    itens: str
    versoes: str
    apresentacoes: str
    aprovacao: str = ""

    @property
    def secoes(self) -> list[str]:
        """Identificadores de seção citados em `itens` ("4", "5", "III"...), na ordem, sem repetição."""
        found = [a or b.upper() or ("III" if c else "") for a, b, c in SECTION_RE.findall(self.itens)]
        return list(dict.fromkeys(f for f in found if f))


@dataclass
class History:
    entries: list[HistoryEntry] = field(default_factory=list)

    @property
    def latest(self) -> HistoryEntry | None:
        """Última linha: a submissão que gerou este PDF (em geral ainda sem nº de expediente)."""
        return self.entries[-1] if self.entries else None

    def by_expediente(self, expediente: str) -> HistoryEntry | None:
        """Entrada cujo expediente bate com o da API, comparando só dígitos ("0121761/25-8" == "0121761258")."""
        digits = re.sub(r"\D", "", expediente)
        for e in self.entries:
            if digits and re.sub(r"\D", "", e.expediente) == digits:
                return e
        return None


def _clean(cell: str | None) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def normalize_rows(rows: list[list[str | None]]) -> list[HistoryEntry]:
    """Linhas brutas da tabela (10 colunas) → entradas; junta continuações e pula cabeçalhos."""
    entries: list[HistoryEntry] = []
    for raw in rows:
        cells = [_clean(c) for c in raw]
        if len(cells) < 10:
            cells += [""] * (10 - len(cells))
        row = dict(zip(COLUMNS, cells, strict=False))
        if not any(cells) or row["data"].lower().startswith("data") or row["data"].startswith("Dados"):
            continue
        is_new = bool(DATE_RE.search(row["data"]) or DATE_RE.search(row["expediente"]) or row["assunto"])
        if is_new or not entries:
            entries.append(
                HistoryEntry(
                    data=row["data"],
                    expediente=row["expediente"],
                    assunto=row["assunto"],
                    itens=row["itens"],
                    versoes=row["versoes"],
                    apresentacoes=row["apresentacoes"],
                    aprovacao=row["aprovacao"],
                )
            )
        else:  # continuação: só acrescenta o que veio preenchido
            e = entries[-1]
            e.itens = f"{e.itens} {row['itens']}".strip()
            e.versoes = f"{e.versoes} {row['versoes']}".strip()
            e.apresentacoes = f"{e.apresentacoes} {row['apresentacoes']}".strip()
    return entries


def read_history(pdf: Path | str) -> History:
    """Extrai a tabela de histórico com pdfplumber (páginas a partir do título, até o fim do documento)."""
    import pdfplumber  # extra `tables`

    rows: list[list[str | None]] = []
    with pdfplumber.open(str(pdf)) as doc:
        in_table = False
        for page in doc.pages:
            text = page.extract_text() or ""
            if HISTORY_RE.search(text):
                in_table = True
            if not in_table:
                continue
            tables = page.extract_tables()
            if not tables:
                in_table = False  # tabela acabou; pode vir outra bula depois
                continue
            for t in tables:
                rows.extend(t)
    return History(normalize_rows(rows))
