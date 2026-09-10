"""Cliente da API interna de consultas.anvisa.gov.br (a que a página do Bulário usa).

Não é documentada. Exige `Authorization: Guest` e headers de navegador (Cloudflare).
Os ids de PDF são JWT com ~5 minutos de validade: baixe logo depois de consultar.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://consultas.anvisa.gov.br/api/consulta"
HEADERS = {
    "Authorization": "Guest",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://consultas.anvisa.gov.br/",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
}


def _retry_after(e: urllib.error.HTTPError) -> float:
    try:
        return float(e.headers.get("Retry-After", 0))
    except (TypeError, ValueError):
        return 0.0


def _transitorio(e: Exception) -> bool:
    """Vale a pena tentar de novo? Erro de rede, resposta truncada, 5xx ou 429; outros 4xx não."""
    return not isinstance(e, urllib.error.HTTPError) or e.code >= 500 or e.code == 429


def _espera(e: Exception, tentativa: int) -> float:
    """Segundos antes da próxima tentativa: no 429, o que o servidor pedir (mínimo 10 s); senão 2, 4, 8…"""
    if isinstance(e, urllib.error.HTTPError) and e.code == 429:
        return max(_retry_after(e), 10)
    return 2 ** (tentativa + 1)


class Client:
    """Requisições com intervalo mínimo entre chamadas (padrão 1 s)."""

    def __init__(self, delay: float = 1.0, timeout: float = 60.0, retries: int = 3):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries  # tentativas extras em 5xx/429/erro de rede/resposta truncada
        self._last = 0.0

    def _get(self, path: str, params: dict[str, Any] | None = None) -> bytes:
        """Falhas saem sempre como `urllib.error.URLError` (um `OSError`), inclusive resposta truncada."""
        url = f"{BASE}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for tentativa in range(self.retries + 1):
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = r.read()
            except (urllib.error.URLError, TimeoutError, http.client.HTTPException) as e:
                self._last = time.monotonic()
                if not _transitorio(e) or tentativa == self.retries:
                    if isinstance(e, http.client.HTTPException):  # IncompleteRead: a ANVISA trunca às vezes
                        raise urllib.error.URLError(e) from e
                    raise
                time.sleep(_espera(e, tentativa))
                continue
            self._last = time.monotonic()
            return data
        raise AssertionError("unreachable")

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return json.loads(self._get(path, params))

    # -- bulário --------------------------------------------------------

    def search(self, page: int = 1, count: int = 50, **filtro: str) -> dict:
        """GET /bulario?filter[...] — resposta paginada (Spring Page).

        Filtros: nomeProduto, numeroRegistro, expediente, cnpj, categoriasRegulatorias,
        periodoPublicacaoInicial/periodoPublicacaoFinal (AAAA-MM-DD).
        """
        params = {"count": count, "page": page, **{f"filter[{k}]": v for k, v in filtro.items()}}
        return self.get_json("bulario", params)

    def search_pages(self, count: int = 200, **filtro: str):
        """Itera as páginas de uma busca (cada uma um Spring Page)."""
        page = 1
        while True:
            r = self.search(page=page, count=count, **filtro)
            yield r
            if r.get("last", True):
                return
            page += 1

    def search_all(self, **filtro: str):
        """Itera todos os resultados de uma busca."""
        for r in self.search_pages(**filtro):
            yield from r["content"]

    def historico(self, id_produto: int, limit: int | None = None) -> dict:
        """GET /bulario/{idProduto}: {registroProduto, nomeProduto, bulaAtual, historico: Page}.
        Cada item do histórico tem expediente, dataPublicacao, idBulaPaciente, idBulaProfissional.
        Vem do mais recente para o mais antigo; `limit` pega só os N primeiros, `None` pega todos."""
        h = self.get_json(f"bulario/{id_produto}", {"count": limit or 500})
        if limit is None:
            for page in range(2, h["historico"]["totalPages"] + 1):
                more = self.get_json(f"bulario/{id_produto}", {"page": page, "count": 500})
                h["historico"]["content"] += more["historico"]["content"]
        return h

    def download_bula(self, id_bula: str) -> bytes:
        """GET /medicamentos/arquivo/bula/parecer/{id}/ — PDF (application/force-download)."""
        return self._get(f"medicamentos/arquivo/bula/parecer/{id_bula}/?Authorization=")

    def produto(self, id_produto: int) -> dict:
        """GET /medicamento/produtos/codigo/{idProduto}: classe terapêutica, ATC, vencimento, ids de bula."""
        return self.get_json(f"medicamento/produtos/codigo/{id_produto}")
