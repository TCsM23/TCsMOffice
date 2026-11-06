"""Drive the real widgets offscreen. No window is shown."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from office.app import MainWindow, create_app  # noqa: E402


@pytest.fixture(scope="module")
def window():
    create_app([])
    w = MainWindow()
    w.show()
    return w


def settle():
    QApplication.processEvents()
    QApplication.processEvents()


def test_sheet_edit_undo_redo(window):
    model, stack = window.sheets.model, window.sheets.undo_stack
    model.setData(model.index(1, 1), "5")  # B2: 4 -> 5
    assert model.sheet.display("D8") == "1731.52"
    assert "edited" in window.file_label.text()
    assert window.undo_btn.isEnabled() and "B2" in window.undo_btn.toolTip()
    window.undo_btn.click()
    assert model.sheet.display("D8") == "1597.12"
    assert not window.sheets.modified
    window.redo_btn.click()
    assert model.sheet.display("B2") == "5"


def test_side_panel_follows_selection(window):
    window.sheets.table.setCurrentIndex(window.sheets.model.index(7, 3))  # D8
    assert window.sheets.panel.title.text() == "Cell D8"
    assert window.sheets.panel.plan.text() == "Nothing to recalc"
    window.sheets.table.setCurrentIndex(window.sheets.model.index(5, 3))  # D6
    assert "D7" in window.sheets.panel.plan.text()


def test_copy_paste_shifts_formulas_and_is_one_undo_step(window):
    p = window.sheets
    p.table.setCurrentIndex(p.model.index(1, 3))  # D2 = =B2*C2
    p.copy()
    p.table.setCurrentIndex(p.model.index(1, 5))  # F2
    p.paste()
    assert p.model.sheet.raw("F2") == "=D2*E2"
    QGuiApplication.clipboard().setText("1\t2\n3\t4")  # from another app
    p.table.setCurrentIndex(p.model.index(20, 0))
    p.paste()
    assert p.model.sheet.display("B22") == "4"
    p.undo_stack.undo()
    assert p.model.sheet.raw("B22") == ""
    p.undo_stack.undo()
    assert p.model.sheet.raw("F2") == ""


def test_writer_undo_goes_through_our_stack(window):
    window.switch_to(1)
    ed, stack = window.writer.editor, window.writer.undo_stack
    assert not stack.can_undo()
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    QTest.keyClicks(ed, " fin")
    cursor = ed.textCursor()
    cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.KeepAnchor, 3)
    ed.setTextCursor(cursor)
    window.writer.bold.click()
    assert stack.undo_text() == "Bold"
    QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not ed.toPlainText().endswith("fin")
    assert not window.writer.modified
    stack.redo()
    assert ed.toPlainText().endswith(" fin")


def test_save_and_reopen_all_three(window, tmp_path):
    window.sheets.save_file(tmp_path / "s.xlsx")
    window.sheets.open_file(tmp_path / "s.xlsx")
    assert window.sheets.model.sheet.raw("D8") == "=D6+D7"
    window.writer.save_file(tmp_path / "w.docx")
    window.writer.open_file(tmp_path / "w.docx")
    from office.writer.qt_bridge import to_paragraphs
    paras = to_paragraphs(window.writer.editor.document())
    assert paras[0].style == "h1" and paras[0].align == "center"
    window.writer.export_pdf(tmp_path / "w.pdf")
    assert (tmp_path / "w.pdf").read_bytes().startswith(b"%PDF")
    window.slides.save_file(tmp_path / "d.pptx")
    window.slides.open_file(tmp_path / "d.pptx")
    assert len(window.slides.pres.slides) == 4


def test_slides_editing_with_undo(window):
    window.switch_to(2)
    p = window.slides
    n = len(p.pres.slides)
    p.add_slide("Title and Content")
    settle()
    assert len(p.pres.slides) == n + 1 and p.current == 1
    p.insert_shape("ellipse")
    settle()
    assert p.slide.shapes[-1].kind == "ellipse"
    assert [s.kind for s in p.selected_shapes()] == ["ellipse"]
    p.nudge(5, 0); p.nudge(5, 0)
    settle()
    assert p.undo_stack.undo_text() == "Move"
    p.format_shapes("size", 30.0, "Font size")
    p.set_shape_attr("fill", "#22090D", "Fill")
    settle()
    for _ in range(4):
        p.undo_stack.undo()
        settle()
    assert p.slide.shapes[-1].kind != "ellipse"
    p.undo_stack.undo()
    settle()
    assert len(p.pres.slides) == n


def test_slides_text_edit_and_present(window):
    p = window.slides
    item = next(i for i in p.shape_items() if i.shape_model.role == "title")
    p.begin_text_edit(item)
    p._editor.setPlainText("Renamed")
    p.finish_text_edit()
    settle()
    assert p.slide.title() == "Renamed"
    p.present()
    p.show_window.go(1)
    p.show_window.close()
