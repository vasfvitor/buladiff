"""Blocos a partir da árvore de estrutura, com elementos e caracteres falsos (sem PDF)."""

from pdfminer.psparser import LIT

from bulario.tagged import blocos, linhas, palavras

ROOT: dict = {"Type": LIT("StructTreeRoot")}
LARGURA = 5.0  # pt por caractere nos textos falsos


def el(tipo: str, pai: dict) -> dict:
    return {"S": LIT(tipo), "P": pai}


def cs(texto: str, x0: float = 0, top: float = 0) -> list[dict]:
    """Caracteres de um texto, 5 pt cada, a partir de x0 (espaços incluídos)."""
    return [
        {"text": ch, "x0": x0 + i * LARGURA, "x1": x0 + (i + 1) * LARGURA, "top": top}
        for i, ch in enumerate(texto)
    ]


def texto(ws: list[dict]) -> list[str]:
    return [w["text"] for w in ws]


def test_paragraphs_and_cross_page_paragraph():
    h, p1, p2 = el("H1", ROOT), el("P", ROOT), el("P", ROOT)
    pagina1 = ([(0, cs("1. INDICAÇÕES")), (1, cs("Começa aqui e", top=20))], [h, p1])
    pagina2 = ([(0, cs("termina aqui.")), (1, cs("Outro parágrafo.", top=20))], [p1, p2])
    assert blocos([pagina1, pagina2], {}) == [
        "1. INDICAÇÕES",
        "Começa aqui e termina aqui.",
        "Outro parágrafo.",
    ]


def test_list_item_joins_label_and_nested_list_is_separate():
    # o Word aninha os itens seguintes dentro do primeiro: "6." fica dentro do LBody do "1."
    lista = el("L", ROOT)
    item1 = el("LI", lista)
    corpo1 = el("LBody", item1)
    item6 = el("LI", el("L", corpo1))
    trechos = [
        (0, cs("1.")),
        (1, cs("PARA QUE SERVE?", x0=20)),
        (2, cs("Corpo da seção 1.", top=20)),
        (3, cs("6.", top=40)),
        (4, cs("COMO USAR?", x0=20, top=40)),
    ]
    donos = [el("Lbl", item1), corpo1, el("P", ROOT), el("Lbl", item6), el("LBody", item6)]
    assert blocos([(trechos, donos)], {}) == ["1. PARA QUE SERVE?", "Corpo da seção 1.", "6. COMO USAR?"]


def test_table_rows_become_visual_lines():
    # uma "linha" do Word com células altas: o texto de cada célula vem inteiro, e as linhas visuais
    # são remontadas pela posição, como na página
    tabela = el("Table", ROOT)
    linha = el("TR", tabela)
    c1, c2 = el("TD", linha), el("TD", linha)
    trechos = [
        (0, cs("Antes")),
        (1, cs("Sinusite", 0, 20) + cs("Anemia", 0, 32)),  # célula 1: duas linhas
        (2, cs("2,1", 100, 20) + cs("0,5", 100, 32)),  # célula 2: duas linhas
        (3, cs("Depois", top=50)),
    ]
    donos = [el("P", ROOT), el("P", c1), el("P", c2), el("P", ROOT)]
    assert blocos([(trechos, donos)], {}) == ["Antes", "Sinusite 2,1", "Anemia 0,5", "Depois"]


def test_words_split_across_marked_content_are_joined():
    # o Word troca de trecho no meio da palavra ("l" + "osartana") e no hífen ("placebo" + "-controlled")
    p = el("P", ROOT)
    trechos = [(0, cs("l")), (1, cs("osartana", 5)), (2, cs(" placebo", 45)), (3, cs("-controlled", 85))]
    assert blocos([(trechos, [p, p, p, p])], {}) == ["losartana placebo-controlled"]


def test_palavras_split_on_space_char_line_change_or_gap():
    assert texto(palavras(cs("mais lentos"))) == ["mais", "lentos"]
    assert texto(palavras(cs("ab") + cs("cd", 10.5))) == ["abcd"]  # vão de 0,5 pt: junta
    assert texto(palavras(cs("ab") + cs("cd", 20))) == ["ab", "cd"]  # vão de 10 pt: separa
    assert texto(palavras(cs("ab") + cs("cd", 10, 12))) == ["ab", "cd"]  # outra linha


def test_linhas_orders_by_position():
    ws = palavras(cs("b", 50, 0) + cs("a", 0, 1) + cs("c", 0, 30))
    assert linhas(ws) == ["a b", "c"]


def test_role_map_and_content_outside_tree():
    titulo = el("Title", ROOT)
    trechos = [(0, cs("Título")), (1, cs("rodapé fora da árvore")), (7, cs("sem dono"))]
    assert blocos([(trechos, [titulo, None])], {"Title": LIT("H1")}) == ["Título"]
