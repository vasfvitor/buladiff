from bulario.history import History, HistoryEntry, normalize_rows

HEADER = [
    ["Dados da submissão eletrônica", "", "", "Dados da petição", "", "", "", "Dados das alterações", "", ""],
    [
        "Data do expediente",
        "Nº do expediente",
        "Assunto",
        "Data",
        "Nº",
        "Assunto",
        "Data de aprovação",
        "Itens de bula",
        "Versões (VP/VPS)",
        "Apresentações relacionadas",
    ],
]


def test_rows_with_continuation_lines():
    rows = HEADER + [
        [
            "27/11/2018",
            "1120093/18-6",
            "10459 - GENÉRICO - Inclusão",
            "NA",
            "NA",
            "NA",
            "NA",
            "Versão inicial",
            "VP/VPS",
            "1 mg/mL",
        ],
        [
            "11/01/2019",
            "0025435/19-5",
            "10452 – Notificação",
            "NA",
            "NA",
            "NA",
            "NA",
            "5. Advertências e Precauções",
            "VPS",
            "1 mg/mL",
        ],
        ["", "", "", "", "", "", "", "6. Como devo usar este\nmedicamento", "VP", ""],
        [
            "-",
            "-",
            "10452 – Notificação",
            "-",
            "-",
            "-",
            "-",
            "3. QUANDO NÃO DEVO USAR? III - DIZERES LEGAIS",
            "VP",
            "1 mg/mL",
        ],
    ]
    entries = normalize_rows(rows)
    assert [e.data for e in entries] == ["27/11/2018", "11/01/2019", "-"]
    assert entries[1].itens == "5. Advertências e Precauções 6. Como devo usar este medicamento"
    assert entries[1].versoes == "VPS VP"
    assert entries[1].secoes == ["5", "6"]
    assert entries[2].secoes == ["3", "III"]


def test_secoes_parses_numbers_roman_and_dizeres():
    e = HistoryEntry("", "", "", "4) O QUE DEVO SABER 9. REAÇÕES Dizeres legais 4. repetido", "", "")
    assert e.secoes == ["4", "9", "III"]


def test_empty_and_short_rows_are_ignored():
    assert normalize_rows([["", None, ""], ["Data do expediente", "x"]]) == []


def test_by_expediente_matches_digits_only():
    h = History([HistoryEntry("11/01/2019", "0025435/19-5", "", "5. X", "VPS", "")])
    assert h.by_expediente("0025435195") is h.entries[0]
    assert h.by_expediente("0000000000") is None
    assert h.by_expediente("") is None
