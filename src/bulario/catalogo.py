"""Catálogo: todos os produtos do Bulário, numa varredura só.

A busca com `nomeProduto` vazio e `count=1000` lista o bulário inteiro em poucas páginas (8.819
produtos em 9 requisições em 2026-09). Cada item traz registro, nome, empresa, CNPJ e a data da
última bula publicada — o bastante para a página de catálogo do site e para saber o tamanho do todo.
O resultado fica em data/catalogo.json.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from bulario.api import Client

ARQUIVO = "catalogo.json"
POR_PAGINA = 1000


def baixar(client: Client, log=print) -> list[dict]:
    """Todos os produtos, ordenados por nome e registro."""
    produtos: list[dict] = []
    page = 1
    while True:
        r = client.search(page=page, count=POR_PAGINA, nomeProduto="")
        produtos += [
            {
                "registro": p["numeroRegistro"],
                "idProduto": p["idProduto"],
                "nome": p["nomeProduto"],
                "empresa": p["razaoSocial"],
                "cnpj": p["cnpj"],
                "data": (p.get("data") or "")[:10],
            }
            for p in r["content"]
        ]
        log(f"  página {page}/{r.get('totalPages', '?')}: {len(produtos)} produtos")
        if r.get("last", True):
            break
        page += 1
    return sorted(produtos, key=lambda p: (p["nome"].lower(), p["registro"]))


def salvar(root: Path, produtos: list[dict], hoje: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    estado = {"atualizado": hoje or dt.date.today().isoformat(), "produtos": produtos}
    (root / ARQUIVO).write_text(json.dumps(estado, ensure_ascii=False, indent=0))


def carregar(root: Path) -> dict:
    f = root / ARQUIVO
    return json.loads(f.read_text()) if f.exists() else {"atualizado": None, "produtos": []}


def run(root: Path, client: Client | None = None, log=print) -> int:
    produtos = baixar(client or Client(), log)
    salvar(root, produtos)
    log(f"{len(produtos)} produtos em {root / ARQUIVO}")
    return len(produtos)
