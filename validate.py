"""Valida segmentação e diff em vários registros. Uso: python3 validate.py <registro>..."""
import sys, json, pathlib, traceback
import bulario

EXPECT_VP = {"1","2","3","4","5","6","7","8","9","I","II","III"}
EXPECT_VPS = {"1","2","3","4","5","6","7","8","9","10","I","II","III"}

def check(pdf, kind):
    secs = bulario.sections(pdf)
    nums = {k.split(" ")[0] for k in secs}
    exp = EXPECT_VP if kind == "vp" else EXPECT_VPS
    missing = sorted(exp - nums, key=lambda x: (len(x), x))
    extra = sorted(nums - exp - {"(preâmbulo)"})
    empty = [k for k, v in secs.items() if not v and not k.startswith("II ")]
    return dict(n=len(secs), missing=missing, extra=extra, empty=empty, hist=bulario.has_history_table(pdf),
                chars=sum(len(v) for v in secs.values()))

report = []
for reg in sys.argv[1:]:
    try:
        prod, versions, files = bulario.fetch(reg)
    except Exception as e:
        report.append(dict(registro=reg, erro=repr(e))); print("ERRO", reg, e); continue
    row = dict(registro=reg, nome=prod["nomeProduto"], empresa=prod["razaoSocial"][:35], versoes=len(json.load(open(f"data/{reg}/historico.json"))["historico"]["content"]), pdfs={})
    for f in files:
        kind = f.stem.split("_")[-1]
        try:
            row["pdfs"][f.name] = check(f, kind)
        except Exception as e:
            row["pdfs"][f.name] = dict(erro=repr(e))
    for kind in ("vp", "vps"):
        pair = sorted(f for f in files if f.stem.endswith("_" + kind))
        if len(pair) == 2:
            rows = bulario.diff(pair[0], pair[1])
            changed = [f"{r['secao'].split(' ')[0]}({r['palavras']})" for r in rows if r["status"] == "alterada"]
            row[f"diff_{kind}"] = changed
            pathlib.Path(f"data/{reg}/diff-{kind}.html").write_text(bulario.diff_html(rows, f"{prod['nomeProduto']} — {kind.upper()}", f"{pair[0].name} → {pair[1].name}"))
    report.append(row)
    print(json.dumps(row, ensure_ascii=False, indent=1))
pathlib.Path("data/validate-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
