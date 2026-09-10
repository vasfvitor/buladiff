"""Roda fetch + segmentação + diff em vários registros e resume o que quebrou.

Uso: uv run scripts/validate.py <registro>...   (sem argumentos: lista curada em registros.txt)
"""

import json
import sys
from pathlib import Path

from bulario.archive import VersionText, fetch, read_curated
from bulario.diff import diff_documents, render_html, summary

EXPECT = {
    "vp": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "III"},
    "vps": {str(i) for i in range(1, 11)} | {"III"},
}


def check(vt: VersionText) -> dict:
    missing = [sorted(EXPECT[vt.tipo] - set(d.secoes), key=lambda x: (len(x), x)) for d in vt.documentos]
    return {
        "docs": len(vt.documentos),
        "tipos": [d.tipo for d in vt.documentos],
        "faltando": missing,
        "hist": bool(vt.historico_tabela),
    }


def main(registros: list[str]) -> None:
    report = []
    for reg in registros:
        try:
            prod, versions = fetch(reg)
        except Exception as e:  # noqa: BLE001 — relatório, não pipeline
            print("ERRO", reg, e)
            report.append({"registro": reg, "erro": repr(e)})
            continue
        row = {"registro": reg, "nome": prod["nomeProduto"], "empresa": prod["razaoSocial"], "versoes": {}}
        loaded = {(v.data, kind): VersionText.load(f) for v in versions for kind, f in v.textos.items()}
        for (data, kind), vt in loaded.items():
            row["versoes"][f"{data}_{vt.expediente}_{kind}"] = check(vt)
        for kind in ("vp", "vps"):
            pair = [vt for (_, k), vt in sorted(loaded.items()) if k == kind]
            if len(pair) >= 2:
                rows = diff_documents(pair[-2].documentos, pair[-1].documentos, skip_preamble=True)
                Path(f"data/{reg}/diff-{kind}.html").write_text(
                    render_html(rows, f"{prod['nomeProduto']} {kind}")
                )
                row[f"diff_{kind}"] = summary(rows)
                detectadas = sorted({r.secao for r in rows if r.alterada and r.secao != "I"})
                declaradas = sorted(pair[-1].declarado)
                row[f"declarado_{kind}"] = declaradas
                bate = (
                    "bate"
                    if set(declaradas) == set(detectadas)
                    else f"declarado={declaradas} detectado={detectadas}"
                )
                print(f"{reg} {kind:3} {row[f'diff_{kind}']}\n        tabela de histórico: {bate}")
        report.append(row)
    Path("data/validate-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or read_curated())
