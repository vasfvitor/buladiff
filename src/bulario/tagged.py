"""Blocos de texto pela árvore de estrutura do PDF ("Tagged PDF").

Os PDFs de bula saem do Word ou do Acrobat com marcação: cada parágrafo é um elemento `P`, títulos
são `H1`, tabelas são `Table > TR > TD`, e cabeçalho/rodapé ficam fora da árvore (`Artifact`). Cada
trecho de conteúdo carrega um `MCID`, e a "parent tree" do PDF diz a que elemento cada MCID de cada
página pertence. Daí saem parágrafos inteiros (mesmo atravessando páginas) e tabelas sem o cabeçalho
e o rodapé misturados, em vez das linhas do pdftotext.

O percurso é guiado pelo conteúdo, não pela árvore: para cada página, na ordem em que os trechos
aparecem, sobe-se do elemento dono até o primeiro elemento de bloco (P, H1, LI…; Span, Link, Lbl e
LBody são "em linha" e não quebram o bloco). Trechos consecutivos do mesmo bloco viram um parágrafo.
Descer pela árvore não serve: o Word aninha os itens de lista seguintes dentro do primeiro e omite a
página em elementos herdados, o que embaralha a ordem e troca o texto.

As palavras são montadas a partir dos caracteres de todo o bloco, não trecho a trecho: o Word troca
de trecho no meio de uma palavra ("l" + "osartana", "placebo" + "-controlled"). Separa palavras um
espaço em branco, uma mudança de linha ou um vão maior que `ESPACO` (PDFs sem caractere de espaço).

Tabelas: cada linha (`TR`) vira linhas visuais (palavras agrupadas pela posição vertical e ordenadas
da esquerda para a direita), como o pdftotext faz. O Word costuma gravar uma tabela inteira como uma
linha só com células altas, e parte a linha onde a página quebra; por célula o texto mudaria de lugar
entre versões conforme a quebra, por linha visual não.
"""

from __future__ import annotations

import itertools
from pathlib import Path

LINHA = "TR"
EM_LINHA = {"Span", "Link", "Lbl", "LBody", "Note", "Reference", "Code", "Quote", "Annot", "Form", "Figure"}
ESPACO = 3.0  # pt: vão maior que isso entre caracteres separa palavras (como o x_tolerance do pdfplumber)
MESMA_LINHA = 3.0  # pt: diferença de `top` tolerada entre caracteres da mesma linha

Char = dict  # como em pdfplumber.chars: text, x0, x1, top
Palavra = dict  # text, x0, x1, top
Trecho = tuple[int, list[Char]]  # (mcid, caracteres), na ordem do conteúdo da página
Pagina = tuple[list[Trecho], list]  # (trechos, elementos donos indexados por mcid)


def _nome(el: dict, role_map: dict) -> str:
    """Tipo do elemento, resolvendo o RoleMap (tipos personalizados → padrão)."""
    nome = getattr(el.get("S"), "name", "") or ""
    mapeado = role_map.get(nome)
    return getattr(mapeado, "name", nome) if mapeado is not None else nome


def _cadeia(el, resolve) -> list[dict]:
    """O elemento e seus ancestrais, até a raiz (que não tem /S)."""
    out: list[dict] = []
    while isinstance(el, dict) and "S" in el:
        out.append(el)
        el = resolve(el.get("P"))
    return out


def palavras(chars: list[Char]) -> list[Palavra]:
    """Caracteres (na ordem do conteúdo) → palavras com posição."""
    out: list[Palavra] = []
    cur: Palavra | None = None
    for c in chars:
        if c["text"].isspace():
            cur = None
            continue
        if (
            cur is not None
            and abs(c["top"] - cur["top"]) < MESMA_LINHA
            and -2.0 < c["x0"] - cur["x1"] < ESPACO
        ):
            cur["text"] += c["text"]
            cur["x1"] = max(cur["x1"], c["x1"])
        else:
            cur = {"text": c["text"], "x0": c["x0"], "x1": c["x1"], "top": c["top"]}
            out.append(cur)
    return out


def linhas(ws: list[Palavra]) -> list[str]:
    """Linhas visuais: palavras agrupadas pela posição vertical, cada linha da esquerda para a direita."""
    grupos: list[list[Palavra]] = []
    for w in sorted(ws, key=lambda w: w["top"]):
        if grupos and w["top"] - grupos[-1][0]["top"] < MESMA_LINHA:
            grupos[-1].append(w)
        else:
            grupos.append([w])
    return [" ".join(w["text"] for w in sorted(g, key=lambda w: w["x0"])) for g in grupos]


def blocos(paginas: list[Pagina], role_map: dict, resolve=lambda x: x) -> list[str]:
    """Parágrafos e linhas de tabela a partir dos trechos de cada página e de seus elementos donos."""
    itens: list[tuple[int, int | None, list[Char]]] = []  # (bloco, linha de tabela, caracteres)
    for trechos, donos in paginas:
        for mcid, chars in trechos:
            dono = resolve(donos[mcid]) if 0 <= mcid < len(donos) else None
            if not isinstance(dono, dict):  # conteúdo fora da árvore
                continue
            cadeia = _cadeia(dono, resolve)
            nomes = [_nome(e, role_map) for e in cadeia]
            bloco = next((e for e, n in zip(cadeia, nomes, strict=True) if n not in EM_LINHA), cadeia[-1])
            linha = next((e for e, n in zip(cadeia, nomes, strict=True) if n == LINHA), None)
            itens.append((id(bloco), id(linha) if linha else None, chars))
    out: list[str] = []
    for _, grupo_ in itertools.groupby(itens, key=lambda it: it[1] or it[0]):
        grupo = list(grupo_)
        ws = palavras([c for *_, cs in grupo for c in cs])
        textos = linhas(ws) if grupo[0][1] is not None else [" ".join(w["text"] for w in ws)]
        out += [t for t in textos if t]
    return out


def tagged_blocks(pdf: Path | str) -> list[str] | None:
    """Parágrafos, títulos e linhas de tabela de um PDF marcado, na ordem de leitura.
    `None` se o PDF não é marcado (sem árvore de estrutura ou com `MarkInfo/Marked` falso)."""
    import pdfplumber
    from pdfminer.data_structures import NumberTree
    from pdfminer.pdftypes import resolve1

    with pdfplumber.open(str(pdf)) as doc:
        catalog = doc.doc.catalog
        root = resolve1(catalog.get("StructTreeRoot"))
        marcado = (resolve1(catalog.get("MarkInfo")) or {}).get("Marked", False)
        if not root or not marcado or "ParentTree" not in root:  # árvore com Marked falso não presta
            return None
        role_map = {k: resolve1(v) for k, v in (resolve1(root.get("RoleMap")) or {}).items()}
        donos_por_chave = dict(NumberTree(resolve1(root["ParentTree"])).values)
        paginas: list[Pagina] = []
        for page in doc.pages:
            chave = resolve1(page.page_obj.attrs.get("StructParents"))
            donos = resolve1(donos_por_chave.get(chave)) if chave is not None else None
            if not isinstance(donos, list):
                continue
            por_mcid: dict[int, list[Char]] = {}
            for c in page.chars:  # na ordem do conteúdo
                if c.get("mcid") is not None:
                    por_mcid.setdefault(c["mcid"], []).append(c)
            paginas.append((list(por_mcid.items()), donos))
        return blocos(paginas, role_map, resolve1) or None
