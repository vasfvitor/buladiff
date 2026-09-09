"""Roda fetch + segmentação + diff em vários registros e resume o que quebrou.

Uso: uv run scripts/validate.py <registro>...
"""

import json
import sys
from pathlib import Path

from bulario.archive import fetch
from bulario.diff import diff_documents, render_html, summary
from bulario.extract import documents_from_pdf, has_history_table

EXPECT = {
    "vp": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "III"},
    "vps": {str(i) for i in range(1, 11)} | {"III"},
}


def check(pdf: Path, kind: str) -> dict:
    docs = documents_from_pdf(pdf)
    missing = [sorted(EXPECT[kind] - set(d.secoes), key=lambda x: (len(x), x)) for d in docs]
    return {
        "docs": len(docs),
        "tipos": [d.tipo for d in docs],
        "faltando": missing,
        "hist": has_history_table(pdf),
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
        row = {"registro": reg, "nome": prod["nomeProduto"], "empresa": prod["razaoSocial"], "pdfs": {}}
        for v in versions:
            for kind, pdf in v.files.items():
                row["pdfs"][pdf.name] = check(pdf, kind)
        for kind in ("vp", "vps"):
            pair = sorted(v.files[kind] for v in versions if kind in v.files)
            if len(pair) >= 2:
                rows = diff_documents(
                    documents_from_pdf(pair[-2]), documents_from_pdf(pair[-1]), skip_preamble=True
                )
                Path(f"data/{reg}/diff-{kind}.html").write_text(
                    render_html(rows, f"{prod['nomeProduto']} {kind}")
                )
                row[f"diff_{kind}"] = summary(rows)
                print(f"{reg} {kind:3} {row[f'diff_{kind}']}")
        report.append(row)
    Path("data/validate-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
