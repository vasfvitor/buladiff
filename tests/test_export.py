import json
from pathlib import Path

from bulario.archive import VersionText, version_path
from bulario.export import export
from bulario.extract import Document

PROD = {
    "idProduto": 1,
    "numeroRegistro": "118190404",
    "nomeProduto": "risperidona",
    "razaoSocial": "MULTILAB",
    "cnpj": "1",
    "numProcesso": "25351",
    "data": "2025-01-28T15:13:10.000-0200",
}


def make_archive(root: Path) -> None:
    out = root / "118190404"
    out.mkdir(parents=True)
    hist = {"historico": {"content": [{"expediente": "0121761258", "descSituacao": "Aditado ao processo"}]}}
    (out / "meta.json").write_text(json.dumps({"produto": PROD, "historico": hist}))
    for exp, data, texto, sha in (
        ("0046116231", "2023-01-16", "indicado para dor", "a"),
        ("0121761258", "2025-01-28", "indicado para febre", "b"),
        ("0200000000", "2026-01-10", "indicado para dor e febre", "c"),
        ("0121761258", "2026-03-27", "indicado para febre", "b"),  # relistagem do mesmo PDF, não adjacente
    ):
        item = {"dataPublicacao": data + "T00:00:00", "expediente": exp}
        vt = VersionText(
            "118190404", exp, data, "", "vp", sha, 1, [Document({"1": texto, "2": "igual"}, "vp")], []
        )
        vt.save(version_path(out, item, "vp"))


def test_export_produces_list_and_detail(tmp_path: Path):
    make_archive(tmp_path / "data")
    n = export(tmp_path / "data", tmp_path / "out", log=lambda s: None)
    assert n == 1
    produtos = json.loads((tmp_path / "out" / "produtos.json").read_text())
    assert produtos[0]["nome"] == "risperidona" and produtos[0]["tem_diff"] and produtos[0]["n_versoes"] == 4
    detail = json.loads((tmp_path / "out" / "produtos" / "118190404.json").read_text())
    assert [v["expediente"] for v in detail["versoes"]] == ["0046116231", "0121761258", "0200000000"]
    assert detail["versoes"][1]["situacao"] == "Aditado ao processo"
    assert detail["versoes"][1]["republicada"] == ["2026-03-27"]
    d, d2 = detail["diffs"]  # a relistagem não gera diff
    assert d["tipo"] == "vp" and d["de"] == "0046116231" and d["para"] == "0121761258"
    assert d2["de"] == "0121761258" and d2["para"] == "0200000000"
    assert d["alteradas"] == ["1"] and d["resumo"] == "1(2)"
    assert any("<ins>febre</ins>" in s["html"] for s in d["secoes"])
    assert (tmp_path / "out" / "feed.json").exists()
