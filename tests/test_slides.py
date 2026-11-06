import io

import pytest
from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt

from office.slides.commands import (
    AddShapeCommand, AddSlideCommand, DeleteShapesCommand, DeleteSlideCommand,
    MoveSlideCommand, ReorderShapeCommand, set_attrs,
)
from office.slides.layouts import LAYOUTS, make_slide, sample_presentation
from office.slides.model import Presentation, Shape
from office.slides.pptx_io import open_pptx, save_pptx
from office.undo import UndoStack


def test_layouts_build():
    for name in LAYOUTS:
        make_slide(name)
    assert make_slide("Title", "Hello").title() == "Hello"


def test_slide_commands_undo_redo():
    pres, stack = Presentation([make_slide("Title")]), UndoStack()
    stack.push(AddSlideCommand(pres, 1, make_slide("Blank")))
    stack.push(AddSlideCommand(pres, 2, make_slide("Title and Content", "Third")))
    stack.push(MoveSlideCommand(pres, 2, 0))
    assert pres.slides[0].title() == "Third"
    stack.push(DeleteSlideCommand(pres, 0))
    assert len(pres.slides) == 2
    stack.undo(); stack.undo()
    assert len(pres.slides) == 3 and pres.slides[2].title() == "Third"
    stack.redo(); stack.redo()
    assert len(pres.slides) == 2


def test_shape_commands_and_merging_nudges():
    slide, stack = make_slide("Blank"), UndoStack()
    a, b = Shape("rect", 0, 0, 10, 10), Shape("ellipse", 5, 5, 10, 10)
    stack.push(AddShapeCommand(slide, a))
    stack.push(AddShapeCommand(slide, b))
    stack.push(ReorderShapeCommand(slide, b, to_front=False))
    assert slide.shapes == [b, a]
    for _ in range(3):
        stack.push(set_attrs([(a, "x", a.x + 1)], "Nudge", merge_key=("nudge", a.id)))
    assert a.x == 3 and len(stack) == 4
    stack.undo()
    assert a.x == 0
    stack.push(set_attrs([(a.style, "size", 40.0), (a, "text", "hi")], "Format"))
    stack.push(DeleteShapesCommand(slide, [a, b]))
    assert slide.shapes == []
    stack.undo()
    assert slide.shapes == [b, a]
    stack.undo()
    assert a.style.size == 22.0 and a.text == ""
    assert set_attrs([(a, "x", a.x)], "noop") is None


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 3), (122, 14, 27)).save(buf, "PNG")
    return buf.getvalue()


def test_pptx_round_trip(tmp_path):
    pres = sample_presentation()
    pres.slides[1].notes = "Speaker notes"
    pres.slides[1].shapes.append(Shape("ellipse", 700, 300, 100, 80, fill="#7A0E1B",
                                       text="Seal", line=None))
    try:
        pres.slides[1].shapes.append(Shape("image", 10, 10, 40, 30, image=_png()))
    except ImportError:
        pass
    path = tmp_path / "deck.pptx"
    save_pptx(pres, path)

    back = open_pptx(path)
    assert len(back.slides) == len(pres.slides)
    assert back.width == pytest.approx(960) and back.height == pytest.approx(540)
    assert [s.title() for s in back.slides] == [s.title() for s in pres.slides]
    assert back.slides[2].background.upper() == pres.slides[2].background.upper()
    assert back.slides[1].notes == "Speaker notes"
    orig = pres.slides[1].shapes
    got = back.slides[1].shapes
    assert [s.kind for s in got] == [s.kind for s in orig]
    body = got[2]
    assert body.bullets and body.text == orig[2].text
    assert body.style.font == "EB Garamond" and body.style.size == 24
    assert [s.role for s in got] == [s.role for s in orig]
    assert not got[0].bullets
    title = got[0]
    assert title.style.color.upper() == "#7A0E1B" and title.style.valign == "middle"
    seal = got[3]
    assert seal.fill.upper() == "#7A0E1B" and seal.line is None
    assert (seal.x, seal.y, seal.w, seal.h) == pytest.approx((700, 300, 100, 80))


def test_opens_a_deck_made_with_placeholders(tmp_path):
    src = PptxPresentation()
    s = src.slides.add_slide(src.slide_layouts[1])  # Title and Content
    s.shapes.title.text = "From PowerPoint"
    s.placeholders[1].text_frame.text = "Point one"
    s.shapes.add_table(2, 2, Inches(1), Inches(5), Inches(4), Inches(1)).table.cell(0, 0).text = "x"
    path = tmp_path / "pp.pptx"
    src.save(path)
    pres = open_pptx(path)
    shapes = pres.slides[0].shapes
    assert shapes[0].role == "title" and shapes[0].text == "From PowerPoint"
    assert shapes[1].role == "body" and shapes[1].bullets
    assert shapes[2].text.startswith("x")
    assert shapes[0].w > 0
