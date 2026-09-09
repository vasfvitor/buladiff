"""Arquivo local: data/<registro>/<dataPublicacao>_<expediente>_<vp|vps>.pdf + historico.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bulario.api import Client

KINDS = (("vp", "idBulaPaciente"), ("vps", "idBulaProfissional"))


@dataclass
class Version:
    expediente: str
    data: str  # AAAA-MM-DD
    situacao: str
    files: dict[str, Path]  # "vp"/"vps" -> caminho


def version_path(root: Path, item: dict, kind: str) -> Path:
    return root / f"{item['dataPublicacao'][:10]}_{item['expediente']}_{kind}.pdf"


def fetch(
    registro: str, root: Path = Path("data"), client: Client | None = None, latest: int | None = 2, log=print
) -> tuple[dict, list[Version]]:
    """Baixa as versões de bula de um registro. `latest=None` baixa todas."""
    client = client or Client()
    found = client.search(numeroRegistro=registro)["content"]
    if not found:
        raise LookupError(f"registro {registro} não encontrado no bulário")
    prod = found[0]
    out = root / registro
    out.mkdir(parents=True, exist_ok=True)
    hist = client.historico(prod["idProduto"], all_pages=latest is None)
    (out / "historico.json").write_text(json.dumps(hist, ensure_ascii=False, indent=1))
    items = sorted(hist["historico"]["content"], key=lambda v: v["dataPublicacao"], reverse=True)
    if latest is not None:
        items = items[:latest]
    log(f"{prod['nomeProduto']} — {prod['razaoSocial']} — {hist['historico']['totalElements']} versões")
    versions = []
    for item in items:
        files = {}
        for kind, key in KINDS:
            if not item.get(key):
                log(f"  {item['expediente']} sem {kind}")
                continue
            dest = version_path(out, item, kind)
            if not dest.exists():
                dest.write_bytes(client.download_bula(item[key]))
                log(f"  {dest.name}  {dest.stat().st_size // 1024} KB")
            files[kind] = dest
        versions.append(Version(item["expediente"], item["dataPublicacao"][:10], item["descSituacao"], files))
    return prod, versions


def local_versions(registro: str, root: Path = Path("data")) -> list[Version]:
    """Versões já baixadas, da mais antiga para a mais nova."""
    out = root / registro
    by_key: dict[tuple[str, str], dict[str, Path]] = {}
    for pdf in sorted(out.glob("*_*_*.pdf")):
        data, exp, kind = pdf.stem.rsplit("_", 2)
        by_key.setdefault((data, exp), {})[kind] = pdf
    return [Version(exp, data, "", files) for (data, exp), files in sorted(by_key.items())]
