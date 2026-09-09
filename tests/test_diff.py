from bulario.diff import diff_documents, pair_documents, render_html, summary, word_diff
from bulario.extract import Document


def test_word_diff_marks_changes():
    html, changed, ratio = word_diff("a b c", "a x c")
    assert "<del>b</del>" in html and "<ins>x</ins>" in html
    assert changed == 2 and 0 < ratio < 1


def test_pair_documents_by_similarity_not_order():
    a1 = Document({"1": "dorflex max comprimido seiscentos " * 20}, "vp")
    a2 = Document({"1": "dorflex comprimido trezentos " * 20}, "vp")
    pairs = pair_documents([a1, a2], [a2, a1])
    assert sorted(pairs) == [(0, 1), (1, 0)]


def test_pair_unmatched_documents():
    a = Document({"1": "x " * 50}, "vp")
    assert pair_documents([a], []) == [(0, None)]
    assert pair_documents([], [a]) == [(None, 0)]


def test_diff_documents_summary_and_html():
    old = [Document({"(preâmbulo)": "capa", "1": "indicado para dor", "2": "igual"}, "vp")]
    new = [Document({"(preâmbulo)": "capa v2", "1": "indicado para febre", "2": "igual"}, "vp")]
    rows = diff_documents(old, new, skip_preamble=True)
    assert [r.secao for r in rows] == ["1", "2"]
    assert summary(rows) == "1(2)"
    out = render_html(rows, "t")
    assert "<del>dor</del>" in out and "<ins>febre</ins>" in out
