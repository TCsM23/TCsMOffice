"""Draw the TCsOffice icon: a gilt-edged crimson gothic arch with a blackletter T.

Run once after changing the design; the PNG/ICO it writes are committed:

    python tools/make_icon.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)

from office import theme  # noqa: E402

OUT = ROOT / "office" / "assets"


def arch_path(r: QRectF) -> QPainterPath:
    """A pointed (lancet) gothic arch filling r: straight sides, two arcs meeting at a peak."""
    w, h = r.width(), r.height()
    spring = r.top() + h * 0.42          # where the arcs start
    path = QPainterPath(QPointF(r.left(), r.bottom()))
    path.lineTo(r.left(), spring)
    # each arc is centred on the opposite side's springing line
    path.cubicTo(r.left(), spring - h * 0.20, r.center().x() - w * 0.18, r.top() + h * 0.05,
                 r.center().x(), r.top())
    path.cubicTo(r.center().x() + w * 0.18, r.top() + h * 0.05, r.right(), spring - h * 0.20,
                 r.right(), spring)
    path.lineTo(r.right(), r.bottom())
    path.closeSubpath()
    return path


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    s = size / 512

    outer = QRectF(56 * s, 18 * s, 400 * s, 476 * s)
    # gold frame
    gold = QLinearGradient(outer.topLeft(), outer.bottomRight())
    gold.setColorAt(0, QColor("#F1DDA8"))
    gold.setColorAt(0.45, QColor(theme.GILT))
    gold.setColorAt(1, QColor("#7C5B2C"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gold))
    p.drawPath(arch_path(outer))
    # crimson field
    inner = outer.adjusted(22 * s, 26 * s, -22 * s, -22 * s)
    red = QRadialGradient(inner.center().x(), inner.top() + inner.height() * 0.38, inner.height() * 0.75)
    red.setColorAt(0, QColor(theme.CRIMSON_BRIGHT))
    red.setColorAt(0.6, QColor(theme.CRIMSON))
    red.setColorAt(1, QColor(theme.OXBLOOD))
    p.setBrush(QBrush(red))
    p.drawPath(arch_path(inner))
    # fine inner gilt rule
    if size >= 48:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(theme.GILT_LIGHT), max(1.0, 5 * s)))
        p.drawPath(arch_path(inner.adjusted(16 * s, 18 * s, -16 * s, -16 * s)))
    # the blackletter T
    font = QFont(theme.BLACKLETTER_FAMILY)
    font.setPixelSize(int(300 * s))
    font.setWeight(QFont.Weight.Bold)
    p.setFont(font)
    text_rect = QRectF(inner.left(), inner.top() + 40 * s, inner.width(), inner.height() - 40 * s)
    p.setPen(QColor(0, 0, 0, 110))
    p.drawText(text_rect.translated(6 * s, 8 * s), Qt.AlignmentFlag.AlignCenter, "T")
    p.setPen(QColor(theme.GILT_LIGHT))
    p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "T")
    # a small gilt quatrefoil-ish star at the apex
    if size >= 64:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.GILT_LIGHT))
        c = QPointF(inner.center().x(), inner.top() + 62 * s)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            p.drawEllipse(QPointF(c.x() + dx * 9 * s, c.y() + dy * 9 * s), 7 * s, 7 * s)
    p.end()
    return img


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    theme.load_fonts()
    draw(1024).save(str(OUT / "icon.png"))
    draw(512).save(str(OUT / "icon-512.png"))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    for n in sizes:
        draw(n).save(str(OUT / f"_icon{n}.png"))
    from PIL import Image  # pip install pillow (only needed for this script)
    imgs = [Image.open(OUT / f"_icon{n}.png") for n in sizes]
    imgs[-1].save(OUT / "icon.ico", sizes=[(n, n) for n in sizes], append_images=imgs[:-1])
    for n in sizes:
        (OUT / f"_icon{n}.png").unlink()
    wizard_art(ROOT / "packaging" / "windows")
    del app


def wizard_art(folder: Path):
    """The installer's left-hand panel (164x314 at 100%, drawn at 200%) and corner badge."""
    from PySide6.QtGui import QPixmap
    w, h = 328, 628
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor("#6A0D18"))
    bg.setColorAt(1, QColor(theme.NIGHT))
    p.fillRect(0, 0, w, h, bg)
    p.setPen(QPen(QColor(theme.GILT), 3))
    p.drawRect(QRectF(14, 14, w - 28, h - 28))
    p.setPen(QPen(QColor(theme.GILT), 1))
    p.drawRect(QRectF(22, 22, w - 44, h - 44))
    p.drawImage(QRectF(64, 120, 200, 200), draw(400))
    font = QFont(theme.BLACKLETTER_FAMILY)
    font.setPixelSize(54)
    p.setFont(font)
    p.setPen(QColor(theme.GILT_LIGHT))
    p.drawText(QRectF(0, 350, w, 70), Qt.AlignmentFlag.AlignCenter, "TCsOffice")
    small = QFont(theme.TITLE_FAMILY)
    small.setPixelSize(20)
    p.setFont(small)
    p.setPen(QColor(theme.IVORY))
    p.drawText(QRectF(0, 425, w, 40), Qt.AlignmentFlag.AlignCenter, "Sheets · Writer · Slides")
    p.end()
    img.save(str(folder / "wizard-large.bmp"))
    badge = QImage(110, 110, QImage.Format.Format_RGB32)
    badge.fill(QColor("white"))
    p = QPainter(badge)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.drawImage(QRectF(5, 5, 100, 100), draw(200))
    p.end()
    badge.save(str(folder / "wizard-small.bmp"))


if __name__ == "__main__":
    main()
