"""Slides 1.1: transitions, tables, new shapes, alignment, find, PDF."""
import pytest
from lxml import etree
from pptx import Presentation as PptxPresentation
from pptx.util import Inches

from office.slides.layouts import make_slide, sample_presentation
from office.slides.model import SHAPES, Presentation, Shape
from office.slides.pptx_io import open_pptx, save_pptx

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def test_transitions_round_trip_and_sit_where_powerpoint_expects(tmp_path):
    pres = sample_presentation()
    for slide, name in zip(pres.slides, ("fade", "push", "none", "zoom")):
        slide.transition = name
    path = tmp_path / "t.pptx"
    save_pptx(pres, path)
    assert [s.transition for s in open_pptx(path).slides] == ["fade", "push", "none", "zoom"]
    el = PptxPresentation(path).slides[0]._element
    tags = [etree.QName(c).localname for c in el]
    assert tags.index("transition") == tags.index("clrMapOvr") + 1


def test_foreign_transitions_play_as_a_fade(tmp_path):
    src = PptxPresentation()
    s = src.slides.add_slide(src.slide_layouts[6])
    trans = etree.SubElement(s._element, P + "transition")
    etree.SubElement(trans, P + "dissolve")
    path = tmp_path / "f.pptx"
    src.save(path)
    assert open_pptx(path).slides[0].transition == "fade"


def test_tables_and_shapes_round_trip(tmp_path):
    slide = make_slide("Blank")
    table = Shape("table", 60, 80, 480, 150, text="A\tB\n1\t2\n3\t4", line="#B08D57")
    table.style.size = 16.0
    slide.shapes.append(table)
    for i, kind in enumerate(SHAPES):
        slide.shapes.append(Shape(kind, 20 + i * 90, 300, 80, 80, fill="#7A0E1B"))
    path = tmp_path / "s.pptx"
    save_pptx(Presentation([slide]), path)
    back = open_pptx(path).slides[0].shapes
    assert back[0].kind == "table" and back[0].table_cells() == [["A", "B"], ["1", "2"], ["3", "4"]]
    assert back[0].style.size == 16
    assert [s.kind for s in back[1:]] == list(SHAPES)
    # PowerPoint sees a real table.
    frame = next(s for s in PptxPresentation(path).slides[0].shapes if s.has_table)
    assert frame.table.cell(2, 1).text == "4"


def test_powerpoint_tables_open_as_tables(tmp_path):
    src = PptxPresentation()
    s = src.slides.add_slide(src.slide_layouts[6])
    t = s.shapes.add_table(2, 3, Inches(1), Inches(1), Inches(6), Inches(1)).table
    t.cell(0, 0).text, t.cell(1, 2).text = "head", "tail"
    path = tmp_path / "p.pptx"
    src.save(path)
    shape = open_pptx(path).slides[0].shapes[0]
    assert shape.kind == "table"
    assert shape.table_cells() == [["head", "", ""], ["", "", "tail"]]


def test_table_cells_pad_ragged_rows():
    assert Shape("table", 0, 0, 1, 1, text="a\tb\tc\nd").table_cells() == [
        ["a", "b", "c"], ["d", "", ""]]


# ---- the panel ----------------------------------------------------------------

pytest.importorskip("PySide6")


@pytest.fixture()
def panel():
    from PySide6.QtWidgets import QApplication
    from office import theme
    from office.slides.view import SlidesPanel
    QApplication.instance() or QApplication([])
    theme.load_fonts()
    return SlidesPanel()


def settle():
    from PySide6.QtWidgets import QApplication
    for _ in range(3):
        QApplication.processEvents()


def select(panel, shapes):
    ids = {s.id for s in shapes}
    for item in panel.shape_items():
        item.setSelected(item.shape_model.id in ids)


def test_align_distribute_and_duplicate(panel):
    panel.add_slide("Blank")
    settle()
    a = Shape("rect", 10, 10, 50, 50)
    b = Shape("rect", 200, 90, 80, 30)
    c = Shape("rect", 500, 40, 40, 40)
    panel.slide.shapes += [a, b, c]
    panel._refresh()
    select(panel, [a, b, c])
    panel.align_shapes("top")
    settle()
    assert a.y == b.y == c.y == 10
    panel.distribute("h")
    settle()
    # span 10..540 holds 170 pt of shapes, so the two gaps are 180 each
    assert b.x == pytest.approx(10 + 50 + 180)
    select(panel, [b])
    panel.align_shapes("hcenter")  # one shape: centred on the slide
    settle()
    assert b.x == pytest.approx((960 - 80) / 2)
    select(panel, [b])
    panel.duplicate_shapes()
    settle()
    assert len(panel.slide.shapes) == 4 and panel.slide.shapes[-1].x == b.x + 18
    assert panel.undo_stack.undo_text() == "Duplicate"
    for _ in range(4):
        panel.undo_stack.undo()
        settle()
    assert a.y == 10 and b.y == 90 and len(panel.slide.shapes) == 3


def test_transition_menu_and_apply_to_all(panel):
    panel.set_transition("wipe")
    settle()
    assert panel.slide.transition == "wipe" and "Wipe" in panel.status.text()
    panel.transition_to_all()
    settle()
    assert {s.transition for s in panel.pres.slides} == {"wipe"}
    panel.undo_stack.undo()
    settle()
    assert [s.transition for s in panel.pres.slides][1:] == ["none"] * 3


def test_find_and_replace_across_slides(panel):
    assert panel.find("engine", True)
    assert panel.current == 1  # "A spreadsheet with its own formula engine"
    assert panel.find("engine", True) and panel.current == 2  # "The Engine"
    assert panel.replace("engine", "Motor")
    settle()
    assert panel.pres.slides[2].title() == "The Motor"
    n = panel.replace_all("slides", "Folios")
    settle()
    assert n == 2 and panel.undo_stack.undo_text() == "Replace all"
    panel.undo_stack.undo()
    settle()
    assert "Slides" in panel.pres.slides[0].shapes[-1].text


def test_insert_table_chart_picture_and_export(panel, tmp_path):
    from office.sheets.chart import png_bytes, render_chart
    t = panel.insert_table(3, 2)
    settle()
    assert t.kind == "table" and len(t.table_cells()) == 3
    pic = panel.insert_image_data(png_bytes(render_chart("pie", "Share", ["a", "b"],
                                                         [("s", [1.0, 3.0])], 400, 300)))
    settle()
    assert pic.kind == "image" and pic.w <= 960 * 0.7
    panel.export_pdf(tmp_path / "deck.pdf")
    data = (tmp_path / "deck.pdf").read_bytes()
    assert data.startswith(b"%PDF") and data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 4
    assert panel.export_slide_png(tmp_path / "slide.png")


def test_slide_show_plays_a_transition(panel):
    from office.slides.view import SlideShow
    panel.pres.slides[1].transition = "push"
    show = SlideShow(panel.pres, 0)
    show.resize(480, 270)
    show.go(1)
    assert show._from is not None and show._kind == "push"
    show._step(0.5)
    show.grab()  # paints a half-way frame without crashing
    show._anim.stop()
    show._done()
    assert show._from is None and show.index == 1
    show.keyPressEvent(_key("B"))
    assert show.black
    show.close()


def _key(ch):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(QEvent.Type.KeyPress, getattr(Qt.Key, f"Key_{ch}"),
                     Qt.KeyboardModifier.NoModifier)
