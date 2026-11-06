"""The Sheets tab: formula bar, grid, and the dependency-graph side panel."""
from pathlib import Path

from PySide6.QtCore import QMarginsF, Qt, Signal
from PySide6.QtGui import (
    QColor, QGuiApplication, QIcon, QKeySequence, QPageLayout, QPageSize, QPalette, QPixmap,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QStyledItemDelegate, QTableView, QToolButton, QVBoxLayout, QWidget,
)

from .. import theme
from ..findbar import FindBar
from . import ops
from .chart import ChartDialog
from .engine import CellError, Sheet
from .engine.numfmt import GENERAL, PRESETS
from .engine.refs import index_to_col, parse_ref, to_addr
from .engine.shift import shift_formula
from .formats import display as format_display
from .model import SheetModel
from .xlsx_io import open_csv, open_xlsx_full, save_csv, save_xlsx

SWATCHES = [("Crimson", theme.CRIMSON), ("Oxblood", theme.OXBLOOD), ("Gilt", theme.GILT),
            ("Pale gold", theme.GILT_LIGHT), ("Rose", theme.PRECEDENT), ("Vellum", theme.VELLUM),
            ("Ink", theme.INK), ("Ivory", theme.IVORY), ("White", "#FFFFFF")]

MAX_CHIPS = 24


class SheetTable(QTableView):
    """A QTableView with spreadsheet keys: Delete clears, Enter moves down,
    and Ctrl+C / Ctrl+X / Ctrl+V go through the panel's clipboard."""

    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    def keyPressEvent(self, event):
        if self.state() != QAbstractItemView.State.EditingState:
            if event.matches(QKeySequence.StandardKey.Copy):
                return self.panel.copy()
            if event.matches(QKeySequence.StandardKey.Cut):
                return self.panel.cut()
            if event.matches(QKeySequence.StandardKey.Paste):
                return self.panel.paste()
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                return self.panel.clear_selection()
            ctrl = event.modifiers() == Qt.KeyboardModifier.ControlModifier
            if ctrl and event.key() == Qt.Key.Key_D:
                return self.panel.fill("down")
            if ctrl and event.key() == Qt.Key.Key_R:
                return self.panel.fill("right")
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                cur = self.currentIndex()
                self.setCurrentIndex(cur.siblingAtRow(min(cur.row() + 1, self.model().rowCount() - 1)))
                return
        super().keyPressEvent(event)


class CellDelegate(QStyledItemDelegate):
    """Keep a cell's own text colour (red for errors) when it is selected."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        color = brush.color() if brush is not None else QColor(theme.TEXT)
        if color.lightnessF() > 0.7:
            # Light text (ivory on a crimson fill) would vanish on the pale
            # selection colour, so selected cells show it in ink instead.
            color = QColor(theme.TEXT)
        option.palette.setColor(QPalette.ColorRole.HighlightedText, color)


def _chips(addrs, color):
    if not addrs:
        return None
    shown = addrs[:MAX_CHIPS]
    parts = [
        f'<span style="background:{color}; font-family:monospace;">&nbsp;{a}&nbsp;</span>'
        for a in shown
    ]
    more = f" <span style='color:{theme.MUTED}'>and {len(addrs) - len(shown)} more</span>" \
        if len(addrs) > len(shown) else ""
    return "&nbsp; ".join(parts) + more


class DependencyPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("depPanel")
        self.setFixedWidth(270)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(6)

        eyebrow = QLabel("DEPENDENCY GRAPH")
        eyebrow.setObjectName("eyebrow")
        self.title = QLabel()
        self.title.setObjectName("cellTitle")
        self.raw = QLabel()
        self.raw.setObjectName("mono")
        self.raw.setWordWrap(True)
        self.raw.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        def section(text):
            label = QLabel(text)
            label.setObjectName("sectionTitle")
            return label

        self.depends = QLabel()
        self.depends.setWordWrap(True)
        self.used_by = QLabel()
        self.used_by.setWordWrap(True)

        self.plan_box = QFrame()
        self.plan_box.setObjectName("planBox")
        plan_lay = QVBoxLayout(self.plan_box)
        plan_lay.setContentsMargins(12, 10, 12, 10)
        self.plan_title = QLabel()
        self.plan_title.setObjectName("sectionTitle")
        self.plan_title.setWordWrap(True)
        self.plan = QLabel()
        self.plan.setObjectName("mono")
        self.plan.setWordWrap(True)
        plan_lay.addWidget(self.plan_title)
        plan_lay.addWidget(self.plan)

        self.cycle_note = QLabel()
        self.cycle_note.setWordWrap(True)
        self.cycle_note.setStyleSheet(f"color: {theme.ERROR};")

        legend = QLabel(
            f'<span style="background:{theme.PRECEDENT}">&nbsp;&nbsp;&nbsp;</span> Precedent'
            f'&nbsp;&nbsp;&nbsp;<span style="background:{theme.DEPENDENT}">&nbsp;&nbsp;&nbsp;</span> Dependent'
        )
        legend.setObjectName("muted")

        lay.addWidget(eyebrow)
        lay.addSpacing(4)
        lay.addWidget(self.title)
        lay.addWidget(self.raw)
        lay.addSpacing(12)
        lay.addWidget(section("Depends on"))
        lay.addWidget(self.depends)
        lay.addSpacing(10)
        lay.addWidget(section("Used by"))
        lay.addWidget(self.used_by)
        lay.addSpacing(10)
        lay.addWidget(self.cycle_note)
        lay.addWidget(self.plan_box)
        lay.addSpacing(10)
        lay.addWidget(legend)
        lay.addStretch(1)

    def show_cell(self, sheet: Sheet, addr: str):
        self.title.setText(f"Cell {addr}")
        raw = sheet.raw(addr)
        self.raw.setText(raw if raw else "(empty)")
        precedents = sheet.precedents(addr)
        dependents = sheet.dependents(addr)
        self.depends.setText(_chips(precedents, theme.PRECEDENT) or
                             f"<span style='color:{theme.MUTED}'>Reads no other cells</span>")
        self.used_by.setText(_chips(dependents, theme.DEPENDENT) or
                             f"<span style='color:{theme.MUTED}'>No cells read this one</span>")
        cycle = next((c for c in sheet.cycles() if addr in c), None)
        if cycle:
            self.cycle_note.setText(
                "On a circular reference: " + " → ".join(cycle + [cycle[0]])
                if len(cycle) > 1 else "This cell refers to itself.")
            self.cycle_note.show()
        else:
            self.cycle_note.hide()
        self.plan_title.setText(f"If {addr} changes, recalc in topological order")
        plan = sheet.recalc_plan(addr)
        self.plan.setText(" → ".join(plan) if plan else "Nothing to recalc")
        return precedents, dependents


class SheetsPanel(QWidget):
    titleChanged = Signal()
    chartToSlides = Signal(bytes)  # PNG of a chart, for the main window to insert in Slides

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.model = SheetModel()
        self.undo_stack = self.model.undo_stack
        # What we last copied, so a paste inside the app keeps formulas.
        self._clip = None  # (clipboard_text, top, left, {(dr, dc): raw}, was_cut)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_toolbar())
        self.find_bar = FindBar(self, whole_word_label="Whole cell")
        lay.addWidget(self.find_bar)

        # Formula bar
        bar = QFrame()
        bar.setObjectName("formulaBar")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 8, 12, 8)
        self.name_box = QLineEdit()
        self.name_box.setFixedWidth(64)
        self.name_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fx = QLabel("fx")
        fx.setObjectName("fx")
        self.formula = QLineEdit()
        self.formula.setPlaceholderText("Type a value or a formula like =SUM(A1:A5)")
        bar_lay.addWidget(self.name_box)
        bar_lay.addWidget(fx)
        bar_lay.addWidget(self.formula, 1)
        lay.addWidget(bar)

        # Grid + side panel
        middle = QHBoxLayout()
        middle.setSpacing(0)
        self.table = SheetTable(self)
        self.table.setModel(self.model)
        self.table.setItemDelegate(CellDelegate(self.table))
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.horizontalHeader().setDefaultSectionSize(106)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setFixedWidth(40)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        for header in (self.table.horizontalHeader(), self.table.verticalHeader()):
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(
            lambda pos: self._header_menu("col", self.table.horizontalHeader(), pos))
        self.table.verticalHeader().customContextMenuRequested.connect(
            lambda pos: self._header_menu("row", self.table.verticalHeader(), pos))
        self.panel = DependencyPanel()
        middle.addWidget(self.table, 1)
        middle.addWidget(self.panel)
        lay.addLayout(middle, 1)

        # Status line
        status = QFrame()
        status.setObjectName("statusBar")
        st_lay = QHBoxLayout(status)
        st_lay.setContentsMargins(12, 5, 12, 5)
        hint = QLabel("Click any cell to see its edges in the dependency graph")
        hint.setObjectName("muted")
        self.stats = QLabel()
        self.stats.setObjectName("muted")
        st_lay.addWidget(hint)
        st_lay.addStretch(1)
        st_lay.addWidget(self.stats)
        lay.addWidget(status)

        self.table.selectionModel().currentChanged.connect(self._on_current_changed)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._refresh_stats())
        self.model.cellsChanged.connect(self._on_cells_changed)
        self.formula.returnPressed.connect(self._commit_formula)
        self.undo_stack.subscribe(self.titleChanged.emit)
        self.name_box.returnPressed.connect(self._jump)

        self.table.setCurrentIndex(self.model.index(0, 0))
        self._refresh_stats()

    # ---- toolbar ------------------------------------------------------------

    def _build_toolbar(self):
        frame = QFrame()
        frame.setObjectName("toolbar")
        bar = QHBoxLayout(frame)
        bar.setContentsMargins(12, 5, 12, 5)
        bar.setSpacing(3)

        def tool(text, tip, slot=None, checkable=False, shortcut=None):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(checkable)
            b.setToolTip(tip + (f" ({shortcut})" if shortcut else ""))
            if slot is not None:
                b.clicked.connect(slot)
            bar.addWidget(b)
            return b

        def divider():
            d = QFrame()
            d.setObjectName("vdivider")
            d.setFixedSize(1, 22)
            bar.addWidget(d)

        self.bold_btn = tool("B", "Bold", lambda on: self.format_selection("Bold", bold=on),
                             True, "Ctrl+B")
        self.italic_btn = tool("I", "Italic", lambda on: self.format_selection("Italic", italic=on),
                               True, "Ctrl+I")
        self.underline_btn = tool("U", "Underline",
                                  lambda on: self.format_selection("Underline", underline=on),
                                  True, "Ctrl+U")
        for b, attr in ((self.bold_btn, "setBold"), (self.italic_btn, "setItalic"),
                        (self.underline_btn, "setUnderline")):
            f = b.font()
            getattr(f, attr)(True)
            b.setFont(f)
        divider()
        self.align_btns = {}
        for key, glyph in (("left", "≡ L"), ("center", "≡ C"), ("right", "≡ R")):
            self.align_btns[key] = tool(
                glyph, f"Align {key}",
                lambda on, k=key: self.format_selection("Alignment", align=k if on else None),
                True)
        divider()
        for label, tip, attr in (("A Text", "Text colour", "color"), ("▧ Fill", "Cell fill", "fill")):
            b = tool(label, tip)
            b.setMenu(self._color_menu(
                lambda c, a=attr, t=tip: self.format_selection(t, **{a: c})))
            b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.number_box = QComboBox()
        for label, code in PRESETS:
            self.number_box.addItem(label, code)
        self.number_box.setToolTip("Number format")
        self.number_box.setMinimumWidth(170)
        self.number_box.activated.connect(
            lambda i: self.format_selection("Number format", number=self.number_box.itemData(i)))
        bar.addWidget(self.number_box)
        divider()
        tool("A→Z", "Sort ascending by this column", lambda: self.sort(False))
        tool("Z→A", "Sort descending by this column", lambda: self.sort(True))
        tool("⇩ Fill down", "Fill down from the top row of the selection", lambda: self.fill("down"),
             shortcut="Ctrl+D")
        rows = tool("Rows/Cols ▾", "Insert or delete rows and columns")
        menu = QMenu(rows)
        menu.addAction("Insert row above", lambda: self.insert("row", before=True))
        menu.addAction("Insert row below", lambda: self.insert("row", before=False))
        menu.addAction("Insert column left", lambda: self.insert("col", before=True))
        menu.addAction("Insert column right", lambda: self.insert("col", before=False))
        menu.addSeparator()
        menu.addAction("Delete selected rows", lambda: self.delete("row"))
        menu.addAction("Delete selected columns", lambda: self.delete("col"))
        rows.setMenu(menu)
        rows.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        divider()
        tool("▥ Chart", "Chart the selected cells", self.show_chart)
        tool("⌕ Find", "Find and replace", lambda: self.open_find(False), shortcut="Ctrl+F")
        bar.addStretch(1)
        self.graph_btn = tool("Graph panel", "Show or hide the dependency graph panel",
                              lambda on: self.panel.setVisible(on), True)
        self.graph_btn.setChecked(True)
        self.bold_btn.setShortcut(QKeySequence("Ctrl+B"))
        self.italic_btn.setShortcut(QKeySequence("Ctrl+I"))
        self.underline_btn.setShortcut(QKeySequence("Ctrl+U"))
        return frame

    def _color_menu(self, slot):
        menu = QMenu(self)
        for name, hexv in SWATCHES:
            pm = QPixmap(14, 14)
            pm.fill(QColor(hexv))
            menu.addAction(QIcon(pm), name, lambda h=hexv: slot(h))
        menu.addAction("None", lambda: slot(None))
        menu.addSeparator()

        def custom():
            c = QColorDialog.getColor(QColor(theme.CRIMSON), self, "Choose a colour")
            if c.isValid():
                slot(c.name().upper())
        menu.addAction("Custom…", custom)
        return menu

    def _sync_toolbar(self):
        idx = self.table.currentIndex()
        f = self.model.formats.get((idx.row(), idx.column())) if idx.isValid() else None
        self.bold_btn.setChecked(bool(f and f.bold))
        self.italic_btn.setChecked(bool(f and f.italic))
        self.underline_btn.setChecked(bool(f and f.underline))
        for k, b in self.align_btns.items():
            b.setChecked(bool(f and f.align == k))
        i = self.number_box.findData(f.number if f else GENERAL)
        self.number_box.setCurrentIndex(max(0, i))

    # ---- file I/O -----------------------------------------------------------

    @property
    def modified(self):
        return not self.undo_stack.is_clean()

    def display_name(self):
        name = self.path.name if self.path else "Untitled.xlsx"
        return name + (" • edited" if self.modified else "")

    def load_sheet(self, sheet: Sheet, path=None, formats=None, widths=None):
        self.model.set_sheet(sheet, formats)
        self.path = Path(path) if path else None
        default = self.table.horizontalHeader().defaultSectionSize()
        for c in range(self.model.columnCount()):
            self.table.setColumnWidth(c, (widths or {}).get(c, 150 if c == 0 and not widths
                                                             else default))
        self.table.setCurrentIndex(self.model.index(0, 0))
        self._on_current_changed(self.table.currentIndex())
        self._refresh_stats()
        self.titleChanged.emit()

    def new_file(self):
        self.load_sheet(Sheet())

    def open_file(self, path):
        if str(path).lower().endswith(".csv"):
            self.load_sheet(open_csv(path), path)
        else:
            sheet, formats, widths = open_xlsx_full(path)
            self.load_sheet(sheet, path, formats, widths)

    def _column_widths(self):
        default = self.table.horizontalHeader().defaultSectionSize()
        used = {c for _r, c in self.model.sheet.cells} | {c for _r, c in self.model.formats}
        return {c: self.table.columnWidth(c) for c in used
                if self.table.columnWidth(c) != default}

    def save_file(self, path):
        if str(path).lower().endswith(".csv"):
            save_csv(self.model.sheet, path, self.model.formats)
        else:
            save_xlsx(self.model.sheet, path, formats=self.model.formats,
                      col_widths=self._column_widths())
        self.path = Path(path)
        self.undo_stack.set_clean()
        self.titleChanged.emit()

    def to_html(self):
        """The used range as an HTML table, formats included. Feeds Export PDF."""
        import html as _html

        sheet, formats = self.model.sheet, self.model.formats
        keys = set(sheet.cells) | set(formats)
        if not keys:
            return "<p>(empty sheet)</p>"
        rows = max(r for r, _ in keys) + 1
        cols = max(c for _, c in keys) + 1
        out = [f"<table cellspacing='0' cellpadding='4' style='border-collapse:collapse;"
               f"font-family:\"{theme.BODY_FAMILY}\"; font-size:10pt;'>",
               "<tr><th style='background:#EFE4D0'></th>"]
        out += [f"<th style='background:{theme.VELLUM}; color:{theme.CRIMSON};"
                f" border:1px solid {theme.GRID}'>{index_to_col(c)}</th>" for c in range(cols)]
        out.append("</tr>")
        for r in range(rows):
            out.append(f"<tr><th style='background:{theme.VELLUM}; color:{theme.CRIMSON};"
                       f" border:1px solid {theme.GRID}'>{r + 1}</th>")
            for c in range(cols):
                cell = sheet.cells.get((r, c))
                f = formats.get((r, c))
                text = format_display(cell.value, f) if cell else ""
                style = [f"border:1px solid {theme.GRID}"]
                align = (f.align if f and f.align else
                         "right" if cell and isinstance(cell.value, float) else "left")
                style.append(f"text-align:{align}")
                if f:
                    if f.bold:
                        style.append("font-weight:bold")
                    if f.italic:
                        style.append("font-style:italic")
                    if f.underline:
                        style.append("text-decoration:underline")
                    if f.color:
                        style.append(f"color:{f.color}")
                    if f.fill:
                        style.append(f"background:{f.fill}")
                if cell and isinstance(cell.value, CellError):
                    style.append(f"color:{theme.ERROR}")
                out.append(f"<td style='{'; '.join(style)}'>{_html.escape(text)}</td>")
            out.append("</tr>")
        out.append("</table>")
        title = _html.escape(self.path.name if self.path else "Untitled")
        return (f"<h2 style='font-family:\"{theme.TITLE_FAMILY}\"; color:{theme.CRIMSON}'>"
                f"{title}</h2>" + "".join(out))

    def export_pdf(self, path):
        from PySide6.QtGui import QPdfWriter

        writer = QPdfWriter(str(path))
        writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                         QPageLayout.Orientation.Landscape,
                                         QMarginsF(12, 12, 12, 12)))
        doc = QTextDocument()
        doc.setHtml(self.to_html())
        doc.print_(writer)

    # ---- interaction --------------------------------------------------------

    def current_addr(self):
        idx = self.table.currentIndex()
        return to_addr(idx.row(), idx.column()) if idx.isValid() else "A1"

    def _on_current_changed(self, index, _previous=None):
        if not index.isValid():
            return
        addr = to_addr(index.row(), index.column())
        self.name_box.setText(addr)
        self.formula.setText(self.model.sheet.raw(addr))
        precedents, dependents = self.panel.show_cell(self.model.sheet, addr)
        self.model.set_highlight(precedents, dependents)
        self._sync_toolbar()

    def _on_cells_changed(self, _changed):
        self._on_current_changed(self.table.currentIndex())
        self._refresh_stats()
        self.titleChanged.emit()

    def _commit_formula(self):
        self.model.setData(self.table.currentIndex(), self.formula.text())
        self.table.setFocus()

    def _jump(self):
        try:
            r, c = parse_ref(self.name_box.text())
        except ValueError:
            self.name_box.setText(self.current_addr())
            return
        if r < self.model.rowCount() and c < self.model.columnCount():
            self.table.setCurrentIndex(self.model.index(r, c))
            self.table.setFocus()

    def _refresh_stats(self):
        sheet = self.model.sheet
        n_cycles = len(sheet.cycles())
        n_errors = sum(1 for c in sheet.cells.values() if isinstance(c.value, CellError))
        parts = [f"Sheet1 · {len(sheet.cells)} cells"]
        if n_cycles:
            parts.append(f"{n_cycles} cycle" + ("s" if n_cycles != 1 else ""))
        if n_errors:
            parts.append(f"{n_errors} error" + ("s" if n_errors != 1 else ""))
        keys = self.selected_keys()
        if len(keys) > 1:
            st = ops.selection_stats(sheet, keys)
            if st["numbers"]:
                parts.append(f"Sum {format_display(float(st['sum']), None)}")
                parts.append(f"Average {format_display(round(st['average'], 6), None)}")
            parts.append(f"Count {st['count']}")
        self.stats.setText(" · ".join(parts))

    def selected_keys(self):
        try:
            idxs = self.table.selectedIndexes()
        except RuntimeError:
            return []
        return [(i.row(), i.column()) for i in idxs]

    # ---- formatting, sort, fill, structure ---------------------------------

    def format_selection(self, text, **changes):
        keys = self.selected_keys() or [(self.table.currentIndex().row(),
                                         self.table.currentIndex().column())]
        self.model.format_cells(keys, text, **changes)
        self._sync_toolbar()
        self.table.setFocus()

    def _current_region(self):
        """The block of filled cells around the current one, like Excel's Ctrl+A."""
        cells = self.model.sheet.cells
        idx = self.table.currentIndex()
        start = (idx.row(), idx.column())
        if start not in cells:
            return None
        seen, todo = {start}, [start]
        while todo and len(seen) < 100_000:
            r, c = todo.pop()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    k = (r + dr, c + dc)
                    if k not in seen and k in cells:
                        seen.add(k)
                        todo.append(k)
        rows = [r for r, _ in seen]
        cols = [c for _, c in seen]
        return min(rows), min(cols), max(rows), max(cols)

    def sort(self, descending=False, block=None, key_col=None, header=None):
        if block is None:
            top, left, bottom, right = self._selected_block()
            if top == bottom and left == right:
                region = self._current_region()
                if region is None:
                    return
                top, left, bottom, right = region
        else:
            top, left, bottom, right = block
        if key_col is None:
            key_col = self.table.currentIndex().column()
            if not left <= key_col <= right:
                key_col = left
        sheet = self.model.sheet
        if header is None:
            first = [sheet.value(to_addr(top, c)) for c in range(left, right + 1)]
            below = [sheet.value(to_addr(r, c)) for r in range(top + 1, bottom + 1)
                     for c in range(left, right + 1)]
            header = (bottom > top and all(isinstance(v, str) for v in first if v is not None)
                      and any(isinstance(v, float) for v in below))
        if header:
            top += 1
        if top >= bottom:
            return
        raws, fmts = ops.sort_rows(sheet, self.model.formats, top, left, bottom, right,
                                   key_col, descending)
        self.model.edit_with_formats(raws, fmts, "Sort " + ("Z→A" if descending else "A→Z"))

    def fill(self, direction="down"):
        top, left, bottom, right = self._selected_block()
        if (direction == "down" and bottom == top) or (direction == "right" and right == left):
            return
        updates = ops.fill(self.model.sheet, top, left, bottom, right, direction)
        fmts = {}
        for r in range(top, bottom + 1):
            for c in range(left, right + 1):
                src = (top, c) if direction == "down" else (r, left)
                fmts[(r, c)] = self.model.formats.get(src)
        self.model.edit_with_formats(updates, fmts,
                                     "Fill down" if direction == "down" else "Fill right")

    def insert(self, axis, before=True, at=None, count=1):
        idx = self.table.currentIndex()
        if at is None:
            top, left, bottom, right = self._selected_block()
            if axis == "row":
                at, count = (top, bottom - top + 1) if before else (bottom + 1, bottom - top + 1)
            else:
                at, count = (left, right - left + 1) if before else (right + 1, right - left + 1)
        raws, fmts = ops.restructure(self.model.sheet, self.model.formats, axis, at, count)
        label = f"Insert {'row' if axis == 'row' else 'column'}{'s' if count > 1 else ''}"
        self.model.edit_with_formats(raws, fmts, label)
        self.table.setCurrentIndex(idx)

    def delete(self, axis, at=None, count=None):
        if at is None:
            top, left, bottom, right = self._selected_block()
            at, count = (top, bottom - top + 1) if axis == "row" else (left, right - left + 1)
        raws, fmts = ops.restructure(self.model.sheet, self.model.formats, axis, at, -count)
        label = f"Delete {'row' if axis == 'row' else 'column'}{'s' if count > 1 else ''}"
        self.model.edit_with_formats(raws, fmts, label)

    # ---- context menus ------------------------------------------------------

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Cut", self.cut)
        menu.addAction("Copy", self.copy)
        menu.addAction("Paste", self.paste)
        menu.addAction("Clear", self.clear_selection)
        menu.addSeparator()
        menu.addAction("Insert row above", lambda: self.insert("row", True))
        menu.addAction("Insert column left", lambda: self.insert("col", True))
        menu.addAction("Delete rows", lambda: self.delete("row"))
        menu.addAction("Delete columns", lambda: self.delete("col"))
        menu.addSeparator()
        menu.addAction("Sort A→Z", lambda: self.sort(False))
        menu.addAction("Sort Z→A", lambda: self.sort(True))
        menu.addAction("Fill down", lambda: self.fill("down"))
        menu.addAction("Chart…", self.show_chart)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _header_menu(self, axis, header, pos):
        i = header.logicalIndexAt(pos)
        if i < 0:
            return
        word = "row" if axis == "row" else "column"
        menu = QMenu(self)
        menu.addAction(f"Insert {word} {'above' if axis == 'row' else 'left'}",
                       lambda: self.insert(axis, at=i, count=1))
        menu.addAction(f"Insert {word} {'below' if axis == 'row' else 'right'}",
                       lambda: self.insert(axis, at=i + 1, count=1))
        menu.addAction(f"Delete {word}", lambda: self.delete(axis, at=i, count=1))
        menu.exec(header.mapToGlobal(pos))

    # ---- charts -------------------------------------------------------------

    def chart_data(self):
        top, left, bottom, right = self._selected_block()
        if top == bottom and left == right:
            region = self._current_region()
            if region:
                top, left, bottom, right = region
        return ops.chart_series(self.model.sheet, top, left, bottom, right)

    def show_chart(self):
        cats, series = self.chart_data()
        self.chart_dialog = ChartDialog(cats, series, "Chart", self)
        self.chart_dialog.sendToSlides.connect(self.chartToSlides.emit)
        self.chart_dialog.show()
        return self.chart_dialog

    # ---- find and replace ---------------------------------------------------

    def open_find(self, replace=False):
        self.find_bar.open_bar(replace)

    def find(self, text, forward=True, match_case=False, whole=False):
        hits = ops.find_cells(self.model.sheet, text, match_case, True, whole)
        if not hits:
            return False
        idx = self.table.currentIndex()
        cur = (idx.row(), idx.column())
        if forward:
            nxt = next((h for h in hits if h > cur), hits[0])
        else:
            nxt = next((h for h in reversed(hits) if h < cur), hits[-1])
        self.table.setCurrentIndex(self.model.index(*nxt))
        return True

    def replace(self, text, new, match_case=False, whole=False):
        idx = self.table.currentIndex()
        key = (idx.row(), idx.column())
        if key not in ops.find_cells(self.model.sheet, text, match_case, True, whole):
            return False
        updates = (({to_addr(*key): new} if whole else
                    ops.replace_in_cells(self.model.sheet, text, new, [key], match_case)))
        self.model.edit(updates, "Replace")
        return bool(updates)

    def replace_all(self, text, new, match_case=False, whole=False):
        keys = ops.find_cells(self.model.sheet, text, match_case, True, whole)
        if whole:
            updates = {to_addr(*k): new for k in keys}
        else:
            updates = ops.replace_in_cells(self.model.sheet, text, new, keys, match_case)
        self.model.edit(updates, "Replace all")
        return len(updates)

    def find_closed(self):
        self.table.setFocus()

    # ---- clipboard ----------------------------------------------------------

    def _selected_block(self):
        idxs = self.table.selectedIndexes() or [self.table.currentIndex()]
        rows = [i.row() for i in idxs]
        cols = [i.column() for i in idxs]
        return min(rows), min(cols), max(rows), max(cols)

    def copy(self, cut=False):
        top, left, bottom, right = self._selected_block()
        sheet = self.model.sheet
        raws, fmts, lines = {}, {}, []
        for r in range(top, bottom + 1):
            line = []
            for c in range(left, right + 1):
                addr = to_addr(r, c)
                if sheet.raw(addr):
                    raws[(r - top, c - left)] = sheet.raw(addr)
                if (r, c) in self.model.formats:
                    fmts[(r - top, c - left)] = self.model.formats[(r, c)]
                line.append(format_display(sheet.value(addr), self.model.formats.get((r, c)))
                            if sheet.raw(addr) else "")
            lines.append("\t".join(line))
        # Other apps get the values as tab-separated text, like Excel does.
        text = "\n".join(lines)
        QGuiApplication.clipboard().setText(text)
        self._clip = (text, top, left, raws, cut, fmts, bottom - top + 1, right - left + 1)

    def cut(self):
        self.copy(cut=True)
        top, left, bottom, right = self._selected_block()
        self.model.edit_with_formats(
            {to_addr(r, c): "" for r in range(top, bottom + 1) for c in range(left, right + 1)},
            {(r, c): None for r in range(top, bottom + 1) for c in range(left, right + 1)},
            "Cut")

    def paste(self):
        text = QGuiApplication.clipboard().text()
        cur = self.table.currentIndex()
        top, left = cur.row(), cur.column()
        updates, fmts = {}, {}
        if self._clip and self._clip[0] == text:
            _text, src_top, src_left, raws, was_cut, clip_fmts, height, width = self._clip
            drow, dcol = top - src_top, left - src_left
            for dr in range(height):
                for dc in range(width):
                    raw = raws.get((dr, dc), "")
                    # Cut moves a formula unchanged; copy shifts its relative refs.
                    updates[to_addr(top + dr, left + dc)] = (
                        raw if was_cut else shift_formula(raw, drow, dcol))
                    fmts[(top + dr, left + dc)] = clip_fmts.get((dr, dc))
        else:
            for dr, line in enumerate(text.rstrip("\n").split("\n")):
                for dc, value in enumerate(line.rstrip("\r").split("\t")):
                    updates[to_addr(top + dr, left + dc)] = value
        if updates:
            self.model.edit_with_formats(updates, fmts, "Paste")

    def clear_selection(self):
        top, left, bottom, right = self._selected_block()
        self.model.edit({to_addr(r, c): "" for r in range(top, bottom + 1)
                         for c in range(left, right + 1)}, "Clear")
