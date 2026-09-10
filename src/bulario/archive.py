"""Arquivo local, sem PDF: data/<registro>/meta.json + <dataPublicacao>_<expediente>_<vp|vps>.json.

Cada JSON de versão guarda o texto já segmentado (documentos → seções), a tabela de histórico lida do
PDF e o hash do PDF. O PDF é baixado para um arquivo temporário, extraído e descartado.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bulario.api import Client
from bulario.extract import Document, documents_from_pdf, pdf_pages

KINDS = (("vp", "idBulaPaciente"), ("vps", "idBulaProfissional"))
META = "meta.json"


@dataclass
class VersionText:
    """Texto de uma bula (um tipo, um expediente) pronto para diff."""

    registro: str
    expediente: str
    data: str  # AAAA-MM-DD
    situacao: str
    tipo: str  # "vp" | "vps"
    pdf_sha256: str
    paginas: int
    documentos: list[Document] = field(default_factory=list)
    historico_tabela: list[dict] = field(default_factory=list)  # HistoryEntry.to_dict()

    @property
    def declarado(self) -> list[str]:
        """Seções declaradas na última linha da tabela de histórico (a submissão que gerou este PDF)."""
        from bulario.history import HistoryEntry

        if not self.historico_tabela:
            return []
        return HistoryEntry(**self.historico_tabela[-1]).secoes

    def to_dict(self) -> dict:
        d = asdict(self)
        d["documentos"] = [doc.to_dict() for doc in self.documentos]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> VersionText:
        d = dict(d)
        d["documentos"] = [Document.from_dict(x) for x in d.get("documentos", [])]
        return cls(**d)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1))

    @classmethod
    def load(cls, path: Path) -> VersionText:
        return cls.from_dict(json.loads(path.read_text()))


@dataclass
class Version:
    expediente: str
    data: str  # AAAA-MM-DD
    situacao: str
    textos: dict[str, Path]  # "vp"/"vps" -> caminho do JSON

    def load(self, kind: str) -> VersionText:
        return VersionText.load(self.textos[kind])


def version_path(root: Path, item: dict, kind: str, suffix: str = ".json") -> Path:
    return root / f"{item['dataPublicacao'][:10]}_{item['expediente']}_{kind}{suffix}"


def extract_pdf(pdf: Path, registro: str, item: dict, kind: str) -> VersionText:
    """Extrai documentos e tabela de histórico de um PDF já em disco."""
    try:
        from bulario.history import read_history

        tabela = [e.to_dict() for e in read_history(pdf).entries]
    except ImportError:  # extra `tables` ausente
        tabela = []
    return VersionText(
        registro=registro,
        expediente=item["expediente"],
        data=item["dataPublicacao"][:10],
        situacao=item.get("descSituacao", ""),
        tipo=kind,
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        paginas=len(pdf_pages(pdf)),
        documentos=documents_from_pdf(pdf),
        historico_tabela=tabela,
    )


TOKEN_KEYS = {
    "idBulaPaciente",
    "idBulaProfissional",
    "idBulaPacienteProtegido",
    "idBulaProfissionalProtegido",
}


def strip_tokens(obj):
    """Remove os ids de PDF (JWT que expira em 5 min) para o meta.json não mudar a cada execução."""
    if isinstance(obj, dict):
        return {k: strip_tokens(v) for k, v in obj.items() if k not in TOKEN_KEYS}
    if isinstance(obj, list):
        return [strip_tokens(v) for v in obj]
    return obj


EXPIRED = {400, 401, 403}  # respostas do download quando o id JWT (5 min) expirou


def _ids_by_document(hist: dict) -> dict[tuple[int, str], str]:
    """(idDocumento, chave) -> id de download, a partir de uma resposta do histórico."""
    return {
        (item["idDocumento"], key): item[key]
        for item in hist["historico"]["content"]
        for _, key in KINDS
        if item.get(key)
    }


def fetch(
    registro: str,
    root: Path = Path("data"),
    client: Client | None = None,
    latest: int | None = 2,
    keep_pdf: bool = False,
    log=print,
    workers: int = 2,
) -> tuple[dict, list[Version]]:
    """Arquiva as versões de bula de um registro como JSON. `latest=None` pega todas. Idempotente.

    Os downloads são sequenciais (1 req/s); a extração roda em threads para não gastar a janela de
    5 minutos dos ids. Se um id expirar mesmo assim, o histórico é consultado de novo e o download repetido.
    """
    client = client or Client()
    found = client.search(numeroRegistro=registro)["content"]
    if not found:
        raise LookupError(f"registro {registro} não encontrado no bulário")
    prod = found[0]
    out = root / registro
    out.mkdir(parents=True, exist_ok=True)
    hist = client.historico(prod["idProduto"], all_pages=latest is None)
    (out / META).write_text(
        json.dumps(strip_tokens({"produto": prod, "historico": hist}), ensure_ascii=False, indent=1)
    )
    items = sorted(hist["historico"]["content"], key=lambda v: v["dataPublicacao"], reverse=True)
    if latest is not None:
        items = items[:latest]
    log(f"{prod['nomeProduto']} — {prod['razaoSocial']} — {hist['historico']['totalElements']} versões")
    ids = _ids_by_document(hist)

    def download(item: dict, key: str) -> bytes:
        try:
            return client.download_bula(ids[(item["idDocumento"], key)])
        except urllib.error.HTTPError as e:
            if e.code not in EXPIRED:
                raise
            log("  ids expiraram; consultando o histórico de novo")
            ids.update(_ids_by_document(client.historico(prod["idProduto"], all_pages=latest is None)))
            return client.download_bula(ids[(item["idDocumento"], key)])

    def extract_and_save(pdf: Path, item: dict, kind: str, dest: Path, downloaded: bool) -> str:
        extract_pdf(pdf, registro, item, kind).save(dest)
        if not keep_pdf:
            pdf.unlink()
        return f"  {dest.name}  {'baixado' if downloaded else 'convertido'}"

    versions = []
    pending: list[Future[str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item in items:
            textos = {}
            for kind, key in KINDS:
                if not item.get(key):
                    log(f"  {item['expediente']} sem {kind}")
                    continue
                dest = version_path(out, item, kind)
                if not dest.exists():
                    pdf = version_path(out, item, kind, ".pdf")
                    downloaded = not pdf.exists()
                    if downloaded:
                        pdf.write_bytes(download(item, key))
                    pending.append(pool.submit(extract_and_save, pdf, item, kind, dest, downloaded))
                textos[kind] = dest
            versions.append(
                Version(item["expediente"], item["dataPublicacao"][:10], item["descSituacao"], textos)
            )
        for fut in pending:
            log(fut.result())  # propaga erro de extração, se houver
    return prod, versions


def local_versions(registro: str, root: Path = Path("data")) -> list[Version]:
    """Versões arquivadas, da mais antiga para a mais nova."""
    out = root / registro
    by_key: dict[tuple[str, str], dict[str, Path]] = {}
    for f in sorted(out.glob("*_*_*.json")):
        data, exp, kind = f.stem.rsplit("_", 2)
        by_key.setdefault((data, exp), {})[kind] = f
    return [Version(exp, data, "", textos) for (data, exp), textos in sorted(by_key.items())]


def load_meta(registro: str, root: Path = Path("data")) -> dict | None:
    f = root / registro / META
    return json.loads(f.read_text()) if f.exists() else None


def registros(root: Path = Path("data")) -> list[str]:
    """Registros com meta.json no arquivo."""
    return sorted(p.parent.name for p in root.glob("*/" + META))


def read_curated(path: Path = Path("registros.txt")) -> list[str]:
    """Lista curada: um registro por linha; `#` inicia comentário."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        reg = line.split("#", 1)[0].strip()
        if reg:
            out.append(reg)
    return out
