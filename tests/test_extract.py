from bulario.extract import Document, split_documents, strip_running

VP = [
    "I - IDENTIFICAÇÃO DO MEDICAMENTO",
    "produto x",
    "APRESENTAÇÕES",
    "Comprimidos 10 mg. " * 20,
    "II - INFORMAÇÕES AO PACIENTE",
    "1. PARA QUE ESTE MEDICAMENTO É INDICADO?",
    "Indicado para dor. " * 30,
    "2. COMO ESTE MEDICAMENTO FUNCIONA?",
    "Funciona assim. " * 30,
    "III – DIZERES LEGAIS:",
    "Registro 1.2345.6789 " * 10,
]
HIST = [
    "Histórico de alteração para a bula",
    "Dados da submissão eletrônica",
    "9. REAÇÕES ADVERSAS",  # a tabela cita títulos de seção
    "4. CONTRAINDICAÇÕES",
]


def test_single_vp():
    docs = split_documents(VP)
    assert len(docs) == 1
    d = docs[0]
    assert d.tipo == "vp"
    assert list(d.secoes) == ["(preâmbulo)", "I", "II", "1", "2", "III"]
    assert d.secoes["1"].startswith("Indicado para dor.")


def test_history_table_is_dropped_and_second_doc_reopens():
    docs = split_documents(VP + HIST + VP)
    assert len(docs) == 2
    assert all("REAÇÕES" not in " ".join(d.secoes.values()) for d in docs)


def test_document_without_identificacao_splits_on_apresentacoes():
    body = VP[2:]  # começa em APRESENTAÇÕES, sem 'IDENTIFICAÇÃO'
    docs = split_documents(body + body)
    assert len(docs) == 2


def test_vps_heading_without_question_mark():
    lines = [
        "IDENTIFICAÇÃO DO MEDICAMENTO",
        "x",
        "1. INDICAÇÕES",
        "Texto. " * 200,
        "4) CONTRAINDICAÇÕES",
        "Y. " * 200,
    ]
    (d,) = split_documents(lines)
    assert d.tipo == "vps"
    assert set(d.secoes) >= {"I", "1", "4"}


def test_out_of_order_fragment_is_discarded():
    frag = ["9. REAÇÕES ADVERSAS", "a " * 600, "4. CONTRAINDICAÇÕES", "b " * 600]
    assert split_documents(frag) == []


def test_strip_running_header_with_version_number():
    # dígitos são mascarados na comparação: "V8"/"V9" e "1 de 3"/"2 de 3" contam como a mesma linha
    corpo = ["indicado para dor", "tome um comprimido", "guarde em local seco"]
    pages = [
        ["produto_VP_V8", "1. PARA QUE ESTE MEDICAMENTO É INDICADO?", corpo[i], f"- {i + 1} de 3 -"]
        for i in range(3)
    ]
    assert strip_running(pages) == [["1. PARA QUE ESTE MEDICAMENTO É INDICADO?", corpo[i]] for i in range(3)]


def test_strip_running_keeps_headings_that_repeat():
    # três apresentações, cada uma abrindo página com o mesmo título: o título fica, o nome repetido não
    pages = [["I - IDENTIFICAÇÃO DO MEDICAMENTO", nome] for nome in ("comprimido", "gotas", "injetável")]
    assert strip_running(pages) == pages


def test_document_properties():
    d = Document({"(preâmbulo)": "", "1": "a", "2": "b"}, "vp")
    assert d.ordenado and d.tamanho == 2
