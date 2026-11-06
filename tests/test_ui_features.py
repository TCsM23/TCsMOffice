"""The 1.1 features driven through the real main window, offscreen."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from office.app import MainWindow, create_app  # noqa: E402


@pytest.fixture()
def window(monkeypatch):
    create_app([])
    # Any "discard changes?" question answers Yes, so tests never block.
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    w = MainWindow()
    w.show()
    yield w
    w.close()


def settle():
    QApplication.processEvents()
    QApplication.processEvents()


def test_sample_sheet_shows_formats(window):
    m = window.sheets.model
    from PySide6.QtCore import Qt
    assert m.data(m.index(7, 3)) == "1,597.12"          # "#,##0.00"
    assert m.data(m.index(0, 0), Qt.ItemDataRole.FontRole).bold()


def test_sheets_toolbar_formats_sorts_and_charts(window):
    p = window.sheets
    m = p.model
    p.table.setCurrentIndex(m.index(1, 1))
    p.format_selection("Fill", fill="#EFDDB0")
    assert m.formats[(1, 1)].fill == "#EFDDB0"
    assert p.undo_stack.undo_text() == "Fill"
    p.sort(descending=True, block=(1, 0, 4, 3), key_col=1, header=False)
    assert m.sheet.raw("A2") == "Ballpens" and m.sheet.value("D2") == 96
    assert m.sheet.raw("A4") == "Bond paper (ream)"     # qty 12, 10, 4, 2
    assert m.formats[(3, 1)].fill == "#EFDDB0"          # its fill moved with it
    p.undo_stack.undo()
    assert m.sheet.raw("A2") == "Bond paper (ream)"
    p.table.setCurrentIndex(m.index(2, 0))
    p.insert("row", before=True)
    assert m.sheet.raw("A4") == "Printer ink" and m.sheet.raw("D7") == "=SUM(D2:D6)"
    p.undo_stack.undo()
    assert m.sheet.raw("D6") == "=SUM(D2:D5)"
    p.table.setCurrentIndex(m.index(1, 0))
    dialog = p.show_chart()
    assert dialog.canvas.categories[:2] == ["Bond paper (ream)", "Printer ink"]
    dialog.slides_btn.click()                           # chart goes to Slides
    settle()
    assert window.stack.currentIndex() == 2
    assert window.slides.slide.shapes[-1].kind == "image"
    assert window.slides.undo_stack.undo_text() == "Insert chart"
    dialog.close()


def test_new_open_by_extension_and_pdf_everywhere(window, tmp_path):
    window.switch_to(1)
    window.writer.save_file(tmp_path / "a.docx")
    window.switch_to(2)
    window.slides.save_file(tmp_path / "b.pptx")
    window.switch_to(0)
    window.sheets.save_file(tmp_path / "c.csv")
    assert window.open_file(str(tmp_path / "a.docx")) and window.stack.currentIndex() == 1
    assert window.open_file(str(tmp_path / "b.pptx")) and window.stack.currentIndex() == 2
    assert window.open_file(str(tmp_path / "c.csv")) and window.stack.currentIndex() == 0
    assert window.sheets.model.sheet.raw("A2") == "Bond paper (ream)"
    for i in range(3):
        window.switch_to(i)
        out = tmp_path / f"m{i}.pdf"
        window.export_pdf(str(out))
        assert out.read_bytes().startswith(b"%PDF")
    window.switch_to(1)
    window.new_file()
    assert window.writer.editor.toPlainText() == "" and window.writer.path is None
    window.switch_to(0)
    window.new_file()
    assert not window.sheets.model.sheet.cells
    window.switch_to(2)
    window.new_file()
    assert len(window.slides.pres.slides) == 1


def test_find_shortcut_opens_the_bar_for_each_module(window):
    for i in range(3):
        window.switch_to(i)
        window.current().open_find(True)
        assert window.current().find_bar.isVisible()
        window.current().find_bar.close_bar()
        assert not window.current().find_bar.isVisible()


def test_sheet_find_bar_replace_all(window):
    p = window.sheets
    p.find_bar.open_bar(True)
    p.find_bar.find_edit.setText("Folders")
    p.find_bar.replace_edit.setText("Binders")
    p.find_bar.replace_all()
    assert p.model.sheet.raw("A4") == "Binders"
    assert p.find_bar.status.text() == "1 replaced"
    p.find_bar.find_edit.setText("nothing here")
    p.find_bar.find()
    assert p.find_bar.status.text() == "Not found"
