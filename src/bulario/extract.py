"""Extração de texto e segmentação de bulas em documentos e seções.

Pipeline: blocos de texto (parágrafos pela árvore de estrutura do PDF, módulo `tagged`; ou, se o PDF
não é marcado, linhas do pdftotext -layout sem cabeçalho/rodapé) → divisão em documentos (um PDF pode
trazer uma bula por apresentação) → seções da RDC 47. As funções sobre listas de blocos são puras,
para teste sem PDF.
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
        """Rótulo curto da apresentação: o texto após 'APRESENTAÇÕES' (ou o início da identificação)."""
        texto = self.secoes.get("I") or self.secoes.get(PREAMBLE) or ""
        _, sep, resto = texto.partition(APRESENTACOES)
        base = resto if sep else texto
        base = re.split(r"\b(USO |COMPOSIÇÃO)", base, maxsplit=1)[0]
        base = re.sub(r"\s+", " ", base).strip(" :.-")
        if len(base) > 70:  # corta em limite de palavra, sem deixar pontuação pendurada
            base = base[:70].rsplit(" ", 1)[0].rstrip(" ,;:(-") + "…"
        return base

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


LOWER_RE = re.compile(r"[a-zçáéíóúâêôãõ]")


def split_heading(block: str) -> list[str]:
    """Separa um título colado ao texto que o segue ("1. INDICAÇÕES Hipertensão" → duas partes).
    O título é o trecho em maiúsculas até a primeira palavra com minúscula; só vale se for um título."""
    if is_heading(block):
        return [block]
    words = block.split(" ")
    for i, w in enumerate(words):
        if LOWER_RE.search(w):
            head = " ".join(words[:i]).rstrip(" -–:")
            if i and (NUM_RE.match(head) or ROMAN_RE.match(head)):
                return [head, block[len(head) :].strip()]
            break
    return [block]


def pdftotext(pdf: Path | str) -> list[str]:
    """Texto bruto de cada página (`pdftotext -layout`), na numeração do PDF (páginas vazias incluídas)."""
    raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True).stdout
    pages = raw.decode("utf-8", "replace").split("\f")
    return pages[:-1]  # cada página termina em \f; o que sobra depois do último não é página


def pdf_pages(pdf: Path | str) -> list[list[str]]:
    """Páginas como listas de linhas normalizadas (espaços colapsados, vazias removidas)."""
    return [
        [re.sub(r"\s+", " ", ln).strip() for ln in page.split("\n") if ln.strip()]
        for page in pdftotext(pdf)
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
        self.titulo = False  # a linha anterior era um título numerado
        self.docs.append((self.cur, self.tipo))

    def open(self, sec: str) -> None:
        self.sec = sec
        self.cur.setdefault(sec, [])

    def build(self, min_size: int, sep: str) -> list[Document]:
        result = [Document({k: sep.join(v) for k, v in secs.items()}, t[0]) for secs, t in self.docs]
        return [d for d in result if d.ordenado and d.tamanho > min_size]


PARAGRAFO = "\n\n"  # separador de parágrafos dentro de uma seção (blocos de PDF marcado)


def split_documents(lines: list[str], min_size: int = 1000, sep: str = " ") -> list[Document]:
    """Divide linhas (ou blocos: `sep=PARAGRAFO`) em documentos e seções.

    Regras: 'IDENTIFICAÇÃO DO MEDICAMENTO' (com ou sem 'I -') abre documento; 'APRESENTAÇÕES' depois de
    seções numeradas também (bula sem a linha de identificação); a tabela 'Histórico de alteração' encerra
    o documento e tudo até a próxima bula é ignorado (a tabela cita títulos de seção). Documentos com
    seções fora de ordem ou muito curtos são descartados (fragmentos de capa ou tabela).
    """
    b = _Builder()
    for ln in (part for block in lines for part in split_heading(block)):
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
            b.titulo = True
            continue
        if b.titulo and len(ln) <= 40 and not LOWER_RE.search(ln):
            continue  # resto de um título que quebrou de linha ("…ESQUECER DE USAR ESTE" / "MEDICAMENTO?")
        b.titulo = False
        if b.sec is not None:
            b.cur[b.sec].append(ln)
    return b.build(min_size, sep)


def documents_from_lines(pages: list[list[str]]) -> list[Document]:
    """Caminho por linhas: páginas do `pdf_pages` sem cabeçalho/rodapé; sem parágrafos."""
    return split_documents([ln for p in strip_running(pages) for ln in p])


def extract_documents(
    pdf: Path | str, pages: list[list[str]] | None = None
) -> tuple[list[Document], list[Document]]:
    """(documentos pela árvore de estrutura, documentos por linhas). A primeira lista fica vazia se o
    PDF não é marcado ou se a árvore não rende nenhuma bula; a segunda existe sempre, para comparar
    com versões sem marcação. `pages` evita rodar o pdftotext de novo quando quem chama já o rodou."""
    from bulario.tagged import tagged_blocks

    blocks = tagged_blocks(pdf)
    linhas = documents_from_lines(pages if pages is not None else pdf_pages(pdf))
    return (split_documents(blocks, sep=PARAGRAFO) if blocks else []), linhas


def documents_from_pdf(pdf: Path | str) -> list[Document]:
    marcados, linhas = extract_documents(pdf)
    return marcados or linhas
