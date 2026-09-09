"""Feed de publicações: o que entrou no Bulário num período, e arquivo incremental a partir dele.

Usa o filtro `periodoPublicacaoInicial/Final` da busca — uma chamada por dia cobre todas as bulas
publicadas, sem varrer registro a registro. O estado (última data coberta) fica em data/feed.json.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bulario.api import Client
from bulario.archive import fetch

STATE_FILE = "feed.json"


@dataclass
class Published:
    registro: str
    id_produto: int
    nome: str
    empresa: str
    cnpj: str
    expediente: str
    data: str  # AAAA-MM-DD
    processo: str

    @classmethod
    def from_api(cls, p: dict) -> Published:
        return cls(
            registro=p["numeroRegistro"],
            id_produto=p["idProduto"],
            nome=p["nomeProduto"],
            empresa=p["razaoSocial"],
            cnpj=p["cnpj"],
            expediente=p["expediente"],
            data=p["data"][:10],
            processo=p["numProcesso"],
        )


def published(client: Client, desde: str, ate: str) -> list[Published]:
    """Bulas publicadas entre `desde` e `ate` (AAAA-MM-DD, inclusivo), ordenadas por data."""
    items = client.search_all(periodoPublicacaoInicial=desde, periodoPublicacaoFinal=ate)
    return sorted((Published.from_api(p) for p in items), key=lambda p: (p.data, p.nome))


def load_state(root: Path) -> dict:
    f = root / STATE_FILE
    return json.loads(f.read_text()) if f.exists() else {}


def save_state(root: Path, state: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=1))


def run(
    root: Path,
    desde: str | None = None,
    ate: str | None = None,
    download: bool = False,
    client: Client | None = None,
    log=print,
) -> list[Published]:
    """Lista (e opcionalmente arquiva) o que foi publicado. Sem `desde`, continua do último estado."""
    client = client or Client()
    state = load_state(root)
    hoje = dt.date.today().isoformat()
    desde = desde or state.get("ate") or hoje
    ate = ate or hoje
    items = published(client, desde, ate)
    log(f"{len(items)} bulas publicadas de {desde} a {ate}")
    for p in items:
        log(f"  {p.data}  {p.registro}  {p.nome[:32]:32}  {p.empresa[:40]}")
    if download:
        for registro in dict.fromkeys(p.registro for p in items):
            try:
                fetch(registro, root, client=client, latest=2, log=lambda s: log("    " + s))
            except (LookupError, OSError) as e:
                log(f"    erro em {registro}: {e}")
    state.update({"ate": ate, "ultima_execucao": dt.datetime.now().isoformat(timespec="seconds")})
    historico = state.setdefault("publicacoes", [])
    known = {(h["registro"], h["expediente"]) for h in historico}
    historico.extend(asdict(p) for p in items if (p.registro, p.expediente) not in known)
    save_state(root, state)
    return items
