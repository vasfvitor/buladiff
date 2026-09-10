import json
import urllib.error
from pathlib import Path

from bulario import archive
from bulario.archive import VersionText, fetch
from bulario.extract import Document

PROD = {
    "idProduto": 1,
    "numeroRegistro": "118190404",
    "nomeProduto": "risperidona",
    "razaoSocial": "MULTILAB",
    "cnpj": "1",
    "data": "2025-01-28T00:00:00.000-0200",
}


def item(doc: int, exp: str, data: str, token: str) -> dict:
    return {
        "idDocumento": doc,
        "expediente": exp,
        "dataPublicacao": f"{data}T00:00:00.000-0200",
        "descSituacao": "Aditado ao processo",
        "idBulaPaciente": f"{token}-vp-{doc}",
        "idBulaProfissional": f"{token}-vps-{doc}",
    }


class FakeClient:
    """Histórico com 2 versões; cada chamada ao histórico gera ids novos ('t1', 't2'…).
    Downloads com id de uma geração antiga respondem 403 (id expirado)."""

    def __init__(self):
        self.geracao = 0
        self.downloads: list[str] = []
        self.historicos = 0

    def search(self, **_):
        return {"content": [PROD]}

    def historico(self, id_produto, all_pages=True):
        self.geracao += 1
        self.historicos += 1
        t = f"t{self.geracao}"
        return {
            "historico": {
                "content": [item(1, "0046116231", "2023-01-16", t), item(2, "0121761258", "2025-01-28", t)],
                "totalElements": 2,
            }
        }

    def produto(self, id_produto):
        return {
            "principioAtivo": "risperidona",
            "classesTerapeuticas": ["NEUROLEPTICOS"],
            "apresentacoes": [],
        }

    def download_bula(self, id_bula: str) -> bytes:
        self.downloads.append(id_bula)
        if not id_bula.startswith(f"t{self.geracao}-"):
            raise urllib.error.HTTPError("http://x", 403, "expired", {}, None)
        return b"%PDF-fake " + id_bula.encode()


def fake_extract(pdf: Path, registro: str, it: dict, kind: str) -> VersionText:
    return VersionText(
        registro,
        it["expediente"],
        it["dataPublicacao"][:10],
        it.get("descSituacao", ""),
        kind,
        "sha",
        1,
        [Document({"1": pdf.name}, kind)],
        [],
    )


def test_fetch_extracts_in_threads_and_removes_pdfs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(archive, "extract_pdf", fake_extract)
    client = FakeClient()
    logs: list[str] = []
    prod, versions = fetch("118190404", tmp_path, client=client, latest=None, log=logs.append)
    assert prod["nomeProduto"] == "risperidona" and len(versions) == 2
    files = sorted(p.name for p in (tmp_path / "118190404").iterdir())
    assert files == [
        "2023-01-16_0046116231_vp.json",
        "2023-01-16_0046116231_vps.json",
        "2025-01-28_0121761258_vp.json",
        "2025-01-28_0121761258_vps.json",
        "meta.json",
    ]
    assert client.historicos == 1 and len(client.downloads) == 4
    assert sum("baixado" in line for line in logs) == 4
    meta = json.loads((tmp_path / "118190404" / "meta.json").read_text())
    assert meta["detalhe"]["principioAtivo"] == "risperidona" and meta["detalhe"]["apresentacoes"] == []


def test_fetch_refreshes_expired_ids(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(archive, "extract_pdf", fake_extract)
    client = FakeClient()

    # simula a expiração: depois do 2º download, a geração avança sem o fetch saber
    original = client.download_bula

    def download_with_expiry(id_bula: str) -> bytes:
        if len(client.downloads) == 2:
            client.geracao += 1
        return original(id_bula)

    client.download_bula = download_with_expiry  # type: ignore[method-assign]
    logs: list[str] = []
    fetch("118190404", tmp_path, client=client, latest=None, log=logs.append)
    assert client.historicos == 2  # consultou o histórico de novo após o 403
    assert any("expiraram" in line for line in logs)
    assert len(list((tmp_path / "118190404").glob("*_*_*.json"))) == 4


def test_fetch_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(archive, "extract_pdf", fake_extract)
    client = FakeClient()
    fetch("118190404", tmp_path, client=client, latest=None, log=lambda s: None)
    fetch("118190404", tmp_path, client=client, latest=None, log=lambda s: None)
    assert len(client.downloads) == 4  # segunda execução não baixa nada


def test_reextract_rebuilds_json_from_local_pdfs(tmp_path: Path, monkeypatch):
    from bulario.archive import reextract

    monkeypatch.setattr(archive, "extract_pdf", fake_extract)
    client = FakeClient()
    fetch("118190404", tmp_path, client=client, latest=None, keep_pdf=True, log=lambda s: None)
    (tmp_path / "118190404" / "2023-01-16_0046116231_vp.json").unlink()
    assert reextract("118190404", tmp_path, log=lambda s: None) == 1
    assert reextract("118190404", tmp_path, log=lambda s: None) == 0
    assert reextract("118190404", tmp_path, force=True, log=lambda s: None) == 4
    v = VersionText.load(tmp_path / "118190404" / "2023-01-16_0046116231_vp.json")
    assert v.expediente == "0046116231" and v.data == "2023-01-16" and v.situacao == "Aditado ao processo"
