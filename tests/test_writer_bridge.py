import pytest

pytest.importorskip("PySide6")
from PySide6.QtGui import QTextCursor, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from office.writer.document import Paragraph, Run  # noqa: E402
from office.writer.qt_bridge import apply_style, load_paragraphs, to_paragraphs  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def strip(paragraphs):
    return [(p.style, [(r.text, r.bold, r.italic, r.underline) for r in p.runs], p.list_id,
             p.align) for p in paragraphs]


def test_round_trip_through_qt():
    paras = [
        Paragraph("h1", [Run("Title", bold=True)], align="center"),
        Paragraph("normal", [Run("a "), Run("b", bold=True), Run(" c", italic=True)],
                  align="justify"),
        Paragraph("number", [Run("one")], 1),
        Paragraph("number", [Run("two")], 1),
        Paragraph("normal", [Run("line one\nline two")]),
        Paragraph("number", [Run("restart")], 2),
        Paragraph("bullet", [Run("dot", underline=True)], 3),
    ]
    doc = QTextDocument()
    load_paragraphs(doc, paras)
    assert strip(to_paragraphs(doc)) == strip(paras)


def test_numbered_list_after_text_restarts_at_one():
    doc = QTextDocument()
    load_paragraphs(doc, [
        Paragraph("number", [Run("a")], 1),
        Paragraph("number", [Run("b")], 1),
        Paragraph("normal", [Run("gap")]),
        Paragraph("number", [Run("c")], 2),
    ])
    last = doc.lastBlock()
    assert last.textList().itemNumber(last) == 0  # first item of its own list
    second = doc.findBlockByNumber(1)
    assert second.textList().itemNumber(second) == 1


def test_apply_style_heading_and_list_toggle():
    doc = QTextDocument()
    load_paragraphs(doc, [Paragraph("normal", [Run("hello")])])
    cursor = QTextCursor(doc)
    apply_style(cursor, "h2")
    assert to_paragraphs(doc)[0].style == "h2"
    apply_style(cursor, "bullet")
    assert to_paragraphs(doc)[0].style == "bullet"
    apply_style(cursor, "bullet")  # toggle off
    assert to_paragraphs(doc)[0].style == "normal"
    apply_style(cursor, "number")
    assert to_paragraphs(doc)[0].style == "number"
