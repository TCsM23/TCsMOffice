"""Charts from a selection: column, bar, line and pie, drawn with QPainter in
the house palette. The dialog can save a PNG or send the chart to Slides."""
import math

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from .. import theme

PALETTE = [theme.CRIMSON, theme.GILT, "#3B060C", "#C9707A", "#5C4A3A", theme.GILT_LIGHT,
           "#9C1426", "#7A6656"]
KINDS = [("Column", "column"), ("Bar", "bar"), ("Line", "line"), ("Pie", "pie")]


def nice_max(v):
    if v <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def _label(v):
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}"


def paint_chart(p: QPainter, rect: QRectF, kind, title, categories, series):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(rect, QColor(theme.PAGE))
    p.setPen(QPen(QColor(theme.GILT), 2))
    p.drawRect(rect.adjusted(6, 6, -6, -6))
    p.setPen(QPen(QColor(theme.GILT), 0.8))
    p.drawRect(rect.adjusted(11, 11, -11, -11))
    scale = rect.height() / 500
    title_font = QFont(theme.TITLE_FAMILY)
    title_font.setPixelSize(max(10, int(26 * scale)))
    title_font.setBold(True)
    body_font = QFont(theme.BODY_FAMILY)
    body_font.setPixelSize(max(8, int(15 * scale)))
    p.setFont(title_font)
    p.setPen(QColor(theme.CRIMSON))
    title_rect = QRectF(rect.left() + 20, rect.top() + 18, rect.width() - 40, 40 * scale)
    p.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)
    p.setFont(body_font)
    # Legend along the bottom.
    legend_items = categories if kind == "pie" else [n for n, _ in series]
    lx = rect.left() + 30
    ly = rect.bottom() - 34 * scale
    fm = p.fontMetrics()
    for i, name in enumerate(legend_items[:12]):
        p.fillRect(QRectF(lx, ly + 3 * scale, 12 * scale, 12 * scale), QColor(PALETTE[i % len(PALETTE)]))
        p.setPen(QColor(theme.INK))
        p.drawText(QPointF(lx + 17 * scale, ly + 14 * scale), name)
        lx += 30 * scale + fm.horizontalAdvance(name)
    plot = QRectF(rect.left() + 70 * scale, title_rect.bottom() + 16 * scale,
                  rect.width() - 100 * scale, ly - title_rect.bottom() - 40 * scale)
    if not series or not categories:
        p.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Select some numbers to chart")
        p.restore()
        return
    if kind == "pie":
        _pie(p, plot, categories, series[0][1], scale)
    else:
        _axes_chart(p, plot, kind, categories, series, scale)
    p.restore()


def _pie(p, plot, categories, values, scale):
    vals = [max(0.0, v) for v in values]
    total = sum(vals)
    d = min(plot.width(), plot.height())
    circle = QRectF(plot.center().x() - d / 2, plot.center().y() - d / 2, d, d)
    if total <= 0:
        p.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Nothing to show")
        return
    angle = 90.0
    p.setPen(QPen(QColor(theme.PAGE), 2))
    for i, v in enumerate(vals):
        span = 360.0 * v / total
        p.setBrush(QColor(PALETTE[i % len(PALETTE)]))
        p.drawPie(circle, int(angle * 16), int(-span * 16))
        if span > 12:
            mid = math.radians(angle - span / 2)
            pt = QPointF(circle.center().x() + math.cos(mid) * d * 0.33,
                         circle.center().y() - math.sin(mid) * d * 0.33)
            p.setPen(QColor(theme.IVORY if i % len(PALETTE) in (0, 2, 4, 6) else theme.INK))
            p.drawText(QRectF(pt.x() - 40, pt.y() - 10, 80, 20), Qt.AlignmentFlag.AlignCenter,
                       f"{100 * v / total:.0f}%")
            p.setPen(QPen(QColor(theme.PAGE), 2))
        angle -= span


def _axes_chart(p, plot, kind, categories, series, scale):
    values = [v for _n, vs in series for v in vs]
    lo = min(0.0, min(values))
    hi = nice_max(max(values)) if max(values) > 0 else 1.0
    if lo < 0:
        lo = -nice_max(-lo)
    horizontal = kind == "bar"
    span = hi - lo or 1.0
    p.setPen(QPen(QColor(theme.GRID), 1))
    steps = 5
    for i in range(steps + 1):
        v = lo + span * i / steps
        if horizontal:
            x = plot.left() + plot.width() * (v - lo) / span
            p.setPen(QPen(QColor(theme.GRID), 1))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(x - 40, plot.bottom() + 4, 80, 18), Qt.AlignmentFlag.AlignCenter,
                       _label(v))
        else:
            y = plot.bottom() - plot.height() * (v - lo) / span
            p.setPen(QPen(QColor(theme.GRID), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(plot.left() - 66 * scale, y - 9, 60 * scale, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _label(v))
    n = len(categories)
    band = (plot.height() if horizontal else plot.width()) / n
    p.setPen(QColor(theme.INK))
    for i, cat in enumerate(categories):
        if horizontal:
            y = plot.top() + band * (i + 0.5)
            p.drawText(QRectF(plot.left() - 68 * scale, y - 9, 62 * scale, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(cat, Qt.TextElideMode.ElideRight, int(62 * scale)))
        else:
            x = plot.left() + band * (i + 0.5)
            p.drawText(QRectF(x - band / 2, plot.bottom() + 4, band, 18),
                       Qt.AlignmentFlag.AlignCenter,
                       p.fontMetrics().elidedText(cat, Qt.TextElideMode.ElideRight, int(band)))

    def pos(v):
        return plot.height() * (v - lo) / span if not horizontal else plot.width() * (v - lo) / span

    zero = pos(0.0)
    if kind == "line":
        for si, (_name, vs) in enumerate(series):
            color = QColor(PALETTE[si % len(PALETTE)])
            path = QPainterPath()
            pts = [QPointF(plot.left() + band * (i + 0.5), plot.bottom() - pos(v))
                   for i, v in enumerate(vs)]
            path.moveTo(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.setPen(QPen(color, 3 * scale))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setBrush(color)
            p.setPen(QPen(QColor(theme.PAGE), 1.5))
            for pt in pts:
                p.drawEllipse(pt, 4.5 * scale, 4.5 * scale)
    else:
        k = len(series)
        inner = band * 0.72
        bw = inner / k
        p.setPen(Qt.PenStyle.NoPen)
        for si, (_name, vs) in enumerate(series):
            p.setBrush(QColor(PALETTE[si % len(PALETTE)]))
            for i, v in enumerate(vs):
                a, b = sorted((zero, pos(v)))
                if horizontal:
                    y = plot.top() + band * i + (band - inner) / 2 + bw * si
                    p.drawRect(QRectF(plot.left() + a, y, b - a, bw * 0.92))
                else:
                    x = plot.left() + band * i + (band - inner) / 2 + bw * si
                    p.drawRect(QRectF(x, plot.bottom() - b, bw * 0.92, b - a))
    p.setPen(QPen(QColor(theme.INK), 1.2))
    if horizontal:
        p.drawLine(QPointF(plot.left() + zero, plot.top()), QPointF(plot.left() + zero, plot.bottom()))
    else:
        p.drawLine(QPointF(plot.left(), plot.bottom() - zero), QPointF(plot.right(), plot.bottom() - zero))


def render_chart(kind, title, categories, series, width=1200, height=700) -> QImage:
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(theme.PAGE))
    p = QPainter(img)
    paint_chart(p, QRectF(0, 0, width, height), kind, title, categories, series)
    p.end()
    return img


def png_bytes(image: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


class ChartCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind, self.title, self.categories, self.series = "column", "", [], []
        self.setMinimumSize(560, 340)

    def paintEvent(self, _event):
        p = QPainter(self)
        paint_chart(p, QRectF(self.rect()), self.kind, self.title, self.categories, self.series)


class ChartDialog(QDialog):
    sendToSlides = Signal(bytes)  # PNG data

    def __init__(self, categories, series, title="Chart", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chart")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.kind_box = QComboBox()
        for label, key in KINDS:
            self.kind_box.addItem(label, key)
        self.title_edit = QLineEdit(title)
        self.title_edit.setStyleSheet(f"font-family: '{theme.BODY_FAMILY}'; font-size: 16px;")
        top.addWidget(QLabel("Type"))
        top.addWidget(self.kind_box)
        top.addWidget(QLabel("Title"))
        top.addWidget(self.title_edit, 1)
        lay.addLayout(top)
        self.canvas = ChartCanvas()
        self.canvas.categories, self.canvas.series = categories, series
        lay.addWidget(self.canvas, 1)
        buttons = QHBoxLayout()
        self.png_btn = QPushButton("Save picture…")
        self.slides_btn = QPushButton("Send to Slides")
        self.slides_btn.setObjectName("primary")
        close = QPushButton("Close")
        buttons.addWidget(self.png_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.slides_btn)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self.kind_box.currentIndexChanged.connect(self._update)
        self.title_edit.textChanged.connect(self._update)
        self.png_btn.clicked.connect(self.save_png)
        self.slides_btn.clicked.connect(lambda: self.sendToSlides.emit(png_bytes(self.image())))
        close.clicked.connect(self.close)
        self._update()

    def _update(self, *_):
        self.canvas.kind = self.kind_box.currentData()
        self.canvas.title = self.title_edit.text()
        self.canvas.update()

    def image(self) -> QImage:
        c = self.canvas
        return render_chart(c.kind, c.title, c.categories, c.series)

    def save_png(self, path=None):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save chart", "chart.png", "PNG (*.png)")
        if path:
            self.image().save(str(path), "PNG")
