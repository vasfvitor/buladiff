"""bulario — arquivo e diff de versões de bula do Bulário Eletrônico da ANVISA.

  python3 bulario.py fetch <numeroRegistro> [--all]     baixa versões (padrão: 2 mais recentes)
  python3 bulario.py search <nome>                      lista produtos (registro, empresa, nº de versões)
  python3 bulario.py diff <a.pdf> <b.pdf> [saida.html]  diff por seção
  python3 bulario.py sections <a.pdf>                   mostra a segmentação (debug)

API não documentada (a que a página consultas.anvisa.gov.br usa). Ids de PDF são JWT com 5 min de validade.
"""
import difflib, html, json, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request

BASE = "https://consultas.anvisa.gov.br/api/consulta"
HDR = {
    "Authorization": "Guest",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://consultas.anvisa.gov.br/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
}

# ---------- API ----------
def get(url, binary=False):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    time.sleep(1)
    return data if binary else json.loads(data)

def search(**filtro):
    q = urllib.parse.urlencode({"count": 50, "page": 1, **{f"filter[{k}]": v for k, v in filtro.items()}})
    return get(f"{BASE}/bulario?{q}")["content"]

def historico(id_produto, all_pages=False):
    """GET /bulario/{idProduto}: {registroProduto, nomeProduto, bulaAtual, historico:{content[], totalPages...}} — 10 por página (?page=N)."""
    h = get(f"{BASE}/bulario/{id_produto}")
    if all_pages:
        for page in range(2, h["historico"]["totalPages"] + 1):
            h["historico"]["content"] += get(f"{BASE}/bulario/{id_produto}?page={page}")["historico"]["content"]
    return h

def fetch(registro, all_versions=False, out_root="data"):
    prods = search(numeroRegistro=registro)
    if not prods:
        sys.exit(f"registro {registro} não encontrado")
    prod = prods[0]
    out = pathlib.Path(out_root) / registro
    out.mkdir(parents=True, exist_ok=True)
    hist = historico(prod["idProduto"], all_pages=all_versions)
    (out / "historico.json").write_text(json.dumps(hist, ensure_ascii=False, indent=1))
    versions = hist["historico"]["content"]
    versions.sort(key=lambda v: v["dataPublicacao"], reverse=True)
    if not all_versions:
        versions = versions[:2]
    print(f"{prod['nomeProduto']} — {prod['razaoSocial']} — {hist['historico']['totalElements']} versões")
    files = []
    for v in versions:
        for kind, key in (("vp", "idBulaPaciente"), ("vps", "idBulaProfissional")):
            if not v.get(key):
                print(f"  {v['expediente']} sem {kind}"); continue
            dest = out / f"{v['dataPublicacao'][:10]}_{v['expediente']}_{kind}.pdf"
            if not dest.exists():
                dest.write_bytes(get(f"{BASE}/medicamentos/arquivo/bula/parecer/{v[key]}/?Authorization=", binary=True))
                print(f"  {dest.name}  {dest.stat().st_size // 1024} KB")
            files.append(dest)
    return prod, versions, files

# ---------- texto ----------
ROMAN = {"IDENTIFICAÇÃO DO MEDICAMENTO": "I", "INFORMAÇÕES AO PACIENTE": "II",
         "INFORMAÇÕES TÉCNICAS AOS PROFISSIONAIS DE SAÚDE": "II", "DIZERES LEGAIS": "III"}
ROMAN_RE = re.compile(r"^(?:[IVX]{1,3}\s*[-–]?\s*)?(" + "|".join(ROMAN) + r")\s*:?$")
NUM_RE = re.compile(r"^(\d{1,2})\s*[.)]\s*([A-ZÇÁÉÍÓÚÂÊÔÃÕ][A-ZÇÁÉÍÓÚÂÊÔÃÕ ,?/()-]{5,})$")
STOP = re.compile(r"Hist[óo]rico d[aeo]s? altera[çc]", re.I)

def _norm(line):
    return re.sub(r"\s+", " ", line).strip()

def pages(pdf):
    raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")
    return [[_norm(l) for l in p.split("\n") if l.strip()] for p in raw.split("\f") if p.strip()]

def strip_running(pgs, min_pages=3):
    """Remove cabeçalho/rodapé: linhas (com dígitos mascarados) que aparecem no topo ou no pé de >= min_pages páginas."""
    import collections
    key = lambda l: re.sub(r"\d+", "#", l)
    seen = collections.Counter()
    for p in pgs:
        for l in set(map(key, p[:2] + p[-2:])):
            seen[l] += 1
    running = {k for k, n in seen.items() if n >= min_pages}
    out = []
    for p in pgs:
        edge = set(p[:2] + p[-2:])
        keep = lambda l: ROMAN_RE.match(l) or NUM_RE.match(l) or STOP.search(l) or l == "APRESENTAÇÕES"
        out.append([l for l in p if keep(l) or not ((l in edge and key(l) in running) or re.fullmatch(r"[-–]?\s*\d+(\s*(de|/)\s*\d+)?\s*[-–]?", l))])
    return out

def lines(pdf):
    return [l for p in strip_running(pages(pdf)) for l in p]

def documents(pdf):
    """Um PDF pode trazer várias bulas (uma por apresentação). Divide em documentos e cada um em seções.
    Retorna lista de dicts {secoes: {id: texto}, tipo: 'vp'|'vps'|'?'}. Cabeçalhos aceitos: 'I - X', 'X' (I/II/III
    por nome), 'N. X' / 'N) X' em caixa alta. Para no Histórico de Alteração."""
    docs, cur, sec, ended = [], None, None, False
    def new_doc():
        nonlocal cur, sec, ended
        cur = {"secoes": {"(preâmbulo)": []}, "tipo": "?"}; sec = "(preâmbulo)"; ended = False; docs.append(cur)
    new_doc()
    for l in lines(pdf):
        if STOP.search(l):
            sec = None; ended = True; continue   # tabela de histórico: fim da bula; ignora até a próxima bula
        if ended:   # depois da tabela só reabre em nova bula (a tabela cita "9. REAÇÕES ADVERSAS" etc.)
            if l == "APRESENTAÇÕES" or (ROMAN_RE.match(l) and ROMAN_RE.match(l).group(1) == "IDENTIFICAÇÃO DO MEDICAMENTO"):
                new_doc()
            else:
                continue
        m = ROMAN_RE.match(l)
        if m:
            name = m.group(1)
            if name == "IDENTIFICAÇÃO DO MEDICAMENTO" and cur["secoes"].get("I"):
                new_doc()
            if name == "INFORMAÇÕES AO PACIENTE": cur["tipo"] = "vp"
            if name.startswith("INFORMAÇÕES TÉCNICAS"): cur["tipo"] = "vps"
            sec = ROMAN[name]; cur["secoes"].setdefault(sec, []); continue
        if l == "APRESENTAÇÕES" and any(cur["secoes"].get(k) for k in cur["secoes"] if k[0].isdigit()):
            new_doc(); sec = "I"; cur["secoes"]["I"] = []   # bula sem 'IDENTIFICAÇÃO' explícita: nova apresentação
        m = NUM_RE.match(l)
        if m:
            sec = m.group(1)
            if cur["tipo"] == "?":
                cur["tipo"] = "vp" if "?" in l else "vps"
            cur["secoes"].setdefault(sec, []); continue
        if sec is not None:
            cur["secoes"][sec].append(l)
    for d in docs:
        d["secoes"] = {k: " ".join(v) for k, v in d["secoes"].items()}
        nums = [int(k) for k in d["secoes"] if k.isdigit()]
        d["ordenado"] = nums == sorted(nums) and (not nums or nums[0] == 1)
    # descarta fragmentos (tabela de histórico que cita títulos de seção, restos de capa)
    return [d for d in docs if d["ordenado"] and sum(len(v) for v in d["secoes"].values()) > 1000]

def sections(pdf):
    """Compat: seções do primeiro documento."""
    return documents(pdf)[0]["secoes"]

def has_history_table(pdf):
    return any(STOP.search(l) for l in lines(pdf))

# ---------- diff ----------
def word_diff(a, b):
    aw, bw = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, aw, bw, autojunk=False)
    out, changed = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(html.escape(" ".join(aw[i1:i2])))
        else:
            changed += (i2 - i1) + (j2 - j1)
            if i2 > i1: out.append("<del>" + html.escape(" ".join(aw[i1:i2])) + "</del>")
            if j2 > j1: out.append("<ins>" + html.escape(" ".join(bw[j1:j2])) + "</ins>")
    return " ".join(out), changed, sm.ratio()

def pair_documents(DA, DB):
    """Pareia bulas de dois PDFs pela semelhança do texto (a ordem das apresentações muda entre versões)."""
    def blob(d): return " ".join(d["secoes"].values())[:20000]
    scores = sorted(((difflib.SequenceMatcher(None, blob(a), blob(b), autojunk=True).quick_ratio(), i, j)
                     for i, a in enumerate(DA) for j, b in enumerate(DB)), reverse=True)
    pairs, ua, ub = [], set(), set()
    for _, i, j in scores:
        if i not in ua and j not in ub:
            pairs.append((i, j)); ua.add(i); ub.add(j)
    pairs += [(i, None) for i in range(len(DA)) if i not in ua] + [(None, j) for j in range(len(DB)) if j not in ub]
    return pairs

def doc_label(d):
    return (d["secoes"].get("I") or d["secoes"].get("(preâmbulo)") or "")[:60]

def diff(pdf_a, pdf_b):
    """Diff bula a bula (pareadas por semelhança) e seção a seção."""
    DA, DB = documents(pdf_a), documents(pdf_b)
    rows = []
    for n, (i, j) in enumerate(pair_documents(DA, DB), 1):
        A = DA[i]["secoes"] if i is not None else {}
        B = DB[j]["secoes"] if j is not None else {}
        tag = f"[{n}: {doc_label(DA[i] if i is not None else DB[j])}] " if max(len(DA), len(DB)) > 1 else ""
        for k in dict.fromkeys(list(A) + list(B)):
            a, b = A.get(k, ""), B.get(k, "")
            if a == b:
                rows.append(dict(secao=tag + k, status="igual", palavras=0, ratio=1.0, html=""))
            else:
                h, ch, r = word_diff(a, b)
                rows.append(dict(secao=tag + k, status="alterada", palavras=ch, ratio=r, html=h))
    return rows

def diff_html(rows, title, subtitle):
    css = ("body{font:15px/1.5 system-ui;max-width:900px;margin:2em auto;padding:0 1em}del{background:#fdd}"
           "ins{background:#dfd;text-decoration:none}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 8px}"
           ".alterada{color:#b00;font-weight:bold}small{color:#666;font-weight:normal}")
    table = "".join(f"<tr><td>{html.escape(r['secao'])}</td><td class={r['status']}>{r['status']}</td>"
                    f"<td>{r['palavras']}</td><td>{r['ratio']:.0%}</td></tr>" for r in rows)
    body = "".join(f"<h2>{html.escape(r['secao'])} <small>{r['palavras']} palavras, similaridade {r['ratio']:.0%}</small></h2><p>{r['html']}</p>"
                   for r in rows if r["status"] == "alterada")
    return (f"<meta charset=utf-8><title>bula-diff</title><style>{css}</style><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>"
            f"<table><tr><th>Seção</th><th>Status</th><th>Palavras alteradas</th><th>Similaridade</th></tr>{table}</table>{body}")

# ---------- CLI ----------
if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "fetch":
        fetch(args[0], all_versions="--all" in args)
    elif cmd == "search":
        for p in search(nomeProduto=args[0]):
            print(f"{p['numeroRegistro']}  {p['nomeProduto'][:30]:30}  {p['razaoSocial'][:40]:40}  {p['data'][:10]}")
    elif cmd == "sections":
        for i, d in enumerate(documents(args[0]), 1):
            print(f"documento {i} ({d['tipo']})")
            for k, v in d["secoes"].items():
                print(f"{len(v):7d}  {k}")
    elif cmd == "diff":
        rows = diff(args[0], args[1])
        out = diff_html(rows, f"{args[0]} → {args[1]}", "")
        (pathlib.Path(args[2]) if len(args) > 2 else sys.stdout).write_text(out) if len(args) > 2 else print(out)
    else:
        print(__doc__)
