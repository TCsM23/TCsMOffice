"""Writer 1.1: run formatting, tables, pictures, find and replace."""
import docx
import pytest

pytest.importorskip("PySide6")
from PySide6.QtGui import QColor, QImage, QTextCursor, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from office.writer.docx_io import open_docx, save_docx  # noqa: E402
from office.writer.document import Image, Paragraph, Run, Table  # noqa: E402
from office.writer.qt_bridge import load_paragraphs, to_paragraphs  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def png(w=40, h=20):
    from PySide6.QtCore import QBuffer, QIODevice
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#7A0E1B"))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def rich():
    return [
        Paragraph("normal", [
            Run("plain "),
            Run("gothic", font="Grenze Gotisch", size=20.0, color="#7A0E1B"),
            Run(" marked", highlight="#F3E2A9", strike=True),
        ]),
        Table.from_text([["Module", "Format"], ["Sheets", ".xlsx"], ["Writer", ".docx"]]),
        Image(png(), 60.0, 30.0, "center"),
        Paragraph("normal", [Run("after")]),
    ]


def runs(p):
    return [(r.text, r.font, r.size, r.color, r.highlight, r.strike) for r in p.runs]


def test_docx_round_trip_of_runs_tables_and_images(tmp_path):
    path = tmp_path / "rich.docx"
    save_docx(rich(), path)
    back = open_docx(path)
    assert [type(b).__name__ for b in back] == ["Paragraph", "Table", "Image", "Paragraph"]
    assert runs(back[0]) == runs(rich()[0])
    assert back[1].text == rich()[1].text
    img = back[2]
    assert img.data == rich()[2].data
    assert (img.width, img.height) == pytest.approx((60, 30), abs=0.5)
    assert img.align == "center"
    # Word sees a real table with gilt borders and real run properties.
    d = docx.Document(path)
    assert len(d.tables) == 1 and d.tables[0].cell(2, 1).text == ".docx"
    borders = d.tables[0]._tbl.tblPr.xpath("./w:tblBorders/w:top")
    assert borders and borders[0].get(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}color") == "B08D57"
    r = d.paragraphs[0].runs[1]
    assert r.font.name == "Grenze Gotisch" and r.font.size.pt == 20
    assert str(r.font.color.rgb) == "7A0E1B"


def test_qt_round_trip_of_runs_tables_and_images():
    doc = QTextDocument()
    load_paragraphs(doc, rich())
    back = to_paragraphs(doc)
    assert [type(b).__name__ for b in back] == ["Paragraph", "Table", "Image", "Paragraph"]
    assert runs(back[0]) == runs(rich()[0])
    assert back[1].text == rich()[1].text
    assert back[2].data == rich()[2].data
    assert (back[2].width, back[2].height) == pytest.approx((60, 30), abs=0.5)


def test_reads_word_highlighter_colours(tmp_path):
    from docx.enum.text import WD_COLOR_INDEX
    d = docx.Document()
    d.add_paragraph().add_run("hi").font.highlight_color = WD_COLOR_INDEX.YELLOW
    path = tmp_path / "hl.docx"
    d.save(path)
    assert open_docx(path)[-1].runs[0].highlight == "#FFFF00"


@pytest.fixture()
def writer():
    from office import theme
    from office.writer.view import WriterPanel
    theme.load_fonts()
    w = WriterPanel()
    w.load([Paragraph("normal", [Run("the cat and the hat and the bat")])])
    return w


def test_replace_all_is_one_undo_step(writer):
    assert writer.replace_all("at", "og", False, False) == 3
    assert writer.editor.toPlainText() == "the cog and the hog and the bog"
    assert writer.undo_stack.undo_text() == "Replace all" and len(writer.undo_stack) == 1
    writer.undo_stack.undo()
    assert writer.editor.toPlainText() == "the cat and the hat and the bat"


def test_find_wraps_and_replace_only_touches_a_match(writer):
    assert writer.find("THE", True, False, False)
    assert writer.editor.textCursor().selectedText() == "the"
    assert not writer.find("THE", True, True, False)  # match case
    assert not writer.replace("dog", "x")             # selection is not "dog"
    assert writer.find("and the", True)
    assert writer.replace("and the", "&")
    assert writer.editor.toPlainText().count("&") == 1
    assert writer.find("hat", whole=True) and not writer.find("ha", whole=True)


def test_font_size_colour_and_clear(writer):
    ed = writer.editor
    c = ed.textCursor()
    c.setPosition(4)
    c.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    writer.set_font("Grenze Gotisch")
    writer.set_size("28")
    writer.set_text_color("#7A0E1B")
    writer.set_highlight("#F3E2A9")
    cat = next(r for r in to_paragraphs(ed.document())[0].runs if r.text == "cat")
    assert (cat.font, cat.size, cat.color, cat.highlight) == (
        "Grenze Gotisch", 28.0, "#7A0E1B", "#F3E2A9")
    assert writer.undo_stack.undo_text() == "Highlight"
    writer.set_highlight(None)
    writer.clear_formatting()
    p = to_paragraphs(ed.document())[0]
    assert [r.text for r in p.runs] == ["the cat and the hat and the bat"]
    assert runs(p)[0][1:] == (None, None, None, None, False)


def test_insert_table_picture_and_table_rows(writer):
    ed = writer.editor
    ed.moveCursor(QTextCursor.MoveOperation.End)
    table = writer.insert_table(2, 2)
    assert table.rows() == 2 and writer.undo_stack.undo_text() == "Insert table"
    assert writer.table_op("row", 1) and table.rows() == 3
    assert writer.table_op("col", 1) and table.columns() == 3
    assert writer.table_op("del_row") and table.rows() == 2
    ed.moveCursor(QTextCursor.MoveOperation.End)
    assert writer.insert_picture_data(png())
    kinds = [type(b).__name__ for b in to_paragraphs(ed.document())]
    assert kinds == ["Paragraph", "Table", "Image"]
    writer.insert_ornament()
    assert "❦" in ed.toPlainText()
    for _ in range(len(writer.undo_stack)):
        writer.undo_stack.undo()
    assert [type(b).__name__ for b in to_paragraphs(ed.document())] == ["Paragraph"]
