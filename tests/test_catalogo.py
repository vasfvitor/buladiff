import json

from bulario import catalogo
from bulario.api import Client

ITEM = {
    "idProduto": 3561242,
    "numeroRegistro": "118190404",
    "nomeProduto": "risperidona",
    "razaoSocial": "MULTILAB",
    "cnpj": "92265552000905",
    "data": "2025-01-28T15:13:10.000-0200",
}


class FakeClient(Client):
    """Só a busca é falsa; a paginação (`search_pages`) é a do cliente de verdade."""

    def __init__(self):
        self.calls = []

    def search(self, page=1, count=50, **filtro):
        self.calls.append((page, count, filtro))
        content = [ITEM] if page == 1 else [{**ITEM, "numeroRegistro": "1", "nomeProduto": "Abacavir"}]
        return {"content": content, "totalPages": 2, "last": page == 2}


def test_run_pages_through_whole_catalog(tmp_path):
    client = FakeClient()
    n = catalogo.run(tmp_path, client=client, log=lambda s: None)
    assert n == 2 and [c[0] for c in client.calls] == [1, 2]
    assert client.calls[0][1:] == (1000, {"nomeProduto": ""})
    saved = json.loads((tmp_path / catalogo.ARQUIVO).read_text())
    assert [p["nome"] for p in saved["produtos"]] == ["Abacavir", "risperidona"]  # ordem sem caixa
    assert saved["produtos"][1] == {
        "registro": "118190404",
        "idProduto": 3561242,
        "nome": "risperidona",
        "empresa": "MULTILAB",
        "cnpj": "92265552000905",
        "data": "2025-01-28",
    }
    assert catalogo.carregar(tmp_path)["atualizado"] == saved["atualizado"]
    assert catalogo.carregar(tmp_path / "nada") == {"atualizado": None, "produtos": []}
