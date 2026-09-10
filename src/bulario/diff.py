"""Diff de bulas: pareamento de documentos por semelhança e diff por palavra dentro de cada seção."""

from __future__ import annotations

import difflib
import html
from dataclasses import dataclass

from bulario.extract import PREAMBLE, Document


@dataclass
class SectionDiff:
    documento: int  # índice (1..n) da bula/apresentação dentro do PDF
    rotulo: str  # rótulo curto da apresentação (Document.label)
    secao: str
    palavras: int  # palavras removidas + inseridas
    ratio: float  # semelhança 0..1
    html: str  # texto com <del>/<ins>

    @property
    def alterada(self) -> bool:
        return self.palavras > 0


def word_diff(a: str, b: str) -> tuple[str, int, float]:
    aw, bw = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, aw, bw, autojunk=False)
    out, changed = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(html.escape(" ".join(aw[i1:i2])))
            continue
        changed += (i2 - i1) + (j2 - j1)
        if i2 > i1:
            out.append("<del>" + html.escape(" ".join(aw[i1:i2])) + "</del>")
        if j2 > j1:
            out.append("<ins>" + html.escape(" ".join(bw[j1:j2])) + "</ins>")
    return " ".join(out), changed, sm.ratio()


def pair_documents(da: list[Document], db: list[Document]) -> list[tuple[int | None, int | None]]:
    """Pareia documentos pela semelhança do texto (a ordem das apresentações muda entre versões)."""

    def blob(d: Document) -> str:
        return " ".join(d.secoes.values())[:20000]

    scores = sorted(
        (
            (difflib.SequenceMatcher(None, blob(a), blob(b), autojunk=True).quick_ratio(), i, j)
            for i, a in enumerate(da)
            for j, b in enumerate(db)
        ),
        reverse=True,
    )
    pairs: list[tuple[int | None, int | None]] = []
    used_a: set[int] = set()
    used_b: set[int] = set()
    for _, i, j in scores:
        if i not in used_a and j not in used_b:
            pairs.append((i, j))
            used_a.add(i)
            used_b.add(j)
    pairs += [(i, None) for i in range(len(da)) if i not in used_a]
    pairs += [(None, j) for j in range(len(db)) if j not in used_b]
    return pairs


def diff_documents(da: list[Document], db: list[Document], skip_preamble: bool = False) -> list[SectionDiff]:
    """Uma linha por seção de cada par de documentos; `documento` numera os pares de 1 em diante."""
    rows = []
    for n, (i, j) in enumerate(pair_documents(da, db), 1):
        a = da[i].secoes if i is not None else {}
        b = db[j].secoes if j is not None else {}
        rotulo = (da[i] if i is not None else db[j]).label
        for k in dict.fromkeys(list(a) + list(b)):
            if skip_preamble and k == PREAMBLE:
                continue
            if a.get(k, "") == b.get(k, ""):
                rows.append(SectionDiff(n, rotulo, k, 0, 1.0, ""))
            else:
                h, ch, r = word_diff(a.get(k, ""), b.get(k, ""))
                rows.append(SectionDiff(n, rotulo, k, ch, r, h))
    return rows


def summary(rows: list[SectionDiff]) -> str:
    """Resumo curto: seções alteradas com contagem de palavras, por apresentação (se houver mais de uma)."""
    docs = dict.fromkeys((r.documento, r.rotulo) for r in rows)
    out = []
    for n, rotulo in docs:
        changed = [f"{r.secao}({r.palavras})" for r in rows if r.documento == n and r.alterada]
        prefix = f"[{n}: {rotulo}] " if len(docs) > 1 else ""
        out.append(prefix + (" ".join(changed) or "sem alterações"))
    return "\n".join(out)


CSS = (
    "body{font:15px/1.5 system-ui;max-width:900px;margin:2em auto;padding:0 1em}"
    "del{background:#fdd}ins{background:#dfd;text-decoration:none}"
    "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 8px}"
    ".alterada{color:#b00;font-weight:bold}small{color:#666;font-weight:normal}"
)


def render_html(rows: list[SectionDiff], title: str, subtitle: str = "") -> str:
    multi = len({r.documento for r in rows}) > 1

    def name(r: SectionDiff) -> str:
        return html.escape(f"[{r.documento}: {r.rotulo}] {r.secao}" if multi else r.secao)

    table = "".join(
        f"<tr><td>{name(r)}</td><td class={'alterada' if r.alterada else 'igual'}>"
        f"{'alterada' if r.alterada else 'igual'}</td><td>{r.palavras}</td><td>{r.ratio:.0%}</td></tr>"
        for r in rows
    )
    body = "".join(
        f"<h2>{name(r)} <small>{r.palavras} palavras, similaridade {r.ratio:.0%}</small></h2><p>{r.html}</p>"
        for r in rows
        if r.alterada
    )
    return (
        f"<meta charset=utf-8><title>bula-diff</title><style>{CSS}</style>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>"
        "<table><tr><th>Seção</th><th>Status</th><th>Palavras alteradas</th><th>Similaridade</th></tr>"
        f"{table}</table>{body}"
    )
