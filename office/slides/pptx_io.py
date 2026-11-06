"""Save and open .pptx with python-pptx.

Saving writes every shape as a free-floating text box, auto shape, table or
picture on a blank layout, so what you see is what PowerPoint shows, and each
slide's transition as <p:transition>. Opening reads text (including
placeholders), the auto shapes we draw, tables, pictures and transitions;
charts and SmartArt come in as a labelled box.
"""
import io

from lxml import etree
from pptx import Presentation as PptxPresentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_COLOR_TYPE, MSO_FILL
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Pt

from .model import Presentation, Shape, Slide, TextStyle
from .render import TABLE_BAND, TABLE_HEADER

_AUTO_OUT = {
    "rect": MSO_AUTO_SHAPE_TYPE.RECTANGLE, "ellipse": MSO_AUTO_SHAPE_TYPE.OVAL,
    "rounded": MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
    "triangle": MSO_AUTO_SHAPE_TYPE.ISOSCELES_TRIANGLE,
    "diamond": MSO_AUTO_SHAPE_TYPE.DIAMOND, "star": MSO_AUTO_SHAPE_TYPE.STAR_5_POINT,
    "arrow": MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, "hexagon": MSO_AUTO_SHAPE_TYPE.HEXAGON,
}
_AUTO_IN = {v: k for k, v in _AUTO_OUT.items()}
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
# Our transition names -> the PowerPoint element (and its attributes).
_TRANSITION_XML = {"fade": ("fade", {}), "push": ("push", {"dir": "l"}),
                   "wipe": ("wipe", {"dir": "r"}), "cover": ("cover", {"dir": "l"}),
                   "zoom": ("zoom", {})}

_ALIGN_OUT = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
_ALIGN_IN = {PP_ALIGN.CENTER: "center", PP_ALIGN.RIGHT: "right"}
_ANCHOR_OUT = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}
_ANCHOR_IN = {MSO_ANCHOR.MIDDLE: "middle", MSO_ANCHOR.BOTTOM: "bottom"}
_BLANK_LAYOUT = 6


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#").upper())


# ---------------------------------------------------------------- saving --

def save_pptx(pres: Presentation, path):
    out = PptxPresentation()
    out.slide_width = Pt(pres.width)
    out.slide_height = Pt(pres.height)
    for slide in pres.slides:
        s = out.slides.add_slide(out.slide_layouts[_BLANK_LAYOUT])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = _rgb(slide.background)
        for shape in slide.shapes:
            _write_shape(s, shape)
        if slide.notes:
            s.notes_slide.notes_text_frame.text = slide.notes
        _write_transition(s, slide.transition)
    out.save(path)


def _write_transition(s, name):
    if name not in _TRANSITION_XML:
        return
    tag, attrs = _TRANSITION_XML[name]
    el = s._element
    trans = etree.SubElement(el, _P + "transition")
    trans.set("spd", "med")
    kind = etree.SubElement(trans, _P + tag)
    for k, v in attrs.items():
        kind.set(k, v)
    # The schema wants <p:transition> straight after cSld / clrMapOvr.
    el.remove(trans)
    anchor = el.find(_P + "clrMapOvr")
    if anchor is None:
        anchor = el.find(_P + "cSld")
    anchor.addnext(trans)


def _read_transition(s):
    trans = s._element.find(_P + "transition")
    if trans is None:
        return "none"
    for child in trans:
        tag = etree.QName(child).localname
        if tag in _TRANSITION_XML:
            return tag
        if tag in ("split", "dissolve", "randomBar", "blinds", "checker", "circle", "plus",
                   "wedge", "wheel", "strips", "diamond", "newsflash", "random"):
            return "fade"
    return "fade" if len(trans) == 0 else "none"


def _write_shape(s, shape: Shape):
    x, y, w, h = Pt(shape.x), Pt(shape.y), Pt(shape.w), Pt(shape.h)
    if shape.kind == "image" and shape.image:
        pic = s.shapes.add_picture(io.BytesIO(shape.image), x, y, w, h)
        pic.name = f"Picture {shape.id}"
        return
    if shape.kind == "table":
        _write_table(s, shape, x, y, w, h)
        return
    if shape.kind in _AUTO_OUT:
        sp = s.shapes.add_shape(_AUTO_OUT[shape.kind], x, y, w, h)
    else:
        sp = s.shapes.add_textbox(x, y, w, h)
    if shape.fill:
        sp.fill.solid()
        sp.fill.fore_color.rgb = _rgb(shape.fill)
    else:
        sp.fill.background()
    if shape.line:
        sp.line.color.rgb = _rgb(shape.line)
        sp.line.width = Pt(shape.line_width)
    else:
        sp.line.fill.background()
    if shape.role:
        sp.name = f"{shape.role.title()} {shape.id}"
    _write_text(sp.text_frame, shape)


def _write_text(tf, shape: Shape):
    tf.word_wrap = True
    tf.vertical_anchor = _ANCHOR_OUT.get(shape.style.valign, MSO_ANCHOR.TOP)
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, Pt(4))
    st = shape.style
    for i, line in enumerate(shape.text.split("\n") if shape.text else []):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = _ALIGN_OUT.get(st.align, PP_ALIGN.LEFT)
        if shape.bullets:
            _add_bullet(p, st.size)
        run = p.add_run()
        run.text = line
        f = run.font
        f.name, f.size = st.font, Pt(st.size)
        f.bold, f.italic, f.underline = st.bold, st.italic, st.underline
        f.color.rgb = _rgb(st.color)


def _write_table(s, shape: Shape, x, y, w, h):
    cells = shape.table_cells()
    rows, cols = len(cells), len(cells[0])
    frame = s.shapes.add_table(rows, cols, x, y, w, h)
    frame.name = f"Table {shape.id}"
    table = frame.table
    st = shape.style
    for c in range(cols):
        table.columns[c].width = int(w / cols)
    for r in range(rows):
        table.rows[r].height = int(h / rows)
        for c in range(cols):
            cell = table.cell(r, c)
            cell.fill.solid()
            band = TABLE_HEADER if r == 0 else (TABLE_BAND if r % 2 == 0 else shape.fill or "#FFFBF3")
            cell.fill.fore_color.rgb = _rgb(band)
            tf = cell.text_frame
            tf.paragraphs[0].alignment = _ALIGN_OUT.get(st.align, PP_ALIGN.LEFT)
            run = tf.paragraphs[0].add_run()
            run.text = cells[r][c]
            f = run.font
            f.name, f.size = st.font, Pt(st.size)
            f.bold = r == 0 or st.bold
            f.italic = st.italic
            f.color.rgb = _rgb("#F3E7D3" if r == 0 else st.color)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE


def _add_bullet(p, size):
    pPr = p._p.get_or_add_pPr()
    indent = int(Pt(size * 1.1))
    pPr.set("marL", str(indent))
    pPr.set("indent", str(-indent))
    bu = etree.SubElement(pPr, qn("a:buChar"))
    bu.set("char", "•")


# --------------------------------------------------------------- opening --

def open_pptx(path) -> Presentation:
    src = PptxPresentation(path)
    pres = Presentation([], src.slide_width.pt, src.slide_height.pt)
    for s in src.slides:
        slide = Slide([], _background(s))
        for sp in s.shapes:
            slide.shapes.extend(_read_shape(sp))
        if s.has_notes_slide:
            slide.notes = s.notes_slide.notes_text_frame.text
        slide.transition = _read_transition(s)
        pres.slides.append(slide)
    return pres


def _solid_color(fill):
    try:
        if fill.type == MSO_FILL.SOLID and fill.fore_color.type == MSO_COLOR_TYPE.RGB:
            return "#" + str(fill.fore_color.rgb)
    except (AttributeError, TypeError, ValueError, NotImplementedError):
        pass
    return None


def _background(s):
    for owner in (s, s.slide_layout, s.slide_layout.slide_master):
        try:
            color = _solid_color(owner.background.fill)
        except (AttributeError, KeyError):
            color = None
        if color:
            return color
    return "#FFFFFF"


def _geometry(sp):
    return tuple((v.pt if v is not None else 0.0) for v in (sp.left, sp.top, sp.width, sp.height))


def _read_shape(sp):
    x, y, w, h = _geometry(sp)
    if sp.shape_type == MSO_SHAPE_TYPE.GROUP:
        return [s for child in sp.shapes for s in _read_shape(child)]
    if sp.shape_type == MSO_SHAPE_TYPE.PICTURE:
        return [Shape("image", x, y, w, h, image=sp.image.blob)]
    if getattr(sp, "has_table", False) and sp.has_table:
        return [_read_table(sp, x, y, w, h)]
    if getattr(sp, "has_chart", False) and sp.has_chart:
        return [Shape("text", x, y, w, h, text="[chart]", line="#B08D57",
                      style=TextStyle(align="center", valign="middle"))]
    kind = "text"
    if sp.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
        try:
            auto = sp.auto_shape_type
        except (NotImplementedError, ValueError):
            auto = None
        kind = _AUTO_IN.get(auto, "rect")
    shape = Shape(kind, x, y, w, h)
    shape.role = _role(sp)
    try:
        shape.fill = _solid_color(sp.fill)
        shape.line = _solid_color(sp.line.fill)
        if shape.line and sp.line.width:
            shape.line_width = sp.line.width.pt
    except (AttributeError, NotImplementedError):
        pass
    if sp.has_text_frame:
        _read_text(sp, shape)
    return [shape]


def _read_table(sp, x, y, w, h):
    rows = [[c.text.replace("\t", " ").replace("\n", " ") for c in r.cells]
            for r in sp.table.rows]
    shape = Shape("table", x, y, w, h, text="\n".join("\t".join(r) for r in rows),
                  line="#B08D57", style=TextStyle(size=16.0))
    # Take the font from the first body cell that has text.
    for r_i, row in enumerate(sp.table.rows):
        for cell in row.cells:
            run = next((r for p in cell.text_frame.paragraphs for r in p.runs if r.text), None)
            if run is None or (r_i == 0 and len(sp.table.rows) > 1):
                continue
            f = run.font
            if f.name:
                shape.style.font = f.name
            if f.size:
                shape.style.size = f.size.pt
            try:
                if f.color.type == MSO_COLOR_TYPE.RGB:
                    shape.style.color = "#" + str(f.color.rgb)
            except AttributeError:
                pass
            return shape
    return shape


def _role(sp):
    if not sp.is_placeholder:
        # Our own files mark roles in the shape name ("Title 12", "Body 13").
        first = (sp.name or "").split(" ")[0].lower()
        return first if first in ("title", "body") else ""
    t = sp.placeholder_format.type
    if t in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
        return "title"
    if t in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.SUBTITLE):
        return "body"
    return ""


def _read_text(sp, shape: Shape):
    tf = sp.text_frame
    shape.text = "\n".join(p.text for p in tf.paragraphs)
    st = TextStyle(size=40.0 if shape.role == "title" else 18.0, color="#000000")
    first_run = next((r for p in tf.paragraphs for r in p.runs if r.text.strip()), None)
    if first_run is not None:
        f = first_run.font
        if f.name:
            st.font = f.name
        if f.size:
            st.size = f.size.pt
        st.bold, st.italic, st.underline = bool(f.bold), bool(f.italic), bool(f.underline)
        try:
            if f.color.type == MSO_COLOR_TYPE.RGB:
                st.color = "#" + str(f.color.rgb)
        except AttributeError:
            pass
    if tf.paragraphs:
        st.align = _ALIGN_IN.get(tf.paragraphs[0].alignment, "left")
    st.valign = _ANCHOR_IN.get(tf.vertical_anchor,
                               "middle" if shape.role == "title" else "top")
    shape.style = st
    first = tf.paragraphs[0]._p.pPr if tf.paragraphs else None
    has_bu_char = first is not None and first.find(qn("a:buChar")) is not None
    shape.bullets = has_bu_char or (
        sp.is_placeholder and shape.role == "body"
        and sp.placeholder_format.type != PP_PLACEHOLDER.SUBTITLE)
