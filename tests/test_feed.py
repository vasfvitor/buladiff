import json

from bulario import feed

ITEM = {
    "idProduto": 3561242,
    "numeroRegistro": "118190404",
    "nomeProduto": "risperidona",
    "expediente": "0121761258",
    "razaoSocial": "MULTILAB",
    "cnpj": "92265552000905",
    "data": "2025-01-28T15:13:10.000-0200",
    "numProcesso": "25351065474202261",
}


class FakeClient:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def search_all(self, **filtro):
        self.calls.append(filtro)
        return iter(self.items)


def test_published_sorted_and_mapped():
    other = {**ITEM, "numeroRegistro": "1", "nomeProduto": "abacavir", "data": "2025-01-27T10:00:00.000-0200"}
    items = feed.published(FakeClient([ITEM, other]), "2025-01-27", "2025-01-28")
    assert [p.nome for p in items] == ["abacavir", "risperidona"]
    assert items[1].data == "2025-01-28" and items[1].registro == "118190404"


def test_run_keeps_state_and_resumes(tmp_path):
    client = FakeClient([ITEM])
    feed.run(tmp_path, desde="2025-01-27", ate="2025-01-28", client=client, log=lambda s: None)
    state = json.loads((tmp_path / feed.STATE_FILE).read_text())
    assert state["ate"] == "2025-01-28"
    assert len(state["publicacoes"]) == 1

    feed.run(tmp_path, ate="2025-01-30", client=client, log=lambda s: None)  # retoma de 'ate'
    assert client.calls[-1]["periodoPublicacaoInicial"] == "2025-01-28"
    state = json.loads((tmp_path / feed.STATE_FILE).read_text())
    assert len(state["publicacoes"]) == 1  # mesmo expediente não duplica
