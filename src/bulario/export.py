"""Exporta o arquivo para o site: só JSON, derivado de data/. O site não deriva nada por string.

<out>/produtos.json            lista de produtos (ordem: última publicação), com os slugs dos diffs
<out>/produtos/<registro>.json meta, versões e diffs (por apresentação, com âncoras e "declarada")
<out>/recentes.json            últimos diffs, projetados (para a página inicial)
<out>/feed.json                publicações recentes, com `arquivado` (se o registro está no site)
<out>/catalogo.json            todos os produtos do Bulário (de data/catalogo.json), com `arquivado`
"""

from __future__ import annotations

import json
from pathlib import Path

from bulario import catalogo
from bulario.archive import VersionText, load_meta, local_versions, registros
from bulario.diff import SectionDiff, diff_documents
from bulario.feed import load_state

# ordem canônica das seções (RDC 47): identificação, informações, 1..10, dizeres legais
ORDEM_SECOES = ["I", "II"] + [str(i) for i in range(1, 11)] + ["III"]
RECENTES = 24


def ordenar_secoes(secoes) -> list[str]:
    known = {s: i for i, s in enumerate(ORDEM_SECOES)}
    return sorted(set(secoes), key=lambda s: (known.get(s, len(known)), s))


def secao_id(tipo: str, secao: str, doc: int, principal: bool) -> str:
    """Âncora de uma seção na página do diff. A 1ª apresentação em que a seção mudou (`principal`) fica
    com o id simples — é para onde os chips apontam; as demais recebem -d<n>."""
    base = f"sec-{tipo}-{secao}"
    return base if principal else f"{base}-d{doc}"


def diff_slug(de: str, para: str, tipo: str) -> str:
    return f"{de}-{para}-{tipo}"


def documentos_view(rows: list[SectionDiff], tipo: str, declarado: list[str]) -> list[dict]:
    """Agrupa as linhas do diff por apresentação e carimba âncora e `declarada` em cada seção."""
    primeira: dict[str, int] = {}
    for r in rows:
        if r.alterada and r.secao not in primeira:
            primeira[r.secao] = r.documento
    docs: dict[int, dict] = {}
    for r in rows:
        d = docs.setdefault(r.documento, {"indice": r.documento, "rotulo": r.rotulo, "secoes": []})
        d["secoes"].append(
            {
                "secao": r.secao,
                "alterada": r.alterada,
                "declarada": r.secao in declarado,
                "palavras": r.palavras,
                "ratio": r.ratio,
                "html": r.html,
                "contexto": r.contexto,  # "" quando a seção é curta e o texto completo já é o contexto
                "ancora": secao_id(tipo, r.secao, r.documento, primeira.get(r.secao) == r.documento),
            }
        )
    return list(docs.values())


def product_entry(registro: str, root: Path, diffs: list[dict]) -> dict | None:
    meta = load_meta(registro, root)
    if not meta:
        return None
    prod, det = meta["produto"], meta.get("detalhe") or {}
    return {
        "registro": registro,
        "idProduto": prod["idProduto"],
        "nome": prod["nomeProduto"],
        "empresa": prod["razaoSocial"],
        "cnpj": prod["cnpj"],
        "principio_ativo": det.get("principioAtivo", ""),
        "classes": det.get("classesTerapeuticas", []),
        "categoria": det.get("categoriaRegulatoria", ""),
        "referencia": det.get("medicamentoReferencia", ""),
        "apresentacoes": [
            ap["apresentacao"] for ap in det.get("apresentacoes", []) if ap.get("apresentacao")
        ],
        "ultima_publicacao": prod["data"][:10],
        "n_versoes": len(local_versions(registro, root)),
        "diffs": [d["slug"] for d in diffs],
    }


def product_diffs(registro: str, root: Path) -> tuple[list[dict], list[dict]]:
    """(versoes, diffs). Versões: uma por expediente (a API relista o mesmo expediente em datas
    novas). Diffs: entre versões de conteúdo distinto (mesmo hash de PDF = republicação)."""
    meta = load_meta(registro, root) or {}
    versions = local_versions(registro, root)
    # primeira ocorrência de cada (expediente, tipo): a relistagem do mesmo expediente repete o PDF com
    # data nova, e a data que interessa é a da publicação original
    loaded: dict[tuple[str, str], VersionText] = {}
    for v in versions:
        for kind, f in v.textos.items():
            loaded.setdefault((v.expediente, kind), VersionText.load(f))
    situacoes = {
        h["expediente"]: h.get("descSituacao", "")
        for h in meta.get("historico", {}).get("historico", {}).get("content", [])
    }
    versoes: list[dict] = []
    por_expediente: dict[str, dict] = {}
    hashes: set[str] = set()
    for v in versions:
        if v.expediente in por_expediente:
            por_expediente[v.expediente]["republicada"].append(v.data)
            continue
        textos = [loaded[(v.expediente, kind)] for kind in v.textos]
        versoes.append(
            {
                "expediente": v.expediente,
                "data": v.data,
                "republicada": [],
                "situacao": situacoes.get(v.expediente, ""),
                "declarado": {vt.tipo: vt.declarado for vt in textos},
                # expediente novo com os mesmos PDFs de antes: não gera diff
                "repetida": bool(textos) and all(vt.pdf_sha256 in hashes for vt in textos),
            }
        )
        hashes.update(vt.pdf_sha256 for vt in textos)
        por_expediente[v.expediente] = versoes[-1]
    diffs = []
    for kind in ("vp", "vps"):
        chain: list[VersionText] = []
        vistos: set[str] = set()
        for v in versions:
            if kind in v.textos:
                vt = loaded[(v.expediente, kind)]
                if vt.pdf_sha256 not in vistos:  # PDF já visto = relistagem, não é versão nova
                    vistos.add(vt.pdf_sha256)
                    chain.append(vt)
        for old, new in zip(chain, chain[1:], strict=False):
            rows = diff_documents(old.comparavel(new), new.comparavel(old), skip_preamble=True)
            diffs.append(
                {
                    "slug": diff_slug(old.expediente, new.expediente, kind),
                    "de": old.expediente,
                    "para": new.expediente,
                    "de_data": old.data,
                    "para_data": new.data,
                    "tipo": kind,
                    "alteradas": ordenar_secoes(r.secao for r in rows if r.alterada),
                    "declarado": ordenar_secoes(new.declarado),
                    "marcado": old.marcado and new.marcado,  # parágrafos preservados nas duas versões
                    "documentos": documentos_view(rows, kind, new.declarado),
                }
            )
    return versoes, diffs


def recente(entry: dict, diff: dict) -> dict:
    """Projeção leve de um diff para a página inicial (sem o texto)."""
    return {
        "registro": entry["registro"],
        "nome": entry["nome"],
        "empresa": entry["empresa"],
        "slug": diff["slug"],
        "tipo": diff["tipo"],
        "para_data": diff["para_data"],
        "alteradas": diff["alteradas"],
        "declarado": diff["declarado"],
    }


def export(root: Path, out: Path, log=print) -> int:
    (out / "produtos").mkdir(parents=True, exist_ok=True)
    produtos, recentes = [], []
    for reg in registros(root):
        versoes, diffs = product_diffs(reg, root)
        entry = product_entry(reg, root, diffs)
        if not entry:
            continue
        produtos.append(entry)
        recentes += [recente(entry, d) for d in diffs]
        detail = {"meta": entry, "versoes": versoes, "diffs": diffs}
        (out / "produtos" / f"{reg}.json").write_text(json.dumps(detail, ensure_ascii=False))
    produtos.sort(key=lambda p: p["ultima_publicacao"], reverse=True)
    recentes.sort(key=lambda r: (r["para_data"], r["nome"]), reverse=True)
    (out / "produtos.json").write_text(json.dumps(produtos, ensure_ascii=False, indent=1))
    (out / "recentes.json").write_text(json.dumps(recentes[:RECENTES], ensure_ascii=False, indent=1))
    arquivados = {p["registro"] for p in produtos}
    state = load_state(root)
    feed = {
        "ate": state.get("ate"),
        "publicacoes": [
            {k: p[k] for k in ("registro", "nome", "empresa", "expediente", "data")}
            | {"arquivado": p["registro"] in arquivados}
            for p in state.get("publicacoes", [])
        ],
    }
    (out / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1))
    cat = catalogo.carregar(root)
    catalogo_site = {
        "atualizado": cat["atualizado"],
        "produtos": [p | {"arquivado": p["registro"] in arquivados} for p in cat["produtos"]],
    }
    (out / "catalogo.json").write_text(json.dumps(catalogo_site, ensure_ascii=False))
    log(f"{len(produtos)} produtos exportados para {out}")
    return len(produtos)
