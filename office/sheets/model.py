"""Qt model over the engine's Sheet. The view never talks to the engine directly."""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from .. import theme
from ..undo import MacroCommand, UndoStack
from .commands import SetCellsCommand, SetFormatsCommand
from . import formats as fmt
from .engine import CellError, Sheet
from .engine.refs import index_to_col, parse_ref, to_addr

MIN_ROWS = 100
MIN_COLS = 26


class SheetModel(QAbstractTableModel):
    # Emitted after every edit with the addresses that were recomputed.
    cellsChanged = Signal(list)

    def __init__(self, sheet: Sheet | None = None, parent=None):
        super().__init__(parent)
        self.sheet = sheet or Sheet()
        self._precedents: set = set()
        self._dependents: set = set()
        self._rows, self._cols = self._size_for(self.sheet)
        self.formats: dict = {}  # (row, col) -> CellFormat; missing means default
        self.undo_stack = UndoStack()

    @staticmethod
    def _size_for(sheet):
        rows, cols = MIN_ROWS, MIN_COLS
        for r, c in sheet.cells:
            rows = max(rows, r + 20)
            cols = max(cols, c + 4)
        return rows, cols

    def set_sheet(self, sheet: Sheet, formats=None):
        self.beginResetModel()
        self.sheet = sheet
        self.formats = dict(formats or {})
        self._precedents, self._dependents = set(), set()
        self._rows, self._cols = self._size_for(sheet)
        self.endResetModel()
        self.undo_stack.clear()

    # ---- QAbstractTableModel -----------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._cols

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = (index.row(), index.column())
        cell = self.sheet.cells.get(key)
        f = self.formats.get(key)
        if role == Qt.ItemDataRole.DisplayRole:
            return fmt.display(cell.value, f) if cell else None
        if role == Qt.ItemDataRole.EditRole:
            return cell.raw if cell else ""
        if role == Qt.ItemDataRole.TextAlignmentRole:
            value = cell.value if cell is not None else None
            if f is not None and f.align:
                h = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
                     "right": Qt.AlignmentFlag.AlignRight}[f.align]
            elif isinstance(value, bool):
                h = Qt.AlignmentFlag.AlignHCenter
            elif isinstance(value, (float, CellError)):
                h = Qt.AlignmentFlag.AlignRight
            else:
                h = Qt.AlignmentFlag.AlignLeft
            return int(h | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if cell is not None and isinstance(cell.value, CellError):
                return QBrush(QColor(theme.ERROR))
            if f is not None and f.color:
                return QBrush(QColor(f.color))
        if role == Qt.ItemDataRole.FontRole and f is not None and (
                f.bold or f.italic or f.underline):
            font = QFont(theme.BODY_FAMILY)
            font.setPixelSize(16)
            font.setBold(f.bold)
            font.setItalic(f.italic)
            font.setUnderline(f.underline)
            return font
        if role == Qt.ItemDataRole.BackgroundRole:
            if key in self._precedents:
                return QBrush(QColor(theme.PRECEDENT))
            if key in self._dependents:
                return QBrush(QColor(theme.DEPENDENT))
            if f is not None and f.fill:
                return QBrush(QColor(f.fill))
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        addr = to_addr(index.row(), index.column())
        self.edit({addr: str(value)}, f"Edit {addr}")
        return True

    def edit(self, updates: dict, text: str):
        """The one entry point for user edits: wraps them in an undoable command."""
        changes = {a: (self.sheet.raw(a), raw) for a, raw in updates.items()
                   if self.sheet.raw(a) != raw}
        if changes:
            self.undo_stack.push(SetCellsCommand(self, changes, text))

    def format_cells(self, keys, text, **changes):
        """Merge `changes` (bold=True, fill="#...", ...) into each cell's format, undoably."""
        diff = {}
        for k in keys:
            old = self.formats.get(k)
            new = (old or fmt.DEFAULT).with_(**changes)
            new = None if new.is_default else new
            if new != old:
                diff[k] = (old, new)
        if diff:
            self.undo_stack.push(SetFormatsCommand(self, diff, text))

    def edit_with_formats(self, raw_updates: dict, format_updates: dict, text: str):
        """One undo step that changes both raws and formats (sort, insert row...)."""
        raws = {a: (self.sheet.raw(a), raw) for a, raw in raw_updates.items()
                if self.sheet.raw(a) != raw}
        fmts = {k: (self.formats.get(k), f) for k, f in format_updates.items()
                if self.formats.get(k) != f}
        parts = []
        if raws:
            parts.append(SetCellsCommand(self, raws, text))
        if fmts:
            parts.append(SetFormatsCommand(self, fmts, text))
        if parts:
            self.undo_stack.push(parts[0] if len(parts) == 1 else MacroCommand(text, parts))

    def apply_formats(self, updates: dict):
        """Write formats straight to the store. Only commands call this."""
        for k, f in updates.items():
            if f is None or f.is_default:
                self.formats.pop(k, None)
            else:
                self.formats[k] = f
        self._grow_for([to_addr(*k) for k in updates])
        for r, c in updates:
            idx = self.index(r, c)
            self.dataChanged.emit(idx, idx)
        self.cellsChanged.emit([])

    def apply(self, updates: dict):
        """Write raws straight to the engine. Only commands call this."""
        changed = self.sheet.set_many(updates)
        self._grow_for(updates)
        # Repaint only what the engine recalculated, plus the edited cells.
        for a in set(changed) | set(updates):
            r, c = parse_ref(a)
            idx = self.index(r, c)
            self.dataChanged.emit(idx, idx)
        self.cellsChanged.emit(changed)
        return changed

    def _grow_for(self, addrs):
        keys = [parse_ref(a) for a in addrs]
        rows = max([self._rows] + [r + 20 for r, _ in keys])
        cols = max([self._cols] + [c + 4 for _, c in keys])
        if rows > self._rows:
            self.beginInsertRows(QModelIndex(), self._rows, rows - 1)
            self._rows = rows
            self.endInsertRows()
        if cols > self._cols:
            self.beginInsertColumns(QModelIndex(), self._cols, cols - 1)
            self._cols = cols
            self.endInsertColumns()

    def flags(self, index):
        return (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return index_to_col(section)
            return str(section + 1)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    # ---- highlighting for the dependency panel -----------------------------

    def set_highlight(self, precedents, dependents):
        old = self._precedents | self._dependents
        self._precedents = {parse_ref(a) for a in precedents}
        self._dependents = {parse_ref(a) for a in dependents}
        for r, c in old | self._precedents | self._dependents:
            if r < self._rows and c < self._cols:
                idx = self.index(r, c)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.BackgroundRole])
