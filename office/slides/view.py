"""The Slides tab: thumbnails, an editable slide canvas, notes, and a slide show."""
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QEvent, QMarginsF, QRectF, QSize, QSizeF, Qt, QTimer,
    QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QActionGroup, QColor, QFont, QIcon, QImage, QKeySequence, QPageLayout, QPageSize,
    QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGraphicsItem,
    QGraphicsObject, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from .. import theme
from ..undo import MacroCommand, UndoStack
from . import layouts
from .commands import (
    AddShapeCommand, AddSlideCommand, DeleteShapesCommand, DeleteSlideCommand,
    MoveSlideCommand, ReorderShapeCommand, set_attrs,
)
from ..findbar import FindBar
from .model import Presentation, Shape, TextStyle, TRANSITIONS
from .pptx_io import open_pptx, save_pptx
from .render import (
    build_static_scene, paint_shape, render_slide, text_document, text_offset,
)

SHAPE_MENU = [("rect", "▭ Rectangle"), ("rounded", "▢ Rounded rectangle"), ("ellipse", "◯ Ellipse"),
              ("triangle", "△ Triangle"), ("diamond", "◇ Diamond"), ("hexagon", "⬡ Hexagon"),
              ("star", "☆ Star"), ("arrow", "➔ Arrow")]
TRANSITION_LABELS = {"none": "None", "fade": "Fade", "push": "Push", "wipe": "Wipe",
                     "cover": "Cover", "zoom": "Zoom"}

HANDLE = 9.0
THUMB_W = 168
FONT_CHOICES = [theme.TITLE_FAMILY, theme.BODY_FAMILY, theme.BLACKLETTER_FAMILY,
                "Georgia", "Times New Roman", "Arial"]
SWATCHES = [("Crimson", layouts.CRIMSON), ("Oxblood", "#3B060C"), ("Night", layouts.NIGHT),
            ("Gilt", layouts.GILT), ("Pale gold", theme.GILT_LIGHT), ("Ink", layouts.INK),
            ("Parchment", layouts.PARCHMENT), ("Ivory", layouts.IVORY), ("White", "#FFFFFF")]


# ------------------------------------------------------------------ items --

class ShapeItem(QGraphicsObject):
    """An editable shape on the canvas. Moves and resizes live; the panel turns
    the result into one undoable command when the mouse is released."""

    def __init__(self, shape: Shape, panel):
        super().__init__()
        self.shape_model = shape
        self.panel = panel
        self.w, self.h = shape.w, shape.h
        self.editing = False
        self._resizing = False
        self._pixmap = None
        if shape.kind == "image" and shape.image:
            self._pixmap = QPixmap.fromImage(QImage.fromData(shape.image))
        self.setPos(shape.x, shape.y)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        pad = max(self.shape_model.line_width, HANDLE)
        return QRectF(-pad, -pad, self.w + 2 * pad, self.h + 2 * pad)

    def _handle_rect(self):
        return QRectF(self.w - HANDLE / 2, self.h - HANDLE / 2, HANDLE, HANDLE)

    def paint(self, painter, _option, _widget=None):
        model = self.shape_model
        if (self.w, self.h) != (model.w, model.h):
            # Draw a resized copy while dragging.
            model = Shape(**{**model.__dict__, "w": self.w, "h": self.h})
        paint_shape(painter, model, self._pixmap, draw_text=not self.editing)
        if self.isSelected():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(theme.CRIMSON_BRIGHT), 0)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(0, 0, self.w, self.h))
            painter.setPen(QPen(QColor(theme.CRIMSON_DARK), 0))
            painter.setBrush(QColor(theme.GILT_LIGHT))
            painter.drawRect(self._handle_rect())

    def hoverMoveEvent(self, event):
        on_handle = self.isSelected() and self._handle_rect().adjusted(-3, -3, 3, 3).contains(event.pos())
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if on_handle else Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if (self.isSelected() and event.button() == Qt.MouseButton.LeftButton
                and self._handle_rect().adjusted(-3, -3, 3, 3).contains(event.pos())):
            self._resizing = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            self.prepareGeometryChange()
            self.w = max(12.0, event.pos().x())
            self.h = max(8.0, event.pos().y())
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        super().mouseReleaseEvent(event)
        self.panel.commit_geometry()

    def mouseDoubleClickEvent(self, event):
        if self.shape_model.kind != "image":
            self.panel.begin_text_edit(self)
        else:
            super().mouseDoubleClickEvent(event)


class InlineEditor(QGraphicsTextItem):
    """Edits a shape's text in place. Leaving it (click away, Esc) commits."""

    def __init__(self, item: ShapeItem, panel):
        super().__init__()
        self.item, self.panel = item, panel
        shape = item.shape_model
        doc = text_document(shape)
        self.setDocument(doc)
        self.setTextWidth(shape.w)
        self.setPos(shape.x, shape.y + text_offset(shape, doc))
        self.setZValue(10_000)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setDefaultTextColor(QColor(shape.style.color))

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        QTimer.singleShot(0, self.panel.finish_text_edit)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        if event.key() == Qt.Key.Key_Tab:  # tables: Tab moves to the next cell
            self.textCursor().insertText("\t")
            return
        super().keyPressEvent(event)

    def sceneEvent(self, event):
        # Keep Tab for the text instead of moving focus to the next item.
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab:
            self.keyPressEvent(event)
            return True
        return super().sceneEvent(event)


# ------------------------------------------------------------------- view --

class SlideView(QGraphicsView):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.setObjectName("stage")
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def fit(self):
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def keyPressEvent(self, event):
        scene = self.scene()
        if scene is not None and isinstance(scene.focusItem(), InlineEditor):
            return super().keyPressEvent(event)
        p = self.panel
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            return p.delete_shapes()
        if event.matches(QKeySequence.StandardKey.Copy):
            return p.copy_shapes()
        if event.matches(QKeySequence.StandardKey.Cut):
            p.copy_shapes()
            return p.delete_shapes()
        if event.matches(QKeySequence.StandardKey.Paste):
            return p.paste_shapes()
        if (key == Qt.Key.Key_D
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            return p.duplicate_shapes()
        if event.matches(QKeySequence.StandardKey.SelectAll):
            for it in p.shape_items():
                it.setSelected(True)
            return
        step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if key in moves and p.selected_shapes():
            return p.nudge(*moves[key])
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2):
            items = [i for i in p.shape_items() if i.isSelected()]
            if len(items) == 1:
                return p.begin_text_edit(items[0])
        super().keyPressEvent(event)


class SlideShow(QWidget):
    """Full-screen presentation. Arrows, Space, click: next/previous. Esc: leave.
    B blacks the screen out. Each slide's transition plays as it arrives."""

    DURATION = 520  # ms

    def __init__(self, pres, start=0, animate=True):
        super().__init__()
        self.pres, self.index = pres, start
        self.animate = animate
        self.black = False
        self.setWindowTitle("Slide show")
        self.setStyleSheet("background: black;")
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._cache = {}
        self._from = None      # the outgoing frame while a transition plays
        self._kind = "none"
        self._dir = 1
        self._t = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.DURATION)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._step)
        self._anim.finished.connect(self._done)

    def _target(self):
        ratio = self.pres.width / self.pres.height
        w = min(self.width(), self.height() * ratio)
        h = w / ratio
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def frame(self, index):
        """The slide (or the end card) as an image the size of the target."""
        target = self._target()
        w, h = max(1, int(target.width())), max(1, int(target.height()))
        key = (index, w, h)
        if key not in self._cache:
            if len(self._cache) > 6:
                self._cache.clear()
            if index >= len(self.pres.slides):
                img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(Qt.GlobalColor.black)
                p = QPainter(img)
                p.setPen(QColor(theme.GILT_LIGHT))
                p.setFont(QFont(theme.TITLE_FAMILY, 16))
                p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "End of slide show — press Esc")
                p.end()
            else:
                img = render_slide(self.pres.slides[index], self.pres.width, self.pres.height,
                                   QSizeF(w, h))
            self._cache[key] = img
        return self._cache[key]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self.black:
            return
        target = self._target()
        new = self.frame(self.index)
        if self._from is None or self._kind == "none":
            painter.drawImage(target, new)
            return
        t, w = self._t, target.width()
        old = self._from
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._kind == "fade":
            painter.drawImage(target, old)
            painter.setOpacity(t)
            painter.drawImage(target, new)
        elif self._kind == "push":
            painter.setClipRect(target)
            painter.drawImage(target.translated(-self._dir * t * w, 0), old)
            painter.drawImage(target.translated(self._dir * (1 - t) * w, 0), new)
        elif self._kind == "cover":
            painter.setClipRect(target)
            painter.drawImage(target, old)
            painter.drawImage(target.translated(self._dir * (1 - t) * w, 0), new)
        elif self._kind == "wipe":
            painter.drawImage(target, old)
            if self._dir > 0:
                clip = QRectF(target.left(), target.top(), w * t, target.height())
            else:
                clip = QRectF(target.right() - w * t, target.top(), w * t, target.height())
            painter.setClipRect(clip)
            painter.drawImage(target, new)
        elif self._kind == "zoom":
            painter.setOpacity(1 - t)
            painter.drawImage(target, old)
            painter.setOpacity(t)
            k = 0.6 + 0.4 * t
            r = QRectF(0, 0, target.width() * k, target.height() * k)
            r.moveCenter(target.center())
            painter.drawImage(r, new)
        else:
            painter.drawImage(target, new)

    def _step(self, value):
        self._t = float(value)
        self.update()

    def _done(self):
        self._from = None
        self._t = 1.0
        self.update()

    def go(self, delta):
        new = max(0, min(len(self.pres.slides), self.index + delta))
        if new == self.index:
            return
        self.black = False
        old = self.frame(self.index)
        incoming = self.pres.slides[new] if new < len(self.pres.slides) else None
        moving_to = incoming if delta > 0 else self.pres.slides[self.index] \
            if self.index < len(self.pres.slides) else None
        kind = moving_to.transition if moving_to is not None else "none"
        self.index = new
        if self.animate and kind != "none" and abs(delta) == 1:
            self._anim.stop()
            self._from, self._kind, self._dir, self._t = old, kind, (1 if delta > 0 else -1), 0.0
            self._anim.start()
        else:
            self._from = None
        self.update()

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Escape:
            self.close()
        elif k in (Qt.Key.Key_B, Qt.Key.Key_Period):
            self.black = not self.black
            self.update()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_PageDown,
                   Qt.Key.Key_Return, Qt.Key.Key_N):
            self.go(1)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace,
                   Qt.Key.Key_P):
            self.go(-1)
        elif k == Qt.Key.Key_Home:
            self.go(-self.index)
        elif k == Qt.Key.Key_End:
            self.go(len(self.pres.slides) - 1 - self.index)

    def mousePressEvent(self, event):
        self.go(-1 if event.button() == Qt.MouseButton.RightButton else 1)


# ------------------------------------------------------------------ panel --

class SlidesPanel(QWidget):
    titleChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.undo_stack = UndoStack()
        self.pres = layouts.sample_presentation()
        self.current = 0
        self._editor: InlineEditor | None = None
        self._clipboard: list[Shape] = []
        self._refresh_pending = False
        self._syncing = False
        self.show_window = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_insert_bar())
        lay.addWidget(self._build_format_bar())
        self.find_bar = FindBar(self)
        lay.addWidget(self.find_bar)
        self._find_pos = (-1, -1)  # (slide index, shape index) of the last match

        body = QHBoxLayout()
        body.setSpacing(0)
        self.thumbs = QListWidget()
        self.thumbs.setObjectName("thumbs")
        self.thumbs.setIconSize(QSize(THUMB_W, int(THUMB_W * 9 / 16)))
        self.thumbs.setFixedWidth(THUMB_W + 36)
        self.thumbs.setSpacing(4)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.currentRowChanged.connect(self._on_thumb_changed)
        body.addWidget(self.thumbs)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.view = SlideView(self)
        self.scene = QGraphicsScene()
        self.scene.selectionChanged.connect(self._sync_format_bar)
        self.view.setScene(self.scene)
        self.notes = QPlainTextEdit()
        self.notes.setObjectName("notes")
        self.notes.setPlaceholderText("Speaker notes")
        self.notes.setFixedHeight(84)
        self.notes.installEventFilter(self)
        right.addWidget(self.view, 1)
        right.addWidget(self.notes)
        body.addLayout(right, 1)
        lay.addLayout(body, 1)

        status = QFrame()
        status.setObjectName("statusBar")
        st = QHBoxLayout(status)
        st.setContentsMargins(14, 5, 14, 5)
        hint = QLabel("Double-click a box to edit its text · drag the gold corner to resize "
                      "· F5 to present")
        hint.setObjectName("muted")
        self.status = QLabel()
        self.status.setObjectName("muted")
        st.addWidget(hint)
        st.addStretch(1)
        st.addWidget(self.status)
        lay.addWidget(status)

        self.undo_stack.subscribe(self.titleChanged.emit)
        self._refresh()

    # ---- toolbars -----------------------------------------------------------

    def _tool(self, bar, text, tip, slot=None, checkable=False):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        if slot is not None:
            b.clicked.connect(slot)
        bar.addWidget(b)
        return b

    @staticmethod
    def _divider(bar):
        d = QFrame()
        d.setObjectName("vdivider")
        d.setFixedSize(1, 22)
        bar.addWidget(d)

    def _build_insert_bar(self):
        frame = QFrame()
        frame.setObjectName("toolbar")
        bar = QHBoxLayout(frame)
        bar.setContentsMargins(14, 5, 14, 3)
        bar.setSpacing(3)
        new = self._tool(bar, "✚ New slide", "Add a slide after this one",
                         lambda: self.add_slide("Title and Content"))
        menu = QMenu(new)
        for name in layouts.LAYOUTS:
            menu.addAction(name, lambda n=name: self.add_slide(n))
        new.setMenu(menu)
        new.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._tool(bar, "Duplicate", "Duplicate this slide", self.duplicate_slide)
        self._tool(bar, "Delete slide", "Delete this slide", self.delete_slide)
        self._tool(bar, "▲", "Move slide up", lambda: self.move_slide(-1))
        self._tool(bar, "▼", "Move slide down", lambda: self.move_slide(1))
        self._divider(bar)
        self._tool(bar, "Text box", "Insert a text box", self.insert_text_box)
        shapes = self._tool(bar, "◆ Shapes ▾", "Insert a shape")
        menu = QMenu(shapes)
        for kind, label in SHAPE_MENU:
            menu.addAction(label, lambda k=kind: self.insert_shape(k))
        shapes.setMenu(menu)
        shapes.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        table = self._tool(bar, "▦ Table ▾", "Insert a table")
        menu = QMenu(table)
        for r, c in ((2, 2), (3, 3), (4, 3), (5, 4)):
            menu.addAction(f"{r} rows × {c} columns", lambda r=r, c=c: self.insert_table(r, c))
        table.setMenu(menu)
        table.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._tool(bar, "Picture", "Insert a picture from a file", self.insert_picture)
        self._divider(bar)
        arrange = self._tool(bar, "Arrange ▾", "Order, align and duplicate shapes")
        menu = QMenu(arrange)
        menu.addAction("Bring to front", lambda: self.reorder(True))
        menu.addAction("Send to back", lambda: self.reorder(False))
        menu.addAction("Duplicate (Ctrl+D)", self.duplicate_shapes)
        menu.addSeparator()
        for key, label in (("left", "Align left"), ("hcenter", "Align centre"),
                           ("right", "Align right"), ("top", "Align top"),
                           ("vcenter", "Align middle"), ("bottom", "Align bottom")):
            menu.addAction(label, lambda k=key: self.align_shapes(k))
        menu.addSeparator()
        menu.addAction("Distribute horizontally", lambda: self.distribute("h"))
        menu.addAction("Distribute vertically", lambda: self.distribute("v"))
        arrange.setMenu(menu)
        arrange.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bg = self._tool(bar, "Background", "Slide background colour")
        bg.setMenu(self._color_menu(self.set_background, allow_none=False))
        bg.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.transition_btn = self._tool(bar, "Transition ▾", "How this slide arrives in the show")
        menu = QMenu(self.transition_btn)
        self._transition_group = QActionGroup(menu)
        self._transition_actions = {}
        for name in TRANSITIONS:
            act = menu.addAction(TRANSITION_LABELS[name], lambda n=name: self.set_transition(n))
            act.setCheckable(True)
            self._transition_group.addAction(act)
            self._transition_actions[name] = act
        menu.addSeparator()
        menu.addAction("Apply to all slides", self.transition_to_all)
        self.transition_btn.setMenu(menu)
        self.transition_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._tool(bar, "⌕ Find", "Find and replace text on every slide (Ctrl+F)",
                   lambda: self.open_find(False))
        bar.addStretch(1)
        present = self._tool(bar, "▶ Present", "Start the slide show from this slide (F5)",
                             self.present)
        present.setObjectName("presentButton")
        return frame

    def _build_format_bar(self):
        frame = QFrame()
        frame.setObjectName("toolbar")
        bar = QHBoxLayout(frame)
        bar.setContentsMargins(14, 3, 14, 5)
        bar.setSpacing(3)
        self.font_box = QComboBox()
        self.font_box.setEditable(True)
        self.font_box.addItems(FONT_CHOICES)
        self.font_box.setMinimumWidth(180)
        self.font_box.activated.connect(
            lambda _i: self.format_shapes("font", self.font_box.currentText(), "Font"))
        bar.addWidget(self.font_box)
        self.size_box = QDoubleSpinBox()
        self.size_box.setRange(6, 200)
        self.size_box.setDecimals(0)
        self.size_box.setSuffix(" pt")
        self.size_box.editingFinished.connect(
            lambda: self.format_shapes("size", float(self.size_box.value()), "Font size"))
        bar.addWidget(self.size_box)
        self._divider(bar)
        self.bold = self._tool(bar, "B", "Bold", checkable=True)
        self.italic = self._tool(bar, "I", "Italic", checkable=True)
        self.underline = self._tool(bar, "U", "Underline", checkable=True)
        for b, attr, bold, italic, under in ((self.bold, "bold", True, False, False),
                                            (self.italic, "italic", False, True, False),
                                            (self.underline, "underline", False, False, True)):
            f = b.font(); f.setBold(bold); f.setItalic(italic); f.setUnderline(under); b.setFont(f)
            b.clicked.connect(lambda on, a=attr: self.format_shapes(a, on, a.title()))
        self.bullets = self._tool(bar, "• Bullets", "Bulleted text", checkable=True)
        self.bullets.clicked.connect(lambda on: self.set_shape_attr("bullets", on, "Bullets"))
        self._divider(bar)
        self.align_buttons = {}
        for key, glyph in (("left", "≡ L"), ("center", "≡ C"),
                           ("right", "≡ R")):
            b = self._tool(bar, glyph, f"Align {key}", checkable=True)
            b.clicked.connect(lambda _c=False, k=key: self.format_shapes("align", k, "Alignment"))
            self.align_buttons[key] = b
        self.valign_box = QComboBox()
        self.valign_box.addItem("Top", "top")
        self.valign_box.addItem("Middle", "middle")
        self.valign_box.addItem("Bottom", "bottom")
        self.valign_box.setMinimumWidth(90)
        self.valign_box.activated.connect(
            lambda i: self.format_shapes("valign", self.valign_box.itemData(i), "Vertical align"))
        bar.addWidget(self.valign_box)
        self._divider(bar)
        for label, tip, slot, allow_none in (
                ("A Text colour", "Text colour",
                 lambda c: self.format_shapes("color", c, "Text colour"), False),
                ("▧ Fill", "Shape fill", lambda c: self.set_shape_attr("fill", c, "Fill"), True),
                ("▢ Outline", "Shape outline",
                 lambda c: self.set_shape_attr("line", c, "Outline"), True)):
            b = self._tool(bar, label, tip)
            b.setMenu(self._color_menu(slot, allow_none))
            b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.addStretch(1)
        return frame

    def _color_menu(self, slot, allow_none):
        menu = QMenu(self)
        for name, hexv in SWATCHES:
            pm = QPixmap(14, 14)
            pm.fill(QColor(hexv))
            menu.addAction(QIcon(pm), name, lambda h=hexv: slot(h))
        if allow_none:
            menu.addAction("None", lambda: slot(None))
        menu.addSeparator()

        def custom():
            c = QColorDialog.getColor(QColor(theme.CRIMSON), self, "Choose a colour")
            if c.isValid():
                slot(c.name().upper())
        menu.addAction("Custom…", custom)
        return menu

    # ---- model access -------------------------------------------------------

    @property
    def slide(self):
        return self.pres.slides[self.current] if self.pres.slides else None

    def shape_items(self):
        return [i for i in self.scene.items() if isinstance(i, ShapeItem)]

    def selected_shapes(self):
        try:
            items = self.scene.selectedItems()
        except RuntimeError:  # the scene is being torn down as the app quits
            return []
        return [i.shape_model for i in items if isinstance(i, ShapeItem)]

    def _push(self, command, select_ids=None):
        if command is None:
            return
        if select_ids is not None:
            self._select_after = set(select_ids)
        self.undo_stack.push(command)

    def changed(self):
        """Every command calls this. Redraw once, after the current event finishes."""
        if not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(0, self._refresh)

    # ---- refresh ------------------------------------------------------------

    def _refresh(self):
        self._refresh_pending = False
        if not self.pres.slides:
            self.pres.slides.append(layouts.make_slide("Blank"))
        self.current = max(0, min(self.current, len(self.pres.slides) - 1))
        keep = getattr(self, "_select_after", None)
        if keep is None:
            keep = {s.id for s in self.selected_shapes()}
        self._select_after = None
        self._rebuild_thumbs()
        self._rebuild_scene(keep)
        if not self.notes.hasFocus():
            self.notes.setPlainText(self.slide.notes)
        trans = self.slide.transition
        self.status.setText(f"Slide {self.current + 1} of {len(self.pres.slides)}"
                            + (f" · {TRANSITION_LABELS.get(trans, trans)} transition"
                               if trans != "none" else ""))
        act = self._transition_actions.get(trans)
        if act is not None:
            act.setChecked(True)
        self._sync_format_bar()

    def _rebuild_thumbs(self):
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        size = QSizeF(THUMB_W * 2, THUMB_W * 2 * self.pres.height / self.pres.width)
        for i, slide in enumerate(self.pres.slides):
            img = render_slide(slide, self.pres.width, self.pres.height, size)
            pm = QPixmap.fromImage(img)
            icon = QIcon(pm)
            icon.addPixmap(pm, QIcon.Mode.Selected)  # no blue selection tint
            item = QListWidgetItem(icon, f"{i + 1}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            self.thumbs.addItem(item)
        self.thumbs.setCurrentRow(self.current)
        self.thumbs.blockSignals(False)

    def _rebuild_scene(self, select_ids):
        self._editor = None
        self.scene.blockSignals(True)
        self.scene.clear()
        w, h = self.pres.width, self.pres.height
        self.scene.setSceneRect(-24, -24, w + 48, h + 48)
        shadow = QGraphicsRectItem(6, 8, w, h)
        shadow.setBrush(QColor(0, 0, 0, 110))
        shadow.setPen(Qt.PenStyle.NoPen)
        self.scene.addItem(shadow)
        bg = QGraphicsRectItem(0, 0, w, h)
        bg.setBrush(QColor(self.slide.background))
        bg.setPen(QPen(QColor(theme.GILT), 0))
        self.scene.addItem(bg)
        for shape in self.slide.shapes:
            item = ShapeItem(shape, self)
            self.scene.addItem(item)
            if shape.id in select_ids:
                item.setSelected(True)
        self.scene.blockSignals(False)
        self.view.fit()

    def _on_thumb_changed(self, row):
        if row < 0 or row == self.current:
            return
        self._commit_notes()
        self.current = row
        self._select_after = set()
        self._refresh()

    def _sync_format_bar(self):
        shapes = self.selected_shapes()
        st = shapes[0].style if shapes else TextStyle()
        self._syncing = True
        self.font_box.setCurrentText(st.font)
        self.size_box.setValue(st.size)
        self.bold.setChecked(st.bold)
        self.italic.setChecked(st.italic)
        self.underline.setChecked(st.underline)
        self.bullets.setChecked(bool(shapes) and shapes[0].bullets)
        for k, b in self.align_buttons.items():
            b.setChecked(k == st.align)
        self.valign_box.setCurrentIndex(self.valign_box.findData(st.valign))
        self._syncing = False

    # ---- slide operations --------------------------------------------------

    def add_slide(self, layout):
        index = self.current + 1 if self.pres.slides else 0
        self.current = index
        self._push(AddSlideCommand(self.pres, index, layouts.make_slide(layout), self.changed,
                                   text=f"New slide ({layout})"), select_ids=())

    def duplicate_slide(self):
        clone = self.slide.clone()
        self.current += 1
        self._push(AddSlideCommand(self.pres, self.current, clone, self.changed,
                                   text="Duplicate slide"), select_ids=())

    def delete_slide(self):
        if len(self.pres.slides) <= 1:
            return
        self._push(DeleteSlideCommand(self.pres, self.current, self.changed), select_ids=())

    def move_slide(self, delta):
        dst = self.current + delta
        if 0 <= dst < len(self.pres.slides):
            src, self.current = self.current, dst
            self._push(MoveSlideCommand(self.pres, src, dst, self.changed))

    def set_background(self, color):
        self._push(set_attrs([(self.slide, "background", color)], "Background", self.changed))

    # ---- shape operations ---------------------------------------------------

    def _centered(self, w, h):
        return (self.pres.width - w) / 2, (self.pres.height - h) / 2

    def insert_text_box(self):
        x, y = self._centered(360, 60)
        shape = Shape("text", x, y, 360, 60, text="Text",
                      style=TextStyle(theme.BODY_FAMILY, 26, color=layouts.INK))
        self._push(AddShapeCommand(self.slide, shape, self.changed, "Insert text box"),
                   select_ids=[shape.id])
        QTimer.singleShot(0, lambda: self._edit_by_id(shape.id))

    def insert_shape(self, kind):
        x, y = self._centered(220, 140)
        w, h = (220, 140) if kind not in ("star", "diamond", "hexagon", "triangle") else (180, 170)
        x, y = self._centered(w, h)
        shape = Shape(kind, x, y, w, h, fill=layouts.CRIMSON, line=layouts.GILT,
                      line_width=2.0,
                      style=TextStyle(theme.TITLE_FAMILY, 20, color=layouts.IVORY,
                                      align="center", valign="middle"))
        name = dict(SHAPE_MENU).get(kind, "shape").split(" ", 1)[-1].lower()
        self._push(AddShapeCommand(self.slide, shape, self.changed, "Insert " + name),
                   select_ids=[shape.id])

    def insert_picture(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Insert picture", "", "Images (*.png *.jpg *.jpeg *.gif *.bmp)")
        if not path:
            return
        data = Path(path).read_bytes()
        img = QImage.fromData(data)
        if img.isNull():
            return
        scale = min(1.0, self.pres.width * 0.6 / img.width(), self.pres.height * 0.6 / img.height())
        w, h = img.width() * scale, img.height() * scale
        x, y = self._centered(w, h)
        shape = Shape("image", x, y, w, h, image=data)
        self._push(AddShapeCommand(self.slide, shape, self.changed, "Insert picture"),
                   select_ids=[shape.id])

    def delete_shapes(self):
        shapes = self.selected_shapes()
        if shapes:
            self._push(DeleteShapesCommand(self.slide, shapes, self.changed), select_ids=())

    def copy_shapes(self):
        self._clipboard = [s.clone() for s in self.selected_shapes()]

    def paste_shapes(self):
        if not self._clipboard:
            return
        pasted = []
        for s in self._clipboard:
            twin = s.clone()
            twin.x += 14
            twin.y += 14
            pasted.append(twin)
        self._clipboard = [s.clone() for s in pasted]  # next paste steps further
        self._push(MacroCommand("Paste", [AddShapeCommand(self.slide, s, self.changed)
                                          for s in pasted]),
                   select_ids=[s.id for s in pasted])

    def reorder(self, to_front):
        shapes = self.selected_shapes()
        if len(shapes) == 1:
            self._push(ReorderShapeCommand(self.slide, shapes[0], to_front, self.changed))

    def nudge(self, dx, dy):
        shapes = self.selected_shapes()
        changes = [(s, "x", s.x + dx) for s in shapes] + [(s, "y", s.y + dy) for s in shapes]
        key = ("nudge", tuple(sorted(s.id for s in shapes)))
        self._push(set_attrs(changes, "Move", self.changed, merge_key=key))

    def format_shapes(self, attr, value, label):
        if self._syncing:
            return
        shapes = self.selected_shapes()
        self._push(set_attrs([(s.style, attr, value) for s in shapes], label, self.changed))

    def set_shape_attr(self, attr, value, label):
        shapes = self.selected_shapes()
        self._push(set_attrs([(s, attr, value) for s in shapes], label, self.changed))

    def commit_geometry(self):
        """After a drag: turn every moved or resized item into one command."""
        changes = []
        for item in self.shape_items():
            s = item.shape_model
            pos = item.pos()
            changes += [(s, "x", round(pos.x(), 1)), (s, "y", round(pos.y(), 1)),
                        (s, "w", round(item.w, 1)), (s, "h", round(item.h, 1))]
        cmd = set_attrs(changes, "Move", self.changed)
        if cmd is not None:
            resized = any(n in ("w", "h") for _o, n, _a, _b in cmd.changes)
            cmd.text = "Resize" if resized else "Move"
            self._push(cmd)

    def insert_table(self, rows=3, cols=3):
        w, h = min(760.0, 150.0 * cols), 44.0 * rows
        x, y = self._centered(w, h)
        header = "\t".join(f"Heading {c + 1}" for c in range(cols))
        body = ["\t".join("" for _ in range(cols)) for _ in range(rows - 1)]
        shape = Shape("table", x, y, w, h, text="\n".join([header] + body), line=layouts.GILT,
                      style=TextStyle(theme.BODY_FAMILY, 18, color=layouts.INK))
        self._push(AddShapeCommand(self.slide, shape, self.changed, "Insert table"),
                   select_ids=[shape.id])
        return shape

    def insert_image_data(self, data: bytes, label="Insert picture"):
        img = QImage.fromData(data)
        if img.isNull():
            return None
        scale = min(1.0, self.pres.width * 0.7 / img.width(), self.pres.height * 0.7 / img.height())
        w, h = img.width() * scale, img.height() * scale
        x, y = self._centered(w, h)
        shape = Shape("image", x, y, w, h, image=data)
        self._push(AddShapeCommand(self.slide, shape, self.changed, label), select_ids=[shape.id])
        return shape

    def duplicate_shapes(self):
        shapes = self.selected_shapes()
        if not shapes:
            return
        twins = []
        for s in shapes:
            twin = s.clone()
            twin.x += 18
            twin.y += 18
            twins.append(twin)
        self._push(MacroCommand("Duplicate", [AddShapeCommand(self.slide, t, self.changed)
                                              for t in twins]),
                   select_ids=[t.id for t in twins])

    def align_shapes(self, edge):
        """One shape aligns to the slide; several align to each other."""
        shapes = self.selected_shapes()
        if not shapes:
            return
        if len(shapes) == 1:
            left, top, right, bottom = 0.0, 0.0, self.pres.width, self.pres.height
        else:
            left = min(s.x for s in shapes)
            top = min(s.y for s in shapes)
            right = max(s.x + s.w for s in shapes)
            bottom = max(s.y + s.h for s in shapes)
        changes = []
        for s in shapes:
            if edge == "left":
                changes.append((s, "x", round(left, 1)))
            elif edge == "right":
                changes.append((s, "x", round(right - s.w, 1)))
            elif edge == "hcenter":
                changes.append((s, "x", round((left + right - s.w) / 2, 1)))
            elif edge == "top":
                changes.append((s, "y", round(top, 1)))
            elif edge == "bottom":
                changes.append((s, "y", round(bottom - s.h, 1)))
            elif edge == "vcenter":
                changes.append((s, "y", round((top + bottom - s.h) / 2, 1)))
        self._push(set_attrs(changes, "Align", self.changed))

    def distribute(self, axis):
        shapes = self.selected_shapes()
        if len(shapes) < 3:
            return
        pos, size = ("x", "w") if axis == "h" else ("y", "h")
        shapes = sorted(shapes, key=lambda s: getattr(s, pos))
        first, last = shapes[0], shapes[-1]
        span = getattr(last, pos) + getattr(last, size) - getattr(first, pos)
        gap = (span - sum(getattr(s, size) for s in shapes)) / (len(shapes) - 1)
        at, changes = getattr(first, pos), []
        for s in shapes:
            changes.append((s, pos, round(at, 1)))
            at += getattr(s, size) + gap
        self._push(set_attrs(changes, "Distribute", self.changed))

    def set_transition(self, name):
        self._push(set_attrs([(self.slide, "transition", name)], "Transition", self.changed))

    def transition_to_all(self):
        name = self.slide.transition
        self._push(set_attrs([(s, "transition", name) for s in self.pres.slides],
                             "Transition for all slides", self.changed))

    # ---- find and replace ---------------------------------------------------

    def open_find(self, replace=False):
        self.find_bar.open_bar(replace)

    def find_closed(self):
        self.view.setFocus()

    @staticmethod
    def _pattern(text, match_case, whole):
        import re
        body = re.escape(text)
        if whole:
            body = rf"\b{body}\b"
        return re.compile(body, 0 if match_case else re.IGNORECASE)

    def _text_spots(self):
        """(slide index, shape index, object, attribute) for every piece of text."""
        for si, slide in enumerate(self.pres.slides):
            for hi, shape in enumerate(slide.shapes):
                if shape.text:
                    yield si, hi, shape
        return

    def find(self, text, forward=True, match_case=False, whole=False):
        rx = self._pattern(text, match_case, whole)
        spots = [(si, hi, sh) for si, hi, sh in self._text_spots() if rx.search(sh.text)]
        if not spots:
            return False
        cur = self._find_pos
        if forward:
            hit = next((x for x in spots if (x[0], x[1]) > cur), spots[0])
        else:
            hit = next((x for x in reversed(spots) if (x[0], x[1]) < cur), spots[-1])
        self._find_pos = (hit[0], hit[1])
        self.current = hit[0]
        self._select_after = {hit[2].id}
        self._refresh()
        return True

    def replace(self, text, new, match_case=False, whole=False):
        si, hi = self._find_pos
        if not (0 <= si < len(self.pres.slides)) or hi >= len(self.pres.slides[si].shapes):
            return False
        shape = self.pres.slides[si].shapes[hi]
        rx = self._pattern(text, match_case, whole)
        out = rx.sub(lambda _m: new, shape.text, count=1)
        if out == shape.text:
            return False
        self._push(set_attrs([(shape, "text", out)], "Replace", self.changed))
        return True

    def replace_all(self, text, new, match_case=False, whole=False):
        rx = self._pattern(text, match_case, whole)
        changes, count = [], 0
        for _si, _hi, shape in self._text_spots():
            out, n = rx.subn(lambda _m: new, shape.text)
            if n:
                changes.append((shape, "text", out))
                count += n
        self._push(set_attrs(changes, "Replace all", self.changed))
        return count

    # ---- text editing -------------------------------------------------------

    def _edit_by_id(self, shape_id):
        for item in self.shape_items():
            if item.shape_model.id == shape_id:
                self.begin_text_edit(item)
                cursor = self._editor.textCursor()
                cursor.select(cursor.SelectionType.Document)
                self._editor.setTextCursor(cursor)

    def begin_text_edit(self, item: ShapeItem):
        if self._editor is not None:
            return
        item.editing = True
        item.update()
        self._editor = InlineEditor(item, self)
        self.scene.addItem(self._editor)
        self._editor.setFocus()

    def finish_text_edit(self):
        editor, self._editor = self._editor, None
        if editor is None or editor.scene() is None:
            return
        text = editor.toPlainText()
        item = editor.item
        item.editing = False
        self.scene.removeItem(editor)
        item.update()
        self._push(set_attrs([(item.shape_model, "text", text)], "Edit text", self.changed))

    # ---- notes --------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.notes and event.type() == QEvent.Type.FocusOut:
            self._commit_notes()
        return super().eventFilter(obj, event)

    def _commit_notes(self):
        if self.slide is not None:
            self._push(set_attrs([(self.slide, "notes", self.notes.toPlainText())], "Notes",
                                 self.changed, merge_key=("notes", self.slide.id)))

    # ---- presenting ---------------------------------------------------------

    def present(self):
        self.show_window = SlideShow(self.pres, self.current)
        self.show_window.showFullScreen()

    # ---- file I/O / undo hooks used by the main window ----------------------

    @property
    def modified(self):
        return not self.undo_stack.is_clean()

    def display_name(self):
        name = self.path.name if self.path else "Untitled.pptx"
        return name + (" • edited" if self.modified else "")

    def load(self, pres, path=None):
        self.pres = pres
        self.path = Path(path) if path else None
        self.current = 0
        self.undo_stack.clear()
        self._select_after = set()
        self._refresh()
        self.titleChanged.emit()

    def new_file(self):
        self.load(Presentation([layouts.make_slide("Title")]))

    def open_file(self, path):
        self.load(open_pptx(path), path)

    def export_pdf(self, path):
        """Every slide on its own page, drawn as vectors so text stays sharp."""
        from PySide6.QtGui import QPdfWriter

        self._commit_notes()
        w, h = self.pres.width, self.pres.height
        writer = QPdfWriter(str(path))
        writer.setTitle(self.path.stem if self.path else "Presentation")
        writer.setPageLayout(QPageLayout(QPageSize(QSizeF(w, h), QPageSize.Unit.Point),
                                         QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
        writer.setResolution(144)
        painter = QPainter(writer)
        target = QRectF(0, 0, writer.width(), writer.height())
        for i, slide in enumerate(self.pres.slides):
            if i:
                writer.newPage()
            scene = build_static_scene(slide, w, h)
            scene.render(painter, target, QRectF(0, 0, w, h))
        painter.end()

    def export_slide_png(self, path, index=None):
        slide = self.pres.slides[self.current if index is None else index]
        img = render_slide(slide, self.pres.width, self.pres.height, QSizeF(1920, 1080))
        return img.save(str(path), "PNG")

    def save_file(self, path):
        self._commit_notes()
        save_pptx(self.pres, path)
        self.path = Path(path)
        self.undo_stack.set_clean()
