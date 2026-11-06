import docx

from office.writer.document import Paragraph, Run
from office.writer.docx_io import open_docx, save_docx


def sample():
    return [
        Paragraph("h1", [Run("Title", bold=True)], align="center"),
        Paragraph("normal", [Run("Plain "), Run("bold", bold=True), Run(" and "),
                             Run("italic", italic=True), Run(" "), Run("under", underline=True)]),
        Paragraph("bullet", [Run("one")], list_id=1),
        Paragraph("bullet", [Run("two")], list_id=1),
        Paragraph("h2", [Run("Steps", bold=True)]),
        Paragraph("number", [Run("first")], list_id=2),
        Paragraph("number", [Run("second")], list_id=2),
        Paragraph("normal", [Run("break")]),
        Paragraph("number", [Run("again")], list_id=3),
    ]


def test_round_trip(tmp_path):
    path = tmp_path / "t.docx"
    save_docx(sample(), path)
    back = open_docx(path)
    assert [p.style for p in back] == [p.style for p in sample()]
    assert [p.align for p in back] == [p.align for p in sample()]
    assert [p.text for p in back] == [p.text for p in sample()]
    runs = back[1].runs
    assert [(r.text, r.bold, r.italic, r.underline) for r in runs] == [
        ("Plain ", False, False, False), ("bold", True, False, False),
        (" and ", False, False, False), ("italic", False, True, False),
        (" ", False, False, False), ("under", False, False, True),
    ]
    # Lists: the two numbered lists stay separate.
    assert back[2].list_id == back[3].list_id
    assert back[5].list_id == back[6].list_id
    assert back[8].list_id != back[5].list_id


def test_word_sees_styles_and_restarted_numbering(tmp_path):
    path = tmp_path / "t.docx"
    save_docx(sample(), path)
    d = docx.Document(path)
    assert [p.style.name for p in d.paragraphs][:3] == ["Heading 1", "Normal", "List Bullet"]
    first, second = d.paragraphs[5], d.paragraphs[8]
    assert first.style.name == second.style.name == "List Number"
    # The second numbered list has its own numId with a startOverride of 1.
    numpr = second._p.pPr.numPr
    assert numpr is not None
    numbering = d.part.numbering_part.element
    num = next(n for n in numbering.num_lst if n.numId == numpr.numId.val)
    assert num.lvlOverride_lst[0].startOverride.val == 1


def test_reads_word_style_list_paragraphs(tmp_path):
    # Word often writes lists as "List Paragraph" + a numId instead of List Bullet.
    path = tmp_path / "w.docx"
    d = docx.Document()
    p = d.add_paragraph("from word", style="List Bullet")
    numpr = d.styles["List Bullet"].element.pPr.numPr
    p.style = d.styles["List Paragraph"]
    new = p._p.get_or_add_pPr().get_or_add_numPr()
    new.get_or_add_ilvl().val = 0
    new.get_or_add_numId().val = numpr.numId.val
    d.save(path)
    assert open_docx(path)[-1].style == "bullet"


def test_house_style_fonts(tmp_path):
    path = tmp_path / "t.docx"
    save_docx(sample(), path)
    d = docx.Document(path)
    assert d.styles["Heading 1"].font.name == "Alegreya SC"
    assert d.styles["Normal"].font.name == "EB Garamond"
