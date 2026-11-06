"""Convert between the document model and .docx using python-docx."""
import io

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from .document import Image, Paragraph, Run, Table

# Word's fixed highlighter colours, for reading files that use them.
_HIGHLIGHTS = {
    WD_COLOR_INDEX.YELLOW: "#FFFF00", WD_COLOR_INDEX.BRIGHT_GREEN: "#00FF00",
    WD_COLOR_INDEX.TURQUOISE: "#00FFFF", WD_COLOR_INDEX.PINK: "#FF00FF",
    WD_COLOR_INDEX.BLUE: "#0000FF", WD_COLOR_INDEX.RED: "#FF0000",
    WD_COLOR_INDEX.DARK_BLUE: "#000080", WD_COLOR_INDEX.TEAL: "#008080",
    WD_COLOR_INDEX.GREEN: "#008000", WD_COLOR_INDEX.VIOLET: "#800080",
    WD_COLOR_INDEX.DARK_RED: "#800000", WD_COLOR_INDEX.DARK_YELLOW: "#808000",
    WD_COLOR_INDEX.GRAY_50: "#808080", WD_COLOR_INDEX.GRAY_25: "#C0C0C0",
    WD_COLOR_INDEX.BLACK: "#000000", WD_COLOR_INDEX.WHITE: "#FFFFFF",
}
GILT_HEX = "B08D57"

_STYLE_TO_DOCX = {
    "normal": "Normal",
    "h1": "Heading 1",
    "h2": "Heading 2",
    "h3": "Heading 3",
    "bullet": "List Bullet",
    "number": "List Number",
}

_ALIGN_TO_DOCX = {
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}
_ALIGN_FROM_DOCX = {v: k for k, v in _ALIGN_TO_DOCX.items()}

# The house style, written into the .docx so Word shows the same look.
# If the fonts aren't installed, Word quietly falls back to its defaults.
BODY_FONT = "EB Garamond"
HEADING_FONT = "Alegreya SC"
HEADING_RGB = RGBColor(0x8B, 0x10, 0x1E)


def _apply_house_style(doc):
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(12)
    for level, size in ((1, 22), (2, 16), (3, 13)):
        st = doc.styles[f"Heading {level}"]
        st.font.name = HEADING_FONT
        st.font.size = Pt(size)
        st.font.color.rgb = HEADING_RGB


def save_docx(paragraphs, path):
    doc = docx.Document()
    # The template starts with one empty paragraph; drop it.
    body = doc.element.body
    for p in list(body.iterchildren(qn("w:p"))):
        body.remove(p)

    _apply_house_style(doc)
    numbered_lists_seen = {}
    for para in paragraphs:
        if isinstance(para, Table):
            _write_table(doc, para)
            continue
        if isinstance(para, Image):
            _write_image(doc.add_paragraph(), para)
            continue
        p = doc.add_paragraph(style=_STYLE_TO_DOCX.get(para.style, "Normal"))
        if para.align in _ALIGN_TO_DOCX:
            p.alignment = _ALIGN_TO_DOCX[para.align]
        if para.style == "number":
            key = para.list_id
            if key not in numbered_lists_seen:
                # The first numbered list uses the style's numbering; each later
                # one gets its own numbering instance so Word restarts at 1.
                numbered_lists_seen[key] = (
                    None if not numbered_lists_seen else _restart_numbering(doc)
                )
            num_id = numbered_lists_seen[key]
            if num_id is not None:
                numpr = p._p.get_or_add_pPr().get_or_add_numPr()
                numpr.get_or_add_ilvl().val = 0
                numpr.get_or_add_numId().val = num_id
        _write_runs(p, para)
    doc.save(path)


def _write_runs(p, para):
    for r in para.runs:
        run = p.add_run(r.text)
        # Headings are bold through their style, so only write explicit bold
        # for body text.
        if r.bold and not para.heading_level:
            run.bold = True
        if r.italic:
            run.italic = True
        if r.underline:
            run.underline = True
        if r.strike:
            run.font.strike = True
        if r.font:
            run.font.name = r.font
        if r.size:
            run.font.size = Pt(r.size)
        if r.color:
            run.font.color.rgb = RGBColor.from_string(r.color.lstrip("#").upper())
        if r.highlight:
            # Shading takes any colour, unlike Word's fixed highlighter palette.
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), r.highlight.lstrip("#").upper())
            run._r.get_or_add_rPr().append(shd)


def _write_image(p, image: Image):
    p.alignment = _ALIGN_TO_DOCX.get(image.align)
    if image.data:
        p.add_run().add_picture(io.BytesIO(image.data), width=Pt(image.width),
                                height=Pt(image.height))


def _write_table(doc, table: Table):
    rows = len(table.rows)
    cols = max((len(r) for r in table.rows), default=0)
    if not rows or not cols:
        return
    t = doc.add_table(rows=rows, cols=cols)
    _gilt_borders(t)
    for r, row in enumerate(table.rows):
        for c in range(cols):
            cell = t.cell(r, c)
            paras = row[c] if c < len(row) else []
            for i, para in enumerate(paras):
                p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
                if para.align in _ALIGN_TO_DOCX:
                    p.alignment = _ALIGN_TO_DOCX[para.align]
                _write_runs(p, para)


def _gilt_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "6")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), GILT_HEX)
        borders.append(el)
    tblPr.append(borders)


def _style_num_id(doc, style_name):
    pPr = doc.styles[style_name].element.pPr
    return pPr.numPr.numId.val


def _restart_numbering(doc) -> int:
    numbering = doc.part.numbering_part.element
    base = _style_num_id(doc, "List Number")
    abstract_id = next(
        n.abstractNumId.val for n in numbering.num_lst if n.numId == base
    )
    num = numbering.add_num(abstract_id)
    num.add_lvlOverride(ilvl=0).add_startOverride(1)
    return num.numId


def _num_id(paragraph):
    pPr = paragraph._p.pPr
    if pPr is not None and pPr.numPr is not None and pPr.numPr.numId is not None:
        return pPr.numPr.numId.val
    return None


def _num_format(doc, num_id):
    """'bullet', 'decimal', ... for a numbering instance, or None."""
    try:
        numbering = doc.part.numbering_part.element
    except (KeyError, NotImplementedError):
        return None
    for num in numbering.num_lst:
        if num.numId == num_id:
            abstract_id = num.abstractNumId.val
            for absnum in numbering.findall(qn("w:abstractNum")):
                if absnum.get(qn("w:abstractNumId")) == str(abstract_id):
                    lvl = absnum.find(qn("w:lvl"))
                    fmt = lvl.find(qn("w:numFmt")) if lvl is not None else None
                    return fmt.get(qn("w:val")) if fmt is not None else None
    return None


def _paragraph_style(doc, p):
    name = p.style.name if p.style is not None else "Normal"
    for level in (1, 2, 3):
        if name == f"Heading {level}":
            return f"h{level}"
    if name == "Title":
        return "h1"
    if name.startswith("Heading "):
        return "h3"  # Heading 4+ collapse to our smallest heading
    if name.startswith("List Bullet"):
        return "bullet"
    if name.startswith("List Number"):
        return "number"
    num_id = _num_id(p)
    if num_id is not None and num_id != 0:  # e.g. Word's "List Paragraph"
        return "bullet" if _num_format(doc, num_id) == "bullet" else "number"
    return "normal"


def _read_run(r, heading):
    f = r.font
    run = Run(r.text, True if heading else bool(r.bold), bool(r.italic), bool(r.underline),
              bool(f.strike))
    if f.name:
        run.font = f.name
    if f.size:
        run.size = f.size.pt
    try:
        if f.color is not None and f.color.type is not None and f.color.rgb is not None:
            run.color = "#" + str(f.color.rgb)
    except (AttributeError, ValueError):
        pass
    rpr = r._r.rPr
    shd = rpr.find(qn("w:shd")) if rpr is not None else None
    fill = shd.get(qn("w:fill")) if shd is not None else None
    if fill and fill.lower() != "auto":
        run.highlight = "#" + fill.upper()
    elif f.highlight_color in _HIGHLIGHTS:
        run.highlight = _HIGHLIGHTS[f.highlight_color]
    return run


def _read_images(doc, p):
    """Pictures inside a paragraph's runs, as Image blocks."""
    out = []
    for blip in p._p.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        part = doc.part.related_parts.get(rid) if rid else None
        if part is None:
            continue
        w = h = 0.0
        inline = blip
        while inline is not None and inline.tag not in (qn("wp:inline"), qn("wp:anchor")):
            inline = inline.getparent()
        ext = inline.find(qn("wp:extent")) if inline is not None else None
        if ext is not None:
            w, h = int(ext.get("cx")) / 12700, int(ext.get("cy")) / 12700
        out.append(Image(part.blob, w or 200.0, h or 150.0,
                         _ALIGN_FROM_DOCX.get(p.alignment, "left")))
    return out


def _read_paragraph(doc, p, style):
    heading = style.startswith("h")
    runs = [_read_run(r, heading) for r in p.runs if r.text]
    return Paragraph(style, runs, None, _ALIGN_FROM_DOCX.get(p.alignment, "left"))


def _read_table(doc, t: DocxTable) -> Table:
    rows = []
    for row in t.rows:
        cells = []
        for cell in row.cells:
            cells.append([_read_paragraph(doc, p, "normal") for p in cell.paragraphs])
        rows.append(cells)
    return Table(rows)


def open_docx(path) -> list:
    doc = docx.Document(path)
    out = []
    list_counter = 0
    prev_style, prev_num_id = None, None
    for item in doc.iter_inner_content():
        if isinstance(item, DocxTable):
            out.append(_read_table(doc, item))
            prev_style = None
            continue
        p: DocxParagraph = item
        style = _paragraph_style(doc, p)
        list_id = None
        if style in ("bullet", "number"):
            num_id = _num_id(p)
            if style != prev_style or num_id != prev_num_id:
                list_counter += 1
            list_id = list_counter
            prev_num_id = num_id
        prev_style = style
        images = _read_images(doc, p)
        para = _read_paragraph(doc, p, style)
        para.list_id = list_id
        if images and not para.runs:
            out.extend(images)
            continue
        out.append(para)
        out.extend(images)
    return out
