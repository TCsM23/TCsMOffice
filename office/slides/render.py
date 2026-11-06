"""Draw slide shapes with QPainter. Used by the editor, thumbnails and the slide show."""
import math

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
    QTextCharFormat, QTextCursor, QTextDocument, QTextListFormat, QTextOption,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene

from .model import SHAPES, Shape, Slide

_ALIGN = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
          "right": Qt.AlignmentFlag.AlignRight}
TEXT_INSET = 4.0


def text_document(shape: Shape) -> QTextDocument:
    """Lay out a shape's text. Sizes are in slide points, so 1 pt = 1 scene unit."""
    st = shape.style
    doc = QTextDocument()
    doc.setDocumentMargin(TEXT_INSET)
    font = QFont(st.font)
    font.setPixelSize(max(1, round(st.size)))
    doc.setDefaultFont(font)
    opt = QTextOption(_ALIGN.get(st.align, Qt.AlignmentFlag.AlignLeft))
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(opt)
    cf = QTextCharFormat()
    cf.setFont(font)
    cf.setFontWeight(QFont.Weight.Bold if st.bold else QFont.Weight.Normal)
    cf.setFontItalic(st.italic)
    cf.setFontUnderline(st.underline)
    cf.setForeground(QColor(st.color))
    cursor = QTextCursor(doc)
    cursor.setCharFormat(cf)
    cursor.setBlockCharFormat(cf)
    lines = shape.text.split("\n") if shape.text else [""]
    for i, line in enumerate(lines):
        if i:
            cursor.insertBlock(cursor.blockFormat(), cf)
        cursor.insertText(line, cf)
    if shape.bullets:
        lf = QTextListFormat()
        lf.setStyle(QTextListFormat.Style.ListDisc)
        lf.setIndent(1)
        doc.setIndentWidth(st.size * 1.1)
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.createList(lf)
    doc.setTextWidth(max(10.0, shape.w))
    return doc


def text_offset(shape: Shape, doc: QTextDocument) -> float:
    spare = shape.h - doc.size().height()
    if shape.style.valign == "middle":
        return max(0.0, spare / 2)
    if shape.style.valign == "bottom":
        return max(0.0, spare)
    return 0.0


def shape_path(kind: str, w: float, h: float) -> QPainterPath:
    """The outline of a drawn shape in a w x h box."""
    path = QPainterPath()
    if kind == "ellipse":
        path.addEllipse(QRectF(0, 0, w, h))
    elif kind == "rounded":
        r = min(w, h) * 0.16
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    elif kind == "triangle":
        path.addPolygon(QPolygonF([QPointF(w / 2, 0), QPointF(w, h), QPointF(0, h)]))
        path.closeSubpath()
    elif kind == "diamond":
        path.addPolygon(QPolygonF([QPointF(w / 2, 0), QPointF(w, h / 2), QPointF(w / 2, h),
                                   QPointF(0, h / 2)]))
        path.closeSubpath()
    elif kind == "hexagon":
        k = w * 0.25
        path.addPolygon(QPolygonF([QPointF(k, 0), QPointF(w - k, 0), QPointF(w, h / 2),
                                   QPointF(w - k, h), QPointF(k, h), QPointF(0, h / 2)]))
        path.closeSubpath()
    elif kind == "star":
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = 0.5 if i % 2 == 0 else 0.2
            pts.append(QPointF(w / 2 + math.cos(a) * w * r, h / 2 + math.sin(a) * h * r * 1.05
                               + h * 0.03))
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
    elif kind == "arrow":
        shaft = h * 0.3
        head = min(w * 0.4, h)
        path.addPolygon(QPolygonF([
            QPointF(0, shaft), QPointF(w - head, shaft), QPointF(w - head, 0), QPointF(w, h / 2),
            QPointF(w - head, h), QPointF(w - head, h - shaft), QPointF(0, h - shaft)]))
        path.closeSubpath()
    else:
        path.addRect(QRectF(0, 0, w, h))
    return path


TABLE_HEADER = "#7A0E1B"
TABLE_BAND = "#EFE4D0"
TABLE_LINE = "#B08D57"


def paint_table(painter: QPainter, shape: Shape):
    """Header row in crimson, banded body rows, gilt rules."""
    cells = shape.table_cells()
    rows, cols = len(cells), len(cells[0])
    cw, rh = shape.w / cols, shape.h / rows
    st = shape.style
    for r, row in enumerate(cells):
        header = r == 0
        fill = TABLE_HEADER if header else (TABLE_BAND if r % 2 == 0 else (shape.fill or "#FFFBF3"))
        painter.fillRect(QRectF(0, r * rh, shape.w, rh), QColor(fill))
        for c, text in enumerate(row):
            if not text:
                continue
            font = QFont(st.font)
            font.setPixelSize(max(1, round(st.size)))
            font.setBold(header or st.bold)
            font.setItalic(st.italic)
            painter.setFont(font)
            painter.setPen(QColor("#F3E7D3" if header else st.color))
            align = _ALIGN.get(st.align, Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter
            painter.drawText(QRectF(c * cw + 6, r * rh, cw - 12, rh),
                             int(align | Qt.TextFlag.TextWordWrap), text)
    pen = QPen(QColor(shape.line or TABLE_LINE), max(0.5, shape.line_width))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for r in range(1, rows):
        painter.drawLine(QPointF(0, r * rh), QPointF(shape.w, r * rh))
    for c in range(1, cols):
        painter.drawLine(QPointF(c * cw, 0), QPointF(c * cw, shape.h))
    painter.drawRect(QRectF(0, 0, shape.w, shape.h))


def paint_shape(painter: QPainter, shape: Shape, pixmap: QPixmap | None = None,
                draw_text=True):
    rect = QRectF(0, 0, shape.w, shape.h)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if shape.kind == "image":
        if pixmap is None and shape.image:
            pixmap = QPixmap.fromImage(QImage.fromData(shape.image))
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
        painter.restore()
        return
    if shape.kind == "table":
        if draw_text:
            paint_table(painter, shape)
        painter.restore()
        return
    pen = QPen(QColor(shape.line), shape.line_width) if shape.line else Qt.PenStyle.NoPen
    painter.setPen(pen)
    painter.setBrush(QBrush(QColor(shape.fill)) if shape.fill else Qt.BrushStyle.NoBrush)
    if shape.kind == "ellipse":
        painter.drawEllipse(rect)
    elif shape.kind in SHAPES:
        painter.drawPath(shape_path(shape.kind, shape.w, shape.h))
    elif shape.fill or shape.line:
        painter.drawRect(rect)
    if draw_text and shape.text:
        doc = text_document(shape)
        painter.translate(0, text_offset(shape, doc))
        painter.setClipRect(QRectF(0, -text_offset(shape, doc), shape.w, max(shape.h, doc.size().height())))
        doc.drawContents(painter)
    painter.restore()


class StaticShapeItem(QGraphicsItem):
    """A non-interactive shape, for thumbnails and the slide show."""

    def __init__(self, shape: Shape):
        super().__init__()
        self.shape_model = shape
        self.setPos(shape.x, shape.y)

    def boundingRect(self):
        pad = self.shape_model.line_width
        return QRectF(-pad, -pad, self.shape_model.w + 2 * pad, self.shape_model.h + 2 * pad)

    def paint(self, painter, _option, _widget=None):
        paint_shape(painter, self.shape_model)


def build_static_scene(slide: Slide, width: float, height: float) -> QGraphicsScene:
    scene = QGraphicsScene(0, 0, width, height)
    bg = QGraphicsRectItem(0, 0, width, height)
    bg.setBrush(QColor(slide.background))
    bg.setPen(Qt.PenStyle.NoPen)
    scene.addItem(bg)
    for shape in slide.shapes:
        scene.addItem(StaticShapeItem(shape))
    return scene


def render_slide(slide: Slide, width: float, height: float, size: QSizeF) -> QImage:
    image = QImage(int(size.width()), int(size.height()), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(slide.background))
    scene = build_static_scene(slide, width, height)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    scene.render(painter, QRectF(0, 0, size.width(), size.height()), QRectF(0, 0, width, height))
    painter.end()
    return image
