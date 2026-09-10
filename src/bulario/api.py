"""Cliente da API interna de consultas.anvisa.gov.br (a que a página do Bulário usa).

Não é documentada. Exige `Authorization: Guest` e headers de navegador (Cloudflare).
Os ids de PDF são JWT com ~5 minutos de validade: baixe logo depois de consultar.
"""

from __future__ import annotations

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


class Client:
    """Requisições com intervalo mínimo entre chamadas (padrão 1 s)."""

    def __init__(self, base: str = BASE, delay: float = 1.0, timeout: float = 60.0, retries: int = 3):
        self.base = base
        self.delay = delay
        self.timeout = timeout
        self.retries = retries  # tentativas extras em 5xx/erro de rede, com espera 2s, 4s, 8s…
        self._last = 0.0

    def _get(self, path: str, params: dict[str, Any] | None = None) -> bytes:
        url = f"{self.base}/{path}"
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        for attempt in range(self.retries + 1):
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = r.read()
                self._last = time.monotonic()
                return data
            except urllib.error.HTTPError as e:
                self._last = time.monotonic()
                if e.code < 500 or attempt == self.retries:
                    raise
            except (urllib.error.URLError, TimeoutError):
                self._last = time.monotonic()
                if attempt == self.retries:
                    raise
            time.sleep(2 ** (attempt + 1))
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

    def search_all(self, **filtro: str):
        """Itera todos os resultados de uma busca."""
        page = 1
        while True:
            r = self.search(page=page, count=200, **filtro)
            yield from r["content"]
            if r.get("last", True):
                return
            page += 1

    def historico(self, id_produto: int, all_pages: bool = True) -> dict:
        """GET /bulario/{idProduto}: {registroProduto, nomeProduto, bulaAtual, historico: Page}.
        Cada item do histórico tem expediente, dataPublicacao, idBulaPaciente, idBulaProfissional."""
        h = self.get_json(f"bulario/{id_produto}")
        if all_pages:
            for page in range(2, h["historico"]["totalPages"] + 1):
                more = self.get_json(f"bulario/{id_produto}", {"page": page})
                h["historico"]["content"] += more["historico"]["content"]
        return h

    def download_bula(self, id_bula: str) -> bytes:
        """GET /medicamentos/arquivo/bula/parecer/{id}/ — PDF (application/force-download)."""
        return self._get(f"medicamentos/arquivo/bula/parecer/{id_bula}/?Authorization=")

    def produto(self, id_produto: int) -> dict:
        """GET /medicamento/produtos/codigo/{idProduto}: classe terapêutica, ATC, vencimento, ids de bula."""
        return self.get_json(f"medicamento/produtos/codigo/{id_produto}")
