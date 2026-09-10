"""Extração de texto e segmentação de bulas em documentos e seções.

Pipeline: pdftotext -layout → páginas de linhas → remoção de cabeçalho/rodapé →
divisão em documentos (um PDF pode trazer uma bula por apresentação) → seções da RDC 47.
As funções sobre listas de linhas são puras, para teste sem PDF.
"""

from __future__ import annotations

import collections
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROMAN = {
    "IDENTIFICAÇÃO DO MEDICAMENTO": "I",
    "INFORMAÇÕES AO PACIENTE": "II",
    "INFORMAÇÕES TÉCNICAS AOS PROFISSIONAIS DE SAÚDE": "II",
    "DIZERES LEGAIS": "III",
}
ROMAN_RE = re.compile(r"^(?:[IVX]{1,3}\s*[-–]?\s*)?(" + "|".join(ROMAN) + r")\s*:?$")
NUM_RE = re.compile(r"^(\d{1,2})\s*[.)]\s*([A-ZÇÁÉÍÓÚÂÊÔÃÕ][A-ZÇÁÉÍÓÚÂÊÔÃÕ ,?/()-]{5,})$")
HISTORY_RE = re.compile(r"hist[óo]rico d[aeo]s? altera[çc]", re.I)
PAGE_NUMBER_RE = re.compile(r"[-–]?\s*\d+(\s*(de|/)\s*\d+)?\s*[-–]?")
APRESENTACOES = "APRESENTAÇÕES"
PREAMBLE = "(preâmbulo)"


@dataclass
class Document:
    """Uma bula (paciente ou profissional) de uma apresentação."""

    secoes: dict[str, str] = field(default_factory=dict)
    tipo: str = "?"  # "vp" | "vps" | "?"

    @property
    def label(self) -> str:
        return (self.secoes.get("I") or self.secoes.get(PREAMBLE) or "")[:60]

    @property
    def ordenado(self) -> bool:
        nums = [int(k) for k in self.secoes if k.isdigit()]
        return nums == sorted(nums) and (not nums or nums[0] == 1)

    @property
    def tamanho(self) -> int:
        return sum(len(v) for v in self.secoes.values())

    def to_dict(self) -> dict:
        return {"tipo": self.tipo, "secoes": dict(self.secoes)}

    @classmethod
    def from_dict(cls, d: dict) -> Document:
        return cls(secoes=dict(d["secoes"]), tipo=d.get("tipo", "?"))


def is_heading(line: str) -> bool:
    return bool(
        ROMAN_RE.match(line) or NUM_RE.match(line) or HISTORY_RE.search(line) or line == APRESENTACOES
    )


def pdf_pages(pdf: Path | str) -> list[list[str]]:
    """Páginas como listas de linhas normalizadas (espaços colapsados, vazias removidas)."""
    raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True).stdout
    text = raw.decode("utf-8", "replace")
    return [
        [re.sub(r"\s+", " ", ln).strip() for ln in page.split("\n") if ln.strip()]
        for page in text.split("\f")
        if page.strip()
    ]


def strip_running(pages: list[list[str]], min_pages: int = 3) -> list[list[str]]:
    """Remove cabeçalho/rodapé: linhas (dígitos mascarados) no topo ou pé de >= min_pages páginas,
    e linhas que são só número de página. Títulos de seção nunca são removidos."""

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line)

    seen: collections.Counter[str] = collections.Counter()
    for p in pages:
        seen.update(set(map(key, p[:2] + p[-2:])))
    running = {k for k, n in seen.items() if n >= min_pages}
    out = []
    for p in pages:
        edge = set(p[:2] + p[-2:])
        out.append(
            [
                ln
                for ln in p
                if is_heading(ln) or not ((ln in edge and key(ln) in running) or PAGE_NUMBER_RE.fullmatch(ln))
            ]
        )
    return out


class _Builder:
    """Acumula documentos/seções durante a varredura das linhas."""

    def __init__(self) -> None:
        self.docs: list[tuple[dict[str, list[str]], list[str]]] = []
        self.new_doc()

    def new_doc(self) -> None:
        self.cur: dict[str, list[str]] = {PREAMBLE: []}
        self.tipo = ["?"]
        self.sec: str | None = PREAMBLE
        self.ended = False
        self.docs.append((self.cur, self.tipo))

    def open(self, sec: str) -> None:
        self.sec = sec
        self.cur.setdefault(sec, [])

    def build(self, min_size: int) -> list[Document]:
        result = [Document({k: " ".join(v) for k, v in secs.items()}, t[0]) for secs, t in self.docs]
        return [d for d in result if d.ordenado and d.tamanho > min_size]


def split_documents(lines: list[str], min_size: int = 1000) -> list[Document]:
    """Divide linhas em documentos e seções.

    Regras: 'IDENTIFICAÇÃO DO MEDICAMENTO' (com ou sem 'I -') abre documento; 'APRESENTAÇÕES' depois de
    seções numeradas também (bula sem a linha de identificação); a tabela 'Histórico de alteração' encerra
    o documento e tudo até a próxima bula é ignorado (a tabela cita títulos de seção). Documentos com
    seções fora de ordem ou muito curtos são descartados (fragmentos de capa ou tabela).
    """
    b = _Builder()
    for ln in lines:
        if HISTORY_RE.search(ln):
            b.sec, b.ended = None, True
            continue
        m = ROMAN_RE.match(ln)
        if b.ended:
            if ln == APRESENTACOES or (m and m.group(1) == "IDENTIFICAÇÃO DO MEDICAMENTO"):
                b.new_doc()
            else:
                continue
        if m:
            name = m.group(1)
            if name == "IDENTIFICAÇÃO DO MEDICAMENTO" and b.cur.get("I"):
                b.new_doc()
            if name == "INFORMAÇÕES AO PACIENTE":
                b.tipo[0] = "vp"
            elif name.startswith("INFORMAÇÕES TÉCNICAS"):
                b.tipo[0] = "vps"
            b.open(ROMAN[name])
            continue
        if ln == APRESENTACOES and any(b.cur.get(k) for k in b.cur if k.isdigit()):
            b.new_doc()
            b.open("I")
        m = NUM_RE.match(ln)
        if m:
            if b.tipo[0] == "?":
                b.tipo[0] = "vp" if "?" in ln else "vps"
            b.open(m.group(1))
            continue
        if b.sec is not None:
            b.cur[b.sec].append(ln)
    return b.build(min_size)


def documents_from_pdf(pdf: Path | str) -> list[Document]:
    return split_documents([ln for p in strip_running(pdf_pages(pdf)) for ln in p])


def has_history_table(pdf: Path | str) -> bool:
    return any(HISTORY_RE.search(ln) for p in pdf_pages(pdf) for ln in p)
