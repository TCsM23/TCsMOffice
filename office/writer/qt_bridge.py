"""Convert between QTextDocument (what the editor shows) and the document model.

The model is a list of blocks: Paragraph, Table or Image (see document.py).
"""
import uuid

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextFrameFormat, QTextImageFormat, QTextLength, QTextListFormat, QTextTableFormat,
)

from .. import theme
from .document import Image, Paragraph, Run, Table

BODY_PT = 13
HEADING_PT = {1: 24, 2: 18, 3: 15}
PX_PER_PT = 96 / 72  # the editor lays out in screen pixels
_LIST_STYLES = {"bullet": QTextListFormat.Style.ListDisc,
                "number": QTextListFormat.Style.ListDecimal}

_ALIGN = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
    "justify": Qt.AlignmentFlag.AlignJustify,
}

# Picture bytes by resource name, so saving writes the original file (a JPEG
# stays a JPEG) rather than a re-encoded copy.
_IMAGE_BYTES: dict = {}
IMAGE_SCHEME = "tcs-image"


def block_align(block) -> str:
    a = block.blockFormat().alignment()
    for name, flag in _ALIGN.items():
        if a & flag and name != "left":
            return name
    return "left"


def set_alignment(cursor: QTextCursor, align: str) -> None:
    cursor.beginEditBlock()
    for c in _blocks(cursor):
        bf = c.blockFormat()
        bf.setAlignment(_ALIGN[align])
        c.setBlockFormat(bf)
    cursor.endEditBlock()


# Shift+Enter inside a paragraph: Qt stores U+2028, .docx stores a line break.
_LINE_SEP = " "
_OBJECT = "￼"  # the character Qt puts where an image sits


def _is_bold(fmt: QTextCharFormat) -> bool:
    return fmt.fontWeight() >= QFont.Weight.DemiBold.value


def block_style(block) -> str:
    lst = block.textList()
    if lst is not None:
        if lst.format().style() == QTextListFormat.Style.ListDecimal:
            return "number"
        return "bullet"
    level = block.blockFormat().headingLevel()
    return f"h{level}" if level in HEADING_PT else "normal"


# ---- reading the editor --------------------------------------------------------

def _style_defaults(level):
    family = theme.TITLE_FAMILY if level else theme.BODY_FAMILY
    color = (theme.CRIMSON if level else theme.INK).upper()
    return family, float(HEADING_PT.get(level, BODY_PT)), color


def _run_from_format(text, cf: QTextCharFormat, level) -> Run:
    family, size, color = _style_defaults(level)
    run = Run(text, _is_bold(cf), cf.fontItalic(), cf.fontUnderline(), cf.fontStrikeOut())
    fams = cf.fontFamilies() or []
    if fams and fams[0] != family:
        run.font = fams[0]
    if cf.fontPointSize() and abs(cf.fontPointSize() - size) > 0.01:
        run.size = round(cf.fontPointSize(), 1)
    fg = cf.foreground()
    if fg.style() != Qt.BrushStyle.NoBrush and fg.color().name().upper() != color:
        run.color = fg.color().name().upper()
    bg = cf.background()
    if bg.style() != Qt.BrushStyle.NoBrush and bg.color().alpha():
        run.highlight = bg.color().name().upper()
    return run


def _read_block(block, list_ids, out):
    """Append the block as a Paragraph, plus an Image for each picture in it."""
    style = block_style(block)
    level = int(style[1]) if style.startswith("h") else 0
    list_id = None
    lst = block.textList()
    if lst is not None:
        list_id = list_ids.setdefault(lst.objectIndex(), len(list_ids) + 1)
    runs, images = [], []
    it = block.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.text():
            cf = frag.charFormat()
            if cf.isImageFormat():
                images.append(_image_from_format(cf.toImageFormat(), block_align(block)))
                rest = frag.text().replace(_OBJECT, "")
                if rest:
                    runs.append(_run_from_format(rest, cf, level))
            else:
                runs.append(_run_from_format(frag.text().replace(_LINE_SEP, "\n"), cf, level))
        it += 1
    if images and not runs:
        out.extend(images)
        return
    out.append(Paragraph(style, runs, list_id, block_align(block)))
    out.extend(images)


def _image_from_format(fmt: QTextImageFormat, align) -> Image:
    name = fmt.name()
    data = _IMAGE_BYTES.get(name, b"")
    return Image(data, round(fmt.width() / PX_PER_PT, 1), round(fmt.height() / PX_PER_PT, 1),
                 align if align != "justify" else "left")


def _read_table(table, list_ids):
    rows = []
    for r in range(table.rows()):
        row = []
        for c in range(table.columns()):
            cell = table.cellAt(r, c)
            paras = []
            block = cell.firstCursorPosition().block()
            end = cell.lastCursorPosition().block()
            while block.isValid():
                _read_block(block, list_ids, paras)
                if block == end:
                    break
                block = block.next()
            row.append([p for p in paras if isinstance(p, Paragraph)])
        rows.append(row)
    return Table(rows)


def to_paragraphs(doc: QTextDocument) -> list:
    """Every block of the document, in order: Paragraph, Table or Image."""
    out = []
    list_ids = {}
    it = doc.rootFrame().begin()
    while not it.atEnd():
        frame = it.currentFrame()
        if frame is not None:
            from PySide6.QtGui import QTextTable
            if isinstance(frame, QTextTable):
                out.append(_read_table(frame, list_ids))
        else:
            block = it.currentBlock()
            if block.isValid():
                _read_block(block, list_ids, out)
        it += 1
    # Qt keeps an empty paragraph after a table at the end; drop it if it is
    # the very last block and nothing is in it.
    if len(out) >= 2 and isinstance(out[-2], Table) and isinstance(out[-1], Paragraph) \
            and not out[-1].runs and out[-1].style == "normal":
        out.pop()
    return out


# ---- writing the editor --------------------------------------------------------

def block_format(level: int, base: QTextBlockFormat | None = None) -> QTextBlockFormat:
    """Heading level plus paragraph spacing, so headings get room above them."""
    bf = QTextBlockFormat(base) if base is not None else QTextBlockFormat()
    bf.setHeadingLevel(level)
    bf.setTopMargin(14 if level else 0)
    bf.setBottomMargin(6 if level else 4)
    return bf


def heading_char_format(level: int) -> QTextCharFormat:
    """Headings are Alegreya SC in crimson; body text is EB Garamond in ink."""
    cf = QTextCharFormat()
    cf.setFontPointSize(HEADING_PT.get(level, BODY_PT))
    cf.setFontWeight(QFont.Weight.Bold if level else QFont.Weight.Normal)
    cf.setFontFamilies([theme.TITLE_FAMILY if level else theme.BODY_FAMILY])
    cf.setForeground(QColor(theme.CRIMSON if level else theme.INK))
    return cf


def run_char_format(run: Run, base: QTextCharFormat, heading=False) -> QTextCharFormat:
    cf = QTextCharFormat(base)
    if run.bold or heading:
        cf.setFontWeight(QFont.Weight.Bold)
    cf.setFontItalic(run.italic)
    cf.setFontUnderline(run.underline)
    cf.setFontStrikeOut(run.strike)
    if run.font:
        cf.setFontFamilies([run.font])
    if run.size:
        cf.setFontPointSize(run.size)
    if run.color:
        cf.setForeground(QColor(run.color))
    if run.highlight:
        cf.setBackground(QColor(run.highlight))
    return cf


def table_format(columns: int) -> QTextTableFormat:
    tf = QTextTableFormat()
    tf.setBorder(1)
    tf.setBorderBrush(QBrush(QColor(theme.GILT)))
    tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
    tf.setBorderCollapse(True)
    tf.setCellPadding(6)
    tf.setCellSpacing(0)
    tf.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
    tf.setTopMargin(6)
    tf.setBottomMargin(6)
    return tf


def register_image(doc: QTextDocument, data: bytes) -> tuple[str, QImage]:
    name = f"{IMAGE_SCHEME}://{uuid.uuid4().hex}"
    img = QImage.fromData(data)
    _IMAGE_BYTES[name] = data
    doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
    return name, img


def insert_image(cursor: QTextCursor, data: bytes, width_pt=None, height_pt=None) -> bool:
    """Put a picture at the cursor. Its size defaults to the picture's own, at
    most the page width."""
    doc = cursor.document()
    name, img = register_image(doc, data)
    if img.isNull():
        return False
    if width_pt is None:
        max_w = doc.textWidth() - 2 * doc.documentMargin() if doc.textWidth() > 0 else 600
        w = min(float(img.width()), max(120.0, max_w - 8))
        h = img.height() * w / img.width()
    else:
        w, h = width_pt * PX_PER_PT, height_pt * PX_PER_PT
    fmt = QTextImageFormat()
    fmt.setName(name)
    fmt.setWidth(w)
    fmt.setHeight(h)
    cursor.insertImage(fmt)
    return True


def _insert_runs(cursor, para, base, level):
    for run in para.runs:
        cursor.insertText(run.text.replace("\n", _LINE_SEP),
                          run_char_format(run, base, bool(level)))


def load_paragraphs(doc: QTextDocument, paragraphs) -> None:
    doc.clear()
    cursor = QTextCursor(doc)
    lists = {}
    first = True
    for block in paragraphs:
        if isinstance(block, Table):
            if first:
                # A table can't be the very first thing: Qt needs a block before it.
                cursor.setBlockFormat(block_format(0))
                cursor.setBlockCharFormat(heading_char_format(0))
            _insert_table(cursor, block)
            first = True  # Qt leaves an empty block after a table: fill that one next
            continue
        level = getattr(block, "heading_level", 0)
        bf = block_format(level)
        bf.setAlignment(_ALIGN.get(block.align, _ALIGN["left"]))
        base = heading_char_format(level)
        if first:
            cursor.setBlockFormat(bf)
            cursor.setBlockCharFormat(base)
        else:
            # A fresh block format, so the new block doesn't inherit the previous
            # block's list (that is how a numbered list would wrongly continue).
            cursor.insertBlock(bf, base)
        first = False
        if isinstance(block, Image):
            if block.data:
                insert_image(cursor, block.data, block.width, block.height)
            continue
        if block.style in _LIST_STYLES:
            lst = lists.get(block.list_id)
            if lst is None:
                lists[block.list_id] = cursor.createList(_LIST_STYLES[block.style])
            else:
                lst.add(cursor.block())
        _insert_runs(cursor, block, base, level)
    doc.setModified(False)


def _insert_table(cursor, table: Table):
    rows = len(table.rows)
    cols = max((len(r) for r in table.rows), default=0)
    if not rows or not cols:
        return
    qt_table = cursor.insertTable(rows, cols, table_format(cols))
    base = heading_char_format(0)
    for r, row in enumerate(table.rows):
        for c in range(cols):
            paras = row[c] if c < len(row) else []
            cell_cursor = qt_table.cellAt(r, c).firstCursorPosition()
            for i, para in enumerate(paras):
                bf = block_format(0)
                bf.setAlignment(_ALIGN.get(para.align, _ALIGN["left"]))
                if i:
                    cell_cursor.insertBlock(bf, base)
                else:
                    cell_cursor.setBlockFormat(bf)
                _insert_runs(cell_cursor, para, base, 0)
    # Step out of the table so whatever comes next lands after it.
    cursor.movePosition(QTextCursor.MoveOperation.End)


def insert_table(cursor: QTextCursor, rows: int, cols: int):
    """Insert an empty table at the cursor (used by the toolbar)."""
    return cursor.insertTable(rows, cols, table_format(cols))


# ---- styles ---------------------------------------------------------------------

def apply_style(cursor: QTextCursor, style: str) -> None:
    """Change the paragraph style of every block the cursor touches."""
    cursor.beginEditBlock()
    if style in _LIST_STYLES:
        _toggle_list(cursor, style)
    else:
        level = int(style[1]) if style.startswith("h") else 0
        _remove_from_lists(cursor)
        for block_cursor in _blocks(cursor):
            was_heading = block_cursor.blockFormat().headingLevel() > 0
            block_cursor.setBlockFormat(block_format(level, block_cursor.blockFormat()))
            if level or was_heading:
                block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                block_cursor.mergeCharFormat(heading_char_format(level))
                block_cursor.clearSelection()
                block_cursor.mergeBlockCharFormat(heading_char_format(level))
    cursor.endEditBlock()


def _blocks(cursor):
    doc = cursor.document()
    start = doc.findBlock(cursor.selectionStart())
    end = doc.findBlock(cursor.selectionEnd())
    block = start
    while block.isValid():
        yield QTextCursor(block)
        if block == end:
            break
        block = block.next()


def _remove_from_lists(cursor):
    for c in _blocks(cursor):
        lst = c.block().textList()
        if lst is not None:
            lst.remove(c.block())
            bf = c.blockFormat()
            bf.setIndent(0)
            c.setBlockFormat(bf)


def _toggle_list(cursor, style):
    target = _LIST_STYLES[style]
    lst = cursor.block().textList()
    if lst is not None and lst.format().style() == target:
        _remove_from_lists(cursor)  # pressing the button again turns it off
        return
    _remove_from_lists(cursor)
    for c in _blocks(cursor):  # lists can't be headings
        if c.blockFormat().headingLevel():
            c.setBlockFormat(block_format(0, c.blockFormat()))
            c.select(QTextCursor.SelectionType.BlockUnderCursor)
            c.mergeCharFormat(heading_char_format(0))
    cursor.createList(target)
