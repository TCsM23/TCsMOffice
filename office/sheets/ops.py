"""Whole-range operations for Sheets: sort, fill, find, insert/delete rows and
columns. Each returns the edits to make; the model wraps them in one undoable
command. Plain Python, tested directly in tests/test_sheet_ops.py.
"""
from .engine import CellError, Sheet
from .engine.refs import to_addr
from .engine.restructure import restructure_formula
from .engine.shift import shift_formula


def _sort_key(value):
    """Numbers first (ascending), then text (case-insensitive), then
    booleans, then errors; blanks always go last, as in Excel."""
    if value is None or value == "":
        return (4, 0)
    if isinstance(value, bool):
        return (2, value)
    if isinstance(value, float):
        return (0, value)
    if isinstance(value, CellError):
        return (3, value.code)
    return (1, str(value).lower())


def sort_rows(sheet: Sheet, formats: dict, top, left, bottom, right, key_col,
              descending=False):
    """Sort rows top..bottom by column key_col, moving cells left..right.

    Returns (raw_updates, format_updates). Formulas move with their row and
    their relative references follow, the way Excel's sort behaves.
    """
    rows = list(range(top, bottom + 1))
    blanks = [r for r in rows if _sort_key(sheet.value(to_addr(r, key_col)))[0] == 4]
    filled = [r for r in rows if r not in blanks]
    filled.sort(key=lambda r: _sort_key(sheet.value(to_addr(r, key_col))), reverse=descending)
    order = filled + blanks  # blanks stay at the bottom either way
    raws, fmts = {}, {}
    for dst, src in zip(rows, order):
        for c in range(left, right + 1):
            raws[to_addr(dst, c)] = shift_formula(sheet.raw(to_addr(src, c)), dst - src, 0)
            fmts[(dst, c)] = formats.get((src, c))
    return raws, fmts


def fill(sheet: Sheet, top, left, bottom, right, direction="down"):
    """Copy the first row (down) or first column (right) across the block,
    shifting relative references like a paste."""
    updates = {}
    for r in range(top, bottom + 1):
        for c in range(left, right + 1):
            src = (top, c) if direction == "down" else (r, left)
            if (r, c) == src:
                continue
            raw = sheet.raw(to_addr(*src))
            updates[to_addr(r, c)] = shift_formula(raw, r - src[0], c - src[1])
    return updates


def find_cells(sheet: Sheet, text: str, match_case=False, in_formulas=True,
               whole_cell=False):
    """Every (row, col) whose shown value (or formula) contains `text`, row by row."""
    if not text:
        return []
    needle = text if match_case else text.lower()
    hits = []
    for key in sorted(sheet.cells):
        addr = to_addr(*key)
        candidates = [sheet.display(addr)]
        if in_formulas:
            candidates.append(sheet.raw(addr))
        for hay in candidates:
            h = hay if match_case else hay.lower()
            if (h == needle) if whole_cell else (needle in h):
                hits.append(key)
                break
    return hits


def replace_in_cells(sheet: Sheet, text: str, new: str, keys=None, match_case=False):
    """Replace inside each cell's raw text (formulas included). Returns updates."""
    import re

    if not text:
        return {}
    rx = re.compile(re.escape(text), 0 if match_case else re.IGNORECASE)
    updates = {}
    for key in keys if keys is not None else sorted(sheet.cells):
        addr = to_addr(*key)
        raw = sheet.raw(addr)
        out = rx.sub(lambda _m: new, raw)
        if out != raw:
            updates[addr] = out
    return updates


def restructure(sheet: Sheet, formats: dict, axis: str, at: int, count: int):
    """Insert (count > 0) or delete (count < 0) rows or columns at `at`.

    Returns (raw_updates, format_updates) covering every cell that moves or
    whose formula changes, including cells that become empty.
    """
    def moved(key):
        r, c = key
        i = r if axis == "row" else c
        if i < at:
            return key
        if count < 0 and i < at - count:
            return None  # deleted
        i += count
        return (i, c) if axis == "row" else (r, i)

    new_raws = {}
    for key, cell in sheet.cells.items():
        dst = moved(key)
        if dst is not None:
            new_raws[dst] = restructure_formula(cell.raw, axis, at, count)
    raws = {to_addr(*k): "" for k in sheet.cells}
    raws.update({to_addr(*k): v for k, v in new_raws.items()})
    fmts = {k: None for k in formats}
    for key, f in formats.items():
        dst = moved(key)
        if dst is not None:
            fmts[dst] = f
    return raws, fmts


def selection_stats(sheet: Sheet, keys):
    """Sum, average and count of the numbers in the selected cells, for the status bar."""
    nums, count = [], 0
    for key in keys:
        cell = sheet.cells.get(key)
        if cell is None:
            continue
        count += 1
        if isinstance(cell.value, float) and not isinstance(cell.value, bool):
            nums.append(cell.value)
    return {"count": count, "numbers": len(nums), "sum": sum(nums),
            "average": sum(nums) / len(nums) if nums else None}


def chart_series(sheet: Sheet, top, left, bottom, right):
    """Read a block as chart data: (categories, [(series name, [values])]).

    If the first column holds text it becomes the category labels; if the
    first row holds text it names the series. Non-numbers count as 0.
    """
    def val(r, c):
        return sheet.value(to_addr(r, c))

    def is_num(v):
        return isinstance(v, float) and not isinstance(v, bool)

    label_rows = range(top + 1, bottom + 1) if bottom > top else [top]
    has_labels = right > left and any(isinstance(val(r, left), str) for r in label_rows)
    first_col = left + 1 if has_labels else left
    has_header = bottom > top and any(
        isinstance(val(top, c), str) for c in range(first_col, right + 1))
    first_row = top + 1 if has_header else top
    categories = [format_label(val(r, left)) if has_labels else str(r - first_row + 1)
                  for r in range(first_row, bottom + 1)]
    series = []
    for c in range(first_col, right + 1):
        name = format_label(val(top, c)) if has_header else to_addr(0, c)[:-1]
        values = [val(r, c) for r in range(first_row, bottom + 1)]
        series.append((name, [v if is_num(v) else 0.0 for v in values]))
    return categories, series


def format_label(v):
    from .engine import format_value
    return format_value(v)
