"""The Writer tab: a formatting toolbar over a QTextEdit page."""
import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QKeySequence, QPageLayout, QPageSize, QPixmap, QTextCharFormat,
    QTextCursor, QTextDocument,
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QMenu, QSpinBox, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from .. import theme
from ..findbar import FindBar
from ..undo import Command, UndoStack
from .docx_io import open_docx, save_docx
from .document import Paragraph
from .qt_bridge import (
    BODY_PT, apply_style, block_align, block_style, heading_char_format,
    insert_image, insert_table, load_paragraphs, set_alignment, to_paragraphs,
)

FONT_CHOICES = [theme.BODY_FAMILY, theme.TITLE_FAMILY, theme.BLACKLETTER_FAMILY, "Georgia",
                "Times New Roman", "Garamond", "Palatino Linotype", "Arial", "Courier New"]
SIZE_CHOICES = [8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 36, 48, 60, 72]
TEXT_SWATCHES = [("Ink", theme.INK), ("Crimson", theme.CRIMSON), ("Oxblood", theme.OXBLOOD),
                 ("Gilt", theme.GILT), ("Muted", theme.MUTED), ("Black", "#000000")]
HIGHLIGHT_SWATCHES = [("Pale gold", "#F3E2A9"), ("Rose", theme.PRECEDENT), ("Vellum", theme.VELLUM),
                      ("Sage", "#DDE5C8"), ("Sky", "#D6E4EE")]

STYLE_CHOICES = [("Body", "normal"), ("Heading I", "h1"), ("Heading II", "h2"),
                 ("Heading III", "h3")]
STYLE_LABELS = {key: label for label, key in STYLE_CHOICES}
STYLE_LABELS.update(bullet="Bulleted list", number="Numbered list")


class TextDocumentCommand(Command):
    """One step of QTextDocument's own undo history, driven from our stack.

    Qt's text engine already records exactly what each keystroke or format
    change did. Rather than duplicate that, each step it adds becomes one
    command here, so Writer, Sheets and Slides all share the same UndoStack
    and the same Undo/Redo buttons.
    """

    def __init__(self, document, text="Typing"):
        self.document = document
        self.text = text

    def redo(self):
        self.document.redo()

    def undo(self):
        self.document.undo()


class Editor(QTextEdit):
    """QTextEdit whose Ctrl+Z / Ctrl+Y and context menu go to our UndoStack."""

    def __init__(self, undo_stack: UndoStack):
        super().__init__()
        self.undo_stack = undo_stack

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            return self.undo_stack.undo()
        if event.matches(QKeySequence.StandardKey.Redo) or (
                event.key() == Qt.Key.Key_Y
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            return self.undo_stack.redo()
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        panel = getattr(self, "panel", None)
        if panel is not None and self.textCursor().currentTable() is not None:
            menu.addSeparator()
            panel.add_table_actions(menu)
        for action in menu.actions():
            if action.objectName() == "edit-undo":
                action.triggered.disconnect()
                action.triggered.connect(self.undo_stack.undo)
                action.setEnabled(self.undo_stack.can_undo())
            elif action.objectName() == "edit-redo":
                action.triggered.disconnect()
                action.triggered.connect(self.undo_stack.redo)
                action.setEnabled(self.undo_stack.can_redo())
        menu.exec(event.globalPos())


class WriterPanel(QWidget):
    titleChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.undo_stack = UndoStack()
        self._next_label = None  # names the next undo step ("Bold", "Heading I", ...)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("toolbar")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 5, 14, 3)
        bar_lay.setSpacing(3)
        bar2 = QFrame()
        bar2.setObjectName("toolbar")
        bar2_lay = QHBoxLayout(bar2)
        bar2_lay.setContentsMargins(14, 3, 14, 5)
        bar2_lay.setSpacing(3)

        self.style_box = QComboBox()
        for label, key in STYLE_CHOICES:
            self.style_box.addItem(label, key)
        bar_lay.addWidget(self.style_box)
        self.font_box = QComboBox()
        self.font_box.setEditable(True)
        self.font_box.addItems(FONT_CHOICES)
        self.font_box.setMinimumWidth(170)
        self.font_box.setToolTip("Font")
        bar_lay.addWidget(self.font_box)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.addItems([str(n) for n in SIZE_CHOICES])
        self.size_box.setMinimumWidth(70)
        self.size_box.setMaximumWidth(80)
        self.size_box.setToolTip("Font size (points)")
        bar_lay.addWidget(self.size_box)
        bar_lay.addWidget(_divider())

        def tool(text, tip, shortcut=None, checkable=True, layout=bar_lay):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(checkable)
            b.setToolTip(tip + (f" ({QKeySequence(shortcut).toString()})" if shortcut else ""))
            if shortcut:
                b.setShortcut(QKeySequence(shortcut))
            layout.addWidget(b)
            return b

        self.bold = tool("B", "Bold", "Ctrl+B")
        f = self.bold.font(); f.setBold(True); self.bold.setFont(f)
        self.italic = tool("I", "Italic", "Ctrl+I")
        f = self.italic.font(); f.setItalic(True); self.italic.setFont(f)
        self.underline = tool("U", "Underline", "Ctrl+U")
        f = self.underline.font(); f.setUnderline(True); self.underline.setFont(f)
        self.strike = tool("S", "Strikethrough", "Ctrl+Shift+X")
        f = self.strike.font(); f.setStrikeOut(True); self.strike.setFont(f)
        bar_lay.addWidget(_divider())
        self.color_btn = tool("A Colour", "Text colour", checkable=False)
        self.color_btn.setMenu(self._color_menu(TEXT_SWATCHES, self.set_text_color, "Automatic"))
        self.color_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.highlight_btn = tool("▮ Highlight", "Highlight colour", checkable=False)
        self.highlight_btn.setMenu(self._color_menu(HIGHLIGHT_SWATCHES, self.set_highlight, "None"))
        self.highlight_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.clear_btn = tool("⌫ Clear", "Clear formatting from the selection", "Ctrl+Space",
                              checkable=False)
        bar_lay.addStretch(1)

        self.align_buttons = {}
        for key, glyph, tip, sc in (("left", "≡ L", "Align left", "Ctrl+L"),
                                    ("center", "≡ C", "Centre", "Ctrl+E"),
                                    ("right", "≡ R", "Align right", "Ctrl+R"),
                                    ("justify", "≡ J", "Justify", "Ctrl+J")):
            self.align_buttons[key] = tool(glyph, tip, sc, layout=bar2_lay)
        bar2_lay.addWidget(_divider())
        self.bullets = tool("• List", "Bulleted list", "Ctrl+Shift+8", layout=bar2_lay)
        self.numbers = tool("1. List", "Numbered list", "Ctrl+Shift+7", layout=bar2_lay)
        bar2_lay.addWidget(_divider())
        self.table_btn = tool("▦ Table", "Insert a table", checkable=False, layout=bar2_lay)
        table_menu = QMenu(self.table_btn)
        for r, c in ((2, 2), (3, 3), (4, 3), (5, 4)):
            table_menu.addAction(f"{r} rows × {c} columns",
                                 lambda r=r, c=c: self.insert_table(r, c))
        table_menu.addAction("Custom size…", self.insert_table_dialog)
        table_menu.addSeparator()
        self._table_actions_menu = table_menu
        self.add_table_actions(table_menu)
        self.table_btn.setMenu(table_menu)
        self.table_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.picture_btn = tool("🖼 Picture", "Insert a picture", checkable=False, layout=bar2_lay)
        self.rule_btn = tool("❦ Ornament", "Insert a centred fleuron between sections",
                             checkable=False, layout=bar2_lay)
        bar2_lay.addWidget(_divider())
        self.find_btn = tool("⌕ Find", "Find and replace (Ctrl+F, Ctrl+H)", checkable=False,
                             layout=bar2_lay)
        bar2_lay.addStretch(1)
        self.pdf_btn = tool("Export PDF", "Save a PDF copy", checkable=False, layout=bar2_lay)
        lay.addWidget(bar)
        lay.addWidget(bar2)
        self.find_bar = FindBar(self)
        lay.addWidget(self.find_bar)

        area = QWidget()
        area.setObjectName("pageArea")
        area_lay = QHBoxLayout(area)
        area_lay.setContentsMargins(28, 28, 28, 28)
        self.editor = Editor(self.undo_stack)
        self.editor.panel = self
        self.editor.setObjectName("page")
        self.editor.setAcceptRichText(False)  # pasted text comes in plain
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor.setMaximumWidth(800)
        doc = self.editor.document()
        doc.setDocumentMargin(56)
        font = QFont(theme.BODY_FAMILY)
        font.setPointSize(BODY_PT)
        doc.setDefaultFont(font)
        doc.setDefaultStyleSheet("")
        area_lay.addStretch(1)
        area_lay.addWidget(self.editor, 8)
        area_lay.addStretch(1)
        lay.addWidget(area, 1)

        status = QFrame()
        status.setObjectName("statusBar")
        st = QHBoxLayout(status)
        st.setContentsMargins(14, 5, 14, 5)
        hint = QLabel("Ctrl+B, Ctrl+I, Ctrl+U for emphasis · Shift+Enter for a line break "
                      "· Ctrl+F to find")
        hint.setObjectName("muted")
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        st.addWidget(hint)
        st.addStretch(1)
        st.addWidget(self.count_label)
        lay.addWidget(status)

        self.bold.clicked.connect(lambda on: self._merge("Bold", weight=on))
        self.italic.clicked.connect(lambda on: self._merge("Italic", italic=on))
        self.underline.clicked.connect(lambda on: self._merge("Underline", underline=on))
        for key, b in self.align_buttons.items():
            b.clicked.connect(lambda _c=False, k=key: self._align(k))
        self.strike.clicked.connect(lambda on: self._apply("Strikethrough", strike=on))
        self.clear_btn.clicked.connect(self.clear_formatting)
        self.font_box.activated.connect(lambda _i: self.set_font(self.font_box.currentText()))
        self.font_box.lineEdit().returnPressed.connect(
            lambda: self.set_font(self.font_box.currentText()))
        self.size_box.activated.connect(lambda _i: self.set_size(self.size_box.currentText()))
        self.size_box.lineEdit().returnPressed.connect(
            lambda: self.set_size(self.size_box.currentText()))
        self.picture_btn.clicked.connect(lambda: self.insert_picture())
        self.rule_btn.clicked.connect(self.insert_ornament)
        self.find_btn.clicked.connect(lambda: self.open_find(False))
        self.bullets.clicked.connect(lambda: self._set_style("bullet"))
        self.numbers.clicked.connect(lambda: self._set_style("number"))
        self.style_box.activated.connect(
            lambda i: self._set_style(self.style_box.itemData(i)))
        self.editor.cursorPositionChanged.connect(self._sync_toolbar)
        self.editor.currentCharFormatChanged.connect(lambda _f: self._sync_toolbar())
        doc.undoCommandAdded.connect(self._record_qt_step)
        doc.contentsChanged.connect(self._update_count)
        self.undo_stack.subscribe(self.titleChanged.emit)

    # ---- undo integration ---------------------------------------------------

    def _record_qt_step(self):
        label, self._next_label = self._next_label or "Typing", None
        self.undo_stack.push(TextDocumentCommand(self.editor.document(), label),
                             already_done=True)

    @property
    def modified(self):
        return not self.undo_stack.is_clean()

    # ---- formatting ---------------------------------------------------------

    def _merge(self, label, weight=None, italic=None, underline=None):
        cf = QTextCharFormat()
        if weight is not None:
            cf.setFontWeight(QFont.Weight.Bold if weight else QFont.Weight.Normal)
        if italic is not None:
            cf.setFontItalic(italic)
        if underline is not None:
            cf.setFontUnderline(underline)
        self._merge_format(label, cf)

    def _merge_format(self, label, cf):
        self._next_label = label
        self.editor.mergeCurrentCharFormat(cf)
        self._next_label = None
        self.editor.setFocus()

    def _apply(self, label, strike=None):
        cf = QTextCharFormat()
        if strike is not None:
            cf.setFontStrikeOut(strike)
        self._merge_format(label, cf)

    def set_font(self, family):
        family = family.strip()
        if not family:
            return
        cf = QTextCharFormat()
        cf.setFontFamilies([family])
        self._merge_format("Font", cf)

    def set_size(self, size):
        try:
            pt = float(str(size).strip())
        except ValueError:
            self._sync_toolbar()
            return
        if not 4 <= pt <= 400:
            return
        cf = QTextCharFormat()
        cf.setFontPointSize(pt)
        self._merge_format("Font size", cf)

    def set_text_color(self, color):
        cf = QTextCharFormat()
        if color is None:
            level = self.editor.textCursor().blockFormat().headingLevel()
            color = theme.CRIMSON if level else theme.INK
        cf.setForeground(QColor(color))
        self._merge_format("Text colour", cf)

    def set_highlight(self, color):
        cursor = self.editor.textCursor()
        if color is None:
            # mergeCharFormat can't remove a property, so clear it fragment by fragment.
            self._next_label = "Highlight"
            self._edit_fragments(cursor, lambda cf: cf.clearBackground())
            self._next_label = None
            return
        cf = QTextCharFormat()
        cf.setBackground(QColor(color))
        self._merge_format("Highlight", cf)

    def _edit_fragments(self, cursor, change):
        """Rewrite the char format of every fragment in the selection."""
        if not cursor.hasSelection():
            cf = self.editor.currentCharFormat()
            change(cf)
            self.editor.setCurrentCharFormat(cf)
            return
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        doc = self.editor.document()
        pieces = []
        block = doc.findBlock(start)
        while block.isValid() and block.position() <= end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                lo = max(start, frag.position())
                hi = min(end, frag.position() + frag.length())
                if lo < hi and not frag.charFormat().isImageFormat():
                    pieces.append((lo, hi, QTextCharFormat(frag.charFormat())))
                it += 1
            block = block.next()
        c = QTextCursor(doc)
        c.beginEditBlock()
        for lo, hi, cf in pieces:
            change(cf)
            c.setPosition(lo)
            c.setPosition(hi, QTextCursor.MoveMode.KeepAnchor)
            c.setCharFormat(cf)
        c.endEditBlock()
        self.editor.setFocus()

    def clear_formatting(self):
        """Back to the paragraph style's own look: no bold, colour, size or font."""
        cursor = self.editor.textCursor()
        level = cursor.blockFormat().headingLevel()
        base = heading_char_format(level)
        self._next_label = "Clear formatting"
        self._edit_fragments(cursor, lambda cf: (cf.clearBackground(), cf.merge(base),
                                                 cf.setFontItalic(False),
                                                 cf.setFontUnderline(False),
                                                 cf.setFontStrikeOut(False)))
        self._next_label = None
        self._sync_toolbar()

    def _color_menu(self, swatches, slot, none_label):
        menu = QMenu(self)
        for name, hexv in swatches:
            pm = QPixmap(14, 14)
            pm.fill(QColor(hexv))
            menu.addAction(QIcon(pm), name, lambda h=hexv: slot(h))
        menu.addAction(none_label, lambda: slot(None))
        menu.addSeparator()

        def custom():
            c = QColorDialog.getColor(QColor(theme.CRIMSON), self, "Choose a colour")
            if c.isValid():
                slot(c.name().upper())
        menu.addAction("Custom…", custom)
        return menu

    # ---- tables, pictures, ornaments ---------------------------------------

    def insert_table(self, rows, cols):
        self._next_label = "Insert table"
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        # Qt puts the table after the cursor's paragraph, so start from its end.
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        table = insert_table(cursor, rows, cols)
        cursor.endEditBlock()
        self._next_label = None
        self.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.editor.setFocus()
        return table

    def insert_table_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Insert table")
        form = QFormLayout(dlg)
        rows, cols = QSpinBox(), QSpinBox()
        rows.setRange(1, 200)
        cols.setRange(1, 30)
        rows.setValue(3)
        cols.setValue(3)
        form.addRow("Rows", rows)
        form.addRow("Columns", cols)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec():
            self.insert_table(rows.value(), cols.value())

    def add_table_actions(self, menu):
        for label, fn in (("Insert row above", lambda: self.table_op("row", 0)),
                          ("Insert row below", lambda: self.table_op("row", 1)),
                          ("Insert column left", lambda: self.table_op("col", 0)),
                          ("Insert column right", lambda: self.table_op("col", 1)),
                          ("Delete row", lambda: self.table_op("del_row")),
                          ("Delete column", lambda: self.table_op("del_col")),
                          ("Delete table", lambda: self.table_op("del_table"))):
            action = menu.addAction(label, fn)
            action.setData("table-op")

    def table_op(self, op, after=0):
        cursor = self.editor.textCursor()
        table = cursor.currentTable()
        if table is None:
            return False
        cell = table.cellAt(cursor)
        r, c = cell.row(), cell.column()
        labels = {"row": "Insert row", "col": "Insert column", "del_row": "Delete row",
                  "del_col": "Delete column", "del_table": "Delete table"}
        self._next_label = labels[op]
        if op == "row":
            table.insertRows(r + after, 1)
        elif op == "col":
            table.insertColumns(c + after, 1)
        elif op == "del_row":
            if table.rows() == 1:
                op = "del_table"
            else:
                table.removeRows(r, 1)
        elif op == "del_col":
            if table.columns() == 1:
                op = "del_table"
            else:
                table.removeColumns(c, 1)
        if op == "del_table":
            c2 = QTextCursor(self.editor.document())
            c2.setPosition(table.firstPosition() - 1)
            c2.setPosition(table.lastPosition() + 1, QTextCursor.MoveMode.KeepAnchor)
            c2.removeSelectedText()
        self._next_label = None
        self.editor.setFocus()
        return True

    def insert_picture(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Insert picture", "", "Images (*.png *.jpg *.jpeg *.gif *.bmp)")
        if not path:
            return False
        data = Path(path).read_bytes()
        return self.insert_picture_data(data)

    def insert_picture_data(self, data: bytes):
        cursor = self.editor.textCursor()
        self._next_label = "Insert picture"
        cursor.beginEditBlock()
        if cursor.block().text():
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertBlock()
        bf = cursor.blockFormat()
        bf.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        cursor.setBlockFormat(bf)
        ok = insert_image(cursor, data)
        cursor.endEditBlock()
        self._next_label = None
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        return ok

    def insert_ornament(self):
        """A centred fleuron in gilt, the baroque way to break a section."""
        cursor = self.editor.textCursor()
        self._next_label = "Insert ornament"
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        bf = cursor.blockFormat()
        cursor.insertBlock()
        orn = cursor.blockFormat()
        orn.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        orn.setHeadingLevel(0)
        orn.setTopMargin(8)
        orn.setBottomMargin(8)
        cursor.setBlockFormat(orn)
        cf = heading_char_format(0)
        cf.setForeground(QColor(theme.GILT))
        cf.setFontPointSize(18)
        cursor.insertText("❦  ❧  ❦", cf)
        bf.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cursor.insertBlock(bf, heading_char_format(0))
        cursor.endEditBlock()
        self._next_label = None
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    # ---- find and replace ---------------------------------------------------

    def open_find(self, replace=False):
        selected = self.editor.textCursor().selectedText()
        self.find_bar.open_bar(replace, selected if selected and "\u2029" not in selected else "")

    def find_closed(self):
        self.editor.setFocus()

    @staticmethod
    def _flags(forward, match_case, whole):
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        if match_case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole:
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags

    def find(self, text, forward=True, match_case=False, whole=False):
        doc = self.editor.document()
        flags = self._flags(forward, match_case, whole)
        found = doc.find(text, self.editor.textCursor(), flags)
        if found.isNull():  # wrap around
            start = QTextCursor(doc)
            if not forward:
                start.movePosition(QTextCursor.MoveOperation.End)
            found = doc.find(text, start, flags)
        if found.isNull():
            return False
        self.editor.setTextCursor(found)
        return True

    def _matches(self, selected, text, match_case):
        return selected == text if match_case else selected.lower() == text.lower()

    def replace(self, text, new, match_case=False, whole=False):
        cursor = self.editor.textCursor()
        if not cursor.hasSelection() or not self._matches(cursor.selectedText(), text,
                                                          match_case):
            return False
        self._next_label = "Replace"
        cursor.insertText(new)
        self._next_label = None
        return True

    def replace_all(self, text, new, match_case=False, whole=False):
        doc = self.editor.document()
        flags = self._flags(True, match_case, whole)
        edit = QTextCursor(doc)
        cursor = doc.find(text, QTextCursor(doc), flags)
        if cursor.isNull():
            return 0
        count = 0
        self._next_label = "Replace all"
        edit.beginEditBlock()
        while not cursor.isNull():
            cursor.insertText(new)
            count += 1
            cursor = doc.find(text, cursor, flags)
        edit.endEditBlock()
        self._next_label = None
        return count

    def _set_style(self, style):
        self._next_label = STYLE_LABELS.get(style, "Style")
        apply_style(self.editor.textCursor(), style)
        self._next_label = None
        self._sync_toolbar()
        self.editor.setFocus()

    def _align(self, align):
        self._next_label = "Alignment"
        set_alignment(self.editor.textCursor(), align)
        self._next_label = None
        self._sync_toolbar()
        self.editor.setFocus()

    def _sync_toolbar(self):
        cf = self.editor.currentCharFormat()
        self.bold.setChecked(cf.fontWeight() >= QFont.Weight.DemiBold.value)
        self.italic.setChecked(cf.fontItalic())
        self.underline.setChecked(cf.fontUnderline())
        self.strike.setChecked(cf.fontStrikeOut())
        fams = cf.fontFamilies() or [theme.BODY_FAMILY]
        if not self.font_box.hasFocus():
            self.font_box.setCurrentText(fams[0])
        if not self.size_box.hasFocus():
            pt = cf.fontPointSize() or BODY_PT
            self.size_box.setCurrentText(f"{pt:g}")
        block = self.editor.textCursor().block()
        style = block_style(block)
        self.bullets.setChecked(style == "bullet")
        self.numbers.setChecked(style == "number")
        heading = style if style.startswith("h") else "normal"
        self.style_box.setCurrentIndex(self.style_box.findData(heading))
        align = block_align(block)
        for key, b in self.align_buttons.items():
            b.setChecked(key == align)

    def _update_count(self):
        text = self.editor.toPlainText()
        words = len(re.findall(r"\S+", text))
        self.count_label.setText(f"{words} word{'s' if words != 1 else ''} · "
                                 f"{len(text.replace(chr(10), ''))} characters")

    # ---- file I/O -----------------------------------------------------------

    def display_name(self):
        name = self.path.name if self.path else "Untitled.docx"
        return name + (" • edited" if self.modified else "")

    def load(self, paragraphs, path=None):
        doc = self.editor.document()
        doc.setUndoRedoEnabled(False)  # loading isn't an undoable edit
        load_paragraphs(doc, paragraphs)
        doc.setUndoRedoEnabled(True)
        self.undo_stack.clear()
        self.path = Path(path) if path else None
        self.editor.moveCursor(self.editor.textCursor().MoveOperation.Start)
        self._sync_toolbar()
        self._update_count()
        self.editor.viewport().update()
        self.titleChanged.emit()

    def new_file(self):
        self.load([Paragraph("normal", [])])

    def open_file(self, path):
        self.load(open_docx(path), path)

    def save_file(self, path):
        save_docx(to_paragraphs(self.editor.document()), path)
        self.path = Path(path)
        self.undo_stack.set_clean()

    def export_pdf(self, path):
        from PySide6.QtGui import QPdfWriter

        writer = QPdfWriter(str(path))
        writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                         QPageLayout.Orientation.Portrait,
                                         QMarginsF(18, 18, 18, 18)))
        self.editor.document().print_(writer)


def _divider():
    d = QFrame()
    d.setObjectName("vdivider")
    d.setFixedSize(1, 22)
    return d
