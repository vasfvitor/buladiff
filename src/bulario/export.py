"""Exporta o arquivo para o site: só JSON, derivado de data/.

<out>/produtos.json            lista de produtos (ordem: última publicação)
<out>/produtos/<registro>.json meta, versões e diffs entre versões consecutivas (por tipo)
<out>/feed.json                cópia do estado do feed (últimas publicações)
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from bulario.archive import VersionText, load_meta, local_versions, registros
from bulario.diff import diff_documents, summary
from bulario.feed import STATE_FILE


def product_entry(registro: str, root: Path) -> dict | None:
    meta = load_meta(registro, root)
    if not meta:
        return None
    prod = meta["produto"]
    versions = local_versions(registro, root)
    textos = {kind: [v for v in versions if kind in v.textos] for kind in ("vp", "vps")}
    return {
        "registro": registro,
        "idProduto": prod["idProduto"],
        "nome": prod["nomeProduto"],
        "empresa": prod["razaoSocial"],
        "cnpj": prod["cnpj"],
        "processo": prod.get("numProcesso", ""),
        "ultima_publicacao": prod["data"][:10],
        "n_versoes": len(versions),
        "tem_diff": any(len(v) >= 2 for v in textos.values()),
    }


def product_detail(registro: str, root: Path) -> dict:
    meta = load_meta(registro, root) or {}
    versions = local_versions(registro, root)
    loaded = {(v.expediente, kind): VersionText.load(f) for v in versions for kind, f in v.textos.items()}
    versoes = []
    for v in versions:
        declarado = {kind: loaded[(v.expediente, kind)].declarado for kind in v.textos}
        situacao = next(
            (
                h["descSituacao"]
                for h in meta.get("historico", {}).get("historico", {}).get("content", [])
                if h["expediente"] == v.expediente
            ),
            "",
        )
        versoes.append(
            {
                "expediente": v.expediente,
                "data": v.data,
                "situacao": situacao,
                "tipos": sorted(v.textos),
                "declarado": declarado,
            }
        )
    diffs = []
    for kind in ("vp", "vps"):
        chain = [v for v in versions if kind in v.textos]
        for old, new in zip(chain, chain[1:], strict=False):
            rows = diff_documents(
                loaded[(old.expediente, kind)].documentos,
                loaded[(new.expediente, kind)].documentos,
                skip_preamble=True,
            )
            diffs.append(
                {
                    "de": old.expediente,
                    "para": new.expediente,
                    "de_data": old.data,
                    "para_data": new.data,
                    "tipo": kind,
                    "resumo": summary(rows),
                    "alteradas": sorted({r.secao for r in rows if r.alterada}, key=lambda s: (len(s), s)),
                    "declarado": loaded[(new.expediente, kind)].declarado,
                    "secoes": [asdict(r) | {"alterada": r.alterada} for r in rows],
                }
            )
    return {"meta": product_entry(registro, root), "versoes": versoes, "diffs": diffs}


def export(root: Path, out: Path, log=print) -> int:
    (out / "produtos").mkdir(parents=True, exist_ok=True)
    produtos = []
    for reg in registros(root):
        entry = product_entry(reg, root)
        if not entry:
            continue
        produtos.append(entry)
        (out / "produtos" / f"{reg}.json").write_text(
            json.dumps(product_detail(reg, root), ensure_ascii=False)
        )
    produtos.sort(key=lambda p: p["ultima_publicacao"], reverse=True)
    (out / "produtos.json").write_text(json.dumps(produtos, ensure_ascii=False, indent=1))
    feed = root / STATE_FILE
    if feed.exists():
        shutil.copy(feed, out / STATE_FILE)
    else:
        (out / STATE_FILE).write_text(json.dumps({"publicacoes": []}))
    log(f"{len(produtos)} produtos exportados para {out}")
    return len(produtos)
