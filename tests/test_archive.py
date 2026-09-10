from pathlib import Path

from bulario.archive import VersionText, local_versions, read_curated, registros, version_path
from bulario.extract import Document


def make_vt(exp="0121761258", data="2025-01-28", tipo="vp") -> VersionText:
    return VersionText(
        registro="118190404",
        expediente=exp,
        data=data,
        situacao="Aditado ao processo",
        tipo=tipo,
        pdf_sha256="abc",
        paginas=15,
        documentos=[Document({"(preâmbulo)": "capa", "1": "indicado para", "III": "dizeres"}, tipo)],
        historico_tabela=[
            {
                "data": "-",
                "expediente": "-",
                "assunto": "10452",
                "itens": "3. QUANDO NÃO DEVO 4. O QUE DEVO SABER Dizeres legais",
                "versoes": "VP",
                "apresentacoes": "",
                "aprovacao": "",
            }
        ],
    )


def test_version_text_round_trip(tmp_path: Path):
    vt = make_vt()
    vt.save(tmp_path / "v.json")
    back = VersionText.load(tmp_path / "v.json")
    assert back == vt
    assert back.documentos[0].secoes["1"] == "indicado para"
    assert back.declarado == ["3", "4", "III"]


def test_declarado_empty_without_table():
    vt = make_vt()
    vt.historico_tabela = []
    assert vt.declarado == []


def test_local_versions_from_json(tmp_path: Path):
    out = tmp_path / "118190404"
    out.mkdir()
    for exp, data in (("0046116231", "2023-01-16"), ("0121761258", "2025-01-28")):
        for tipo in ("vp", "vps"):
            item = {"dataPublicacao": data + "T15:13:10.000-0200", "expediente": exp}
            make_vt(exp, data, tipo).save(version_path(out, item, tipo))
    (out / "meta.json").write_text("{}")
    vs = local_versions("118190404", tmp_path)
    assert [v.expediente for v in vs] == ["0046116231", "0121761258"]
    assert set(vs[0].textos) == {"vp", "vps"}
    assert vs[1].load("vps").tipo == "vps"
    assert registros(tmp_path) == ["118190404"]


def test_read_curated(tmp_path: Path):
    f = tmp_path / "registros.txt"
    f.write_text("# comentário\n118190404  # risperidona\n\n112360031\n")
    assert read_curated(f) == ["118190404", "112360031"]
    assert read_curated(tmp_path / "nao-existe.txt") == []


def test_comparavel_uses_line_extraction_against_unmarked_version():
    from bulario.archive import VersionText
    from bulario.extract import Document

    marcada = VersionText(
        "r",
        "1",
        "2025-01-01",
        "",
        "vp",
        "x",
        1,
        [Document({"1": "a\n\nb"})],
        [],
        True,
        [Document({"1": "a b"})],
    )
    linhas = VersionText("r", "2", "2025-02-01", "", "vp", "y", 1, [Document({"1": "a b c"})], [], False)
    assert marcada.comparavel(linhas)[0].secoes["1"] == "a b"
    assert marcada.comparavel(marcada)[0].secoes["1"] == "a\n\nb"
    assert linhas.comparavel(marcada)[0].secoes["1"] == "a b c"
    d = VersionText.from_dict(marcada.to_dict())
    assert d.documentos_linhas[0].secoes == {"1": "a b"} and d.marcado
