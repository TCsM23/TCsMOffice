"""Save and open .xlsx with openpyxl, and plain .csv.

Formulas stay formulas (Excel recomputes them). Cell formatting (bold,
italic, underline, colours, alignment, number format) and column widths go
into the .xlsx too, so a workbook looks the same in Excel.
"""
import csv
import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .engine import Sheet, format_value
from .engine.numfmt import GENERAL
from .engine.refs import to_addr
from .formats import CellFormat, display

# Qt pixels per Excel character width, near enough for EB Garamond at 16px.
PX_PER_CHAR = 7.5


def _argb(hex_color):
    return "FF" + hex_color.lstrip("#").upper()


def _hex(color):
    """openpyxl Color -> '#RRGGBB', or None for theme/indexed colours."""
    try:
        if color is not None and color.type == "rgb" and isinstance(color.rgb, str):
            return "#" + color.rgb[-6:].upper()
    except AttributeError:
        pass
    return None


def save_xlsx(sheet: Sheet, path, title="Sheet1", formats=None, col_widths=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for (row, col), cell in sorted(sheet.cells.items()):
        raw = cell.raw
        if raw.startswith("="):
            value = raw  # openpyxl writes strings starting with '=' as formulas
        elif isinstance(cell.value, bool):
            value = cell.value
        elif isinstance(cell.value, float):
            value = int(cell.value) if cell.value.is_integer() else cell.value
        else:
            value = raw
        ws.cell(row=row + 1, column=col + 1, value=value)
    for (row, col), f in (formats or {}).items():
        if f is None:
            continue
        c = ws.cell(row=row + 1, column=col + 1)
        c.font = Font(bold=f.bold, italic=f.italic, underline="single" if f.underline else None,
                      color=_argb(f.color) if f.color else None)
        if f.fill:
            c.fill = PatternFill(fill_type="solid", fgColor=_argb(f.fill))
        if f.align:
            c.alignment = Alignment(horizontal=f.align)
        if f.number != GENERAL:
            c.number_format = f.number
    for col, px in (col_widths or {}).items():
        ws.column_dimensions[get_column_letter(col + 1)].width = round(px / PX_PER_CHAR, 1)
    wb.save(path)


def _raw_from_openpyxl(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return format_value(float(value))
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    return str(value)  # text, or a formula starting with '='


def _format_from_openpyxl(c) -> CellFormat | None:
    font, fill, align = c.font, c.fill, c.alignment
    f = CellFormat(
        bold=bool(font and font.b),
        italic=bool(font and font.i),
        underline=bool(font and font.u),
        color=_hex(font.color) if font else None,
        fill=_hex(fill.fgColor) if fill is not None and fill.fill_type == "solid" else None,
        align=align.horizontal if align is not None and align.horizontal in (
            "left", "center", "right") else None,
        number=c.number_format if c.number_format and c.number_format != GENERAL
        and not c.is_date else GENERAL,
    )
    return None if f.is_default else f


def open_xlsx_full(path):
    """Read the first worksheet: (Sheet, formats, column widths in pixels)."""
    wb = openpyxl.load_workbook(path)  # data_only=False keeps formulas
    ws = wb.worksheets[0]
    updates, formats = {}, {}
    for row in ws.iter_rows():
        for c in row:
            raw = _raw_from_openpyxl(c.value)
            if raw != "":
                updates[to_addr(c.row - 1, c.column - 1)] = raw
            if c.has_style:
                f = _format_from_openpyxl(c)
                if f is not None:
                    formats[(c.row - 1, c.column - 1)] = f
    widths = {}
    for letter, dim in ws.column_dimensions.items():
        if dim.width and dim.customWidth:
            widths[openpyxl.utils.column_index_from_string(letter) - 1] = round(
                dim.width * PX_PER_CHAR)
    sheet = Sheet()
    sheet.set_many(updates)
    return sheet, formats, widths


def open_xlsx(path) -> Sheet:
    """Read the first worksheet. Formulas we can't parse show as #ERROR!."""
    return open_xlsx_full(path)[0]


# ---- CSV -------------------------------------------------------------------

def save_csv(sheet: Sheet, path, formats=None):
    """Write the values as shown (formulas become their results), like Excel."""
    if not sheet.cells:
        open(path, "w", encoding="utf-8").close()
        return
    rows = max(r for r, _ in sheet.cells) + 1
    cols = max(c for _, c in sheet.cells) + 1
    formats = formats or {}
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for r in range(rows):
            line = []
            for c in range(cols):
                cell = sheet.cells.get((r, c))
                line.append(display(cell.value, formats.get((r, c))) if cell else "")
            w.writerow(line)


def open_csv(path) -> Sheet:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        updates = {}
        for r, line in enumerate(csv.reader(fh, dialect)):
            for c, value in enumerate(line):
                if value != "":
                    updates[to_addr(r, c)] = value
    sheet = Sheet()
    sheet.set_many(updates)
    return sheet
