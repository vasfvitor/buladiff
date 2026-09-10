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
from bulario.extract import Document, extract_documents, pdf_pages
from bulario.history import HistoryEntry, read_history

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
    marcado: bool = False  # `documentos` veio da árvore de estrutura do PDF (parágrafos preservados)
    documentos_linhas: list[Document] = field(default_factory=list)  # extração por linhas, se marcado

    def comparavel(self, other: VersionText) -> list[Document]:
        """Documentos para comparar com `other`: a mesma extração dos dois lados. Se só um é marcado,
        usa-se a extração por linhas nos dois; misturar as duas enche o diff de diferenças falsas."""
        if self.marcado and not other.marcado and self.documentos_linhas:
            return self.documentos_linhas
        return self.documentos

    @property
    def declarado(self) -> list[str]:
        """Seções declaradas na última linha da tabela de histórico (a submissão que gerou este PDF)."""
        if not self.historico_tabela:
            return []
        return HistoryEntry(**self.historico_tabela[-1]).secoes

    def to_dict(self) -> dict:
        d = asdict(self)
        d["documentos"] = [doc.to_dict() for doc in self.documentos]
        d["documentos_linhas"] = [doc.to_dict() for doc in self.documentos_linhas]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> VersionText:
        d = dict(d)
        d["documentos"] = [Document.from_dict(x) for x in d.get("documentos", [])]
        d["documentos_linhas"] = [Document.from_dict(x) for x in d.get("documentos_linhas", [])]
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
    textos: dict[str, Path]  # "vp"/"vps" -> caminho do JSON


def version_path(root: Path, data: str, expediente: str, kind: str, suffix: str = ".json") -> Path:
    return root / f"{data}_{expediente}_{kind}{suffix}"


def version_parts(path: Path) -> tuple[str, str, str]:
    """(data, expediente, tipo) do nome de um arquivo de versão; o inverso de `version_path`."""
    data, expediente, kind = path.stem.rsplit("_", 2)
    return data, expediente, kind


def extract_pdf(
    pdf: Path, registro: str, kind: str, expediente: str, data: str, situacao: str = ""
) -> VersionText:
    """Extrai documentos e tabela de histórico de um PDF já em disco."""
    pages = pdf_pages(pdf)
    marcados, linhas = extract_documents(pdf, pages)
    return VersionText(
        registro=registro,
        expediente=expediente,
        data=data,
        situacao=situacao,
        tipo=kind,
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        paginas=len(pages),
        documentos=marcados or linhas,
        historico_tabela=[e.to_dict() for e in read_history(pdf).entries],
        marcado=bool(marcados),
        documentos_linhas=linhas if marcados else [],
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


def resumo_detalhe(d: dict) -> dict:
    """O que o site usa do detalhe do produto (`/medicamento/produtos/codigo/{id}`), sem os ids de bula."""
    return {
        "principioAtivo": d.get("principioAtivo") or "",
        "classesTerapeuticas": d.get("classesTerapeuticas") or [],
        "atcs": d.get("atcs") or [],
        "categoriaRegulatoria": d.get("categoriaRegulatoria") or "",
        "medicamentoReferencia": d.get("medicamentoReferencia") or "",
        "dataVencimentoRegistro": (d.get("dataVencimentoRegistro") or "")[:10],
        "apresentacoes": [
            {
                "apresentacao": (ap.get("apresentacao") or "").strip(),
                "formasFarmaceuticas": ap.get("formasFarmaceuticas") or [],
                "viasAdministracao": ap.get("viasAdministracao") or [],
                "restricaoPrescricao": ap.get("restricaoPrescricao") or [],
                "registro": ap.get("registro") or "",
            }
            for ap in d.get("apresentacoes") or []
        ],
    }


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

    def historico() -> dict:
        return client.historico(prod["idProduto"], limit=latest)

    hist = historico()
    try:
        detalhe = resumo_detalhe(client.produto(prod["idProduto"]))
    except OSError as e:  # o detalhe é complemento; o histórico é o que importa
        log(f"  detalhe do produto indisponível ({e})")
        detalhe = load_meta(registro, root).get("detalhe", {})
    meta = {"produto": prod, "historico": hist, "detalhe": detalhe}
    (out / META).write_text(json.dumps(strip_tokens(meta), ensure_ascii=False, indent=1))
    items = sorted(hist["historico"]["content"], key=lambda v: v["dataPublicacao"], reverse=True)[:latest]
    log(f"{prod['nomeProduto']} — {prod['razaoSocial']} — {hist['historico']['totalElements']} versões")
    ids = _ids_by_document(hist)

    def download(item: dict, key: str) -> bytes:
        for renovado in (False, True):
            try:
                return client.download_bula(ids[(item["idDocumento"], key)])
            except urllib.error.HTTPError as e:
                if renovado or e.code not in EXPIRED:
                    raise
                log("  ids expiraram; consultando o histórico de novo")
                ids.update(_ids_by_document(historico()))
        raise AssertionError("unreachable")

    def extract_and_save(pdf: Path, v: Version, kind: str, situacao: str, downloaded: bool) -> str:
        dest = v.textos[kind]
        extract_pdf(pdf, registro, kind, v.expediente, v.data, situacao).save(dest)
        if not keep_pdf:
            pdf.unlink()
        return f"  {dest.name}  {'baixado' if downloaded else 'convertido'}"

    versions = []
    pending: list[Future[str]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for item in items:
            v = Version(item["expediente"], item["dataPublicacao"][:10], {})
            for kind, key in KINDS:
                if not item.get(key):
                    log(f"  {v.expediente} sem {kind}")
                    continue
                dest = v.textos[kind] = version_path(out, v.data, v.expediente, kind)
                if dest.exists():
                    continue
                pdf = version_path(out, v.data, v.expediente, kind, ".pdf")
                downloaded = not pdf.exists()
                if downloaded:
                    pdf.write_bytes(download(item, key))
                pending.append(
                    pool.submit(extract_and_save, pdf, v, kind, item.get("descSituacao", ""), downloaded)
                )
            versions.append(v)
        for fut in pending:
            log(fut.result())  # propaga erro de extração, se houver
    return prod, versions


def reextract(registro: str, root: Path = Path("data"), force: bool = False, log=print) -> int:
    """Refaz os JSON a partir dos PDFs guardados em data/<registro>/ (`fetch --keep-pdf`), sem a API.
    Só os que faltam, ou todos com `force`. Devolve quantos foram extraídos."""
    out = root / registro
    situacao = situacoes(load_meta(registro, root))
    n = 0
    for pdf in sorted(out.glob("*_*_*.pdf")):
        data, exp, kind = version_parts(pdf)
        dest = pdf.with_suffix(".json")
        if dest.exists() and not force:
            continue
        extract_pdf(pdf, registro, kind, exp, data, situacao.get(exp, "")).save(dest)
        log(f"  {dest.name}  convertido")
        n += 1
    return n


def local_versions(registro: str, root: Path = Path("data")) -> list[Version]:
    """Versões arquivadas, da mais antiga para a mais nova."""
    out = root / registro
    by_key: dict[tuple[str, str], dict[str, Path]] = {}
    for f in sorted(out.glob("*_*_*.json")):
        data, exp, kind = version_parts(f)
        by_key.setdefault((data, exp), {})[kind] = f
    return [Version(exp, data, textos) for (data, exp), textos in sorted(by_key.items())]


def load_meta(registro: str, root: Path = Path("data")) -> dict:
    """meta.json do registro; `{}` se ainda não foi arquivado."""
    f = root / registro / META
    return json.loads(f.read_text()) if f.exists() else {}


def situacoes(meta: dict) -> dict[str, str]:
    """expediente -> situação ("Aditado ao processo"…), do histórico da API guardado no meta.json."""
    content = meta.get("historico", {}).get("historico", {}).get("content", [])
    return {h["expediente"]: h.get("descSituacao", "") for h in content}


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
