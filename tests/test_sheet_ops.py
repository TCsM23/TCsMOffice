"""Sort, fill, find, insert/delete rows and columns, charts, formats and CSV."""
import openpyxl
import pytest

from office.sheets import ops
from office.sheets.engine import Sheet
from office.sheets.engine.restructure import restructure_formula
from office.sheets.formats import CellFormat, display
from office.sheets.xlsx_io import open_csv, open_xlsx_full, save_csv, save_xlsx


def grid():
    s = Sheet()
    s.set_many({"A1": "Name", "B1": "Qty", "C1": "Total",
                "A2": "pear", "B2": "3", "C2": "=B2*2",
                "A3": "fig", "B3": "10", "C3": "=B3*2",
                "A4": "apple", "B4": "1", "C4": "=B4*2",
                "A5": "", "B5": "", "C5": "=SUM(C2:C4)"})
    return s


def test_sort_moves_rows_and_their_formulas():
    s = grid()
    raws, fmts = ops.sort_rows(s, {(1, 0): CellFormat(bold=True)}, 1, 0, 3, 2, key_col=1)
    s.set_many(raws)
    assert [s.raw(f"A{r}") for r in (2, 3, 4)] == ["apple", "pear", "fig"]
    assert s.raw("C2") == "=B2*2" and s.value("C2") == 2  # the formula followed its row
    assert fmts[(2, 0)] == CellFormat(bold=True)           # pear's bold went with it
    assert s.value("C5") == 28


def test_sort_descending_text_and_blanks_last():
    s = Sheet()
    s.set_many({"A1": "b", "A2": "", "A3": "C", "A4": "a"})
    s.set("A2", "")
    raws, _ = ops.sort_rows(s, {}, 0, 0, 3, 0, 0, descending=True)
    s.set_many(raws)
    assert [s.raw(f"A{r}") for r in range(1, 5)] == ["C", "b", "a", ""]


def test_fill_down_and_right_shift_references():
    s = grid()
    s.set_many(ops.fill(s, 1, 2, 3, 2, "down"))  # C2 down to C4
    assert s.raw("C4") == "=B4*2"
    s.set("D2", "=C2+1")
    s.set_many(ops.fill(s, 1, 3, 1, 5, "right"))
    assert s.raw("F2") == "=E2+1"


@pytest.mark.parametrize("raw,axis,at,count,expected", [
    ("=A1+A5", "row", 2, 1, "=A1+A6"),              # insert above row 3
    ("=$A$5", "row", 0, 2, "=$A$7"),                # absolute refs move too
    ("=SUM(A1:A5)", "row", 2, 1, "=SUM(A1:A6)"),    # the range grows
    ("=SUM(A1:A5)", "row", 1, -2, "=SUM(A1:A3)"),   # delete rows 2-3: it shrinks
    ("=A3", "row", 2, -1, "=#REF!"),                # deleted cell
    ("=SUM(A2:A3)", "row", 1, -2, "=SUM(#REF!)"),   # whole range deleted
    ("=B1*C1", "col", 1, 1, "=C1*D1"),              # insert a column before B
    ("=D1", "col", 1, -1, "=C1"),
    ('="A5"&A5', "row", 0, 1, '="A5"&A6'),          # text in quotes is left alone
])
def test_restructure_formula(raw, axis, at, count, expected):
    assert restructure_formula(raw, axis, at, count) == expected


def test_insert_and_delete_rows_keep_totals_right():
    s = grid()
    raws, _ = ops.restructure(s, {}, "row", 2, 1)  # a blank row above "fig"
    s.set_many(raws)
    assert s.raw("A4") == "fig" and s.raw("A3") == ""
    assert s.raw("C6") == "=SUM(C2:C5)" and s.value("C6") == 28
    raws, _ = ops.restructure(s, {}, "row", 1, -1)  # delete "pear"
    s.set_many(raws)
    assert s.raw("A3") == "fig" and s.value("C5") == 22


def test_find_and_replace():
    s = grid()
    assert ops.find_cells(s, "AP") == [(3, 0)]
    assert ops.find_cells(s, "B2") == [(1, 2)]                 # found inside a formula
    assert ops.find_cells(s, "B2", in_formulas=False) == []
    assert ops.find_cells(s, "fig", whole_cell=True) == [(2, 0)]
    assert ops.replace_in_cells(s, "B", "C", [(1, 2)]) == {"C2": "=C2*2"}


def test_selection_stats_and_chart_series():
    s = grid()
    st = ops.selection_stats(s, [(1, 1), (2, 1), (3, 1), (0, 1)])
    assert st == {"count": 4, "numbers": 3, "sum": 14, "average": pytest.approx(14 / 3)}
    cats, series = ops.chart_series(s, 0, 0, 3, 2)
    assert cats == ["pear", "fig", "apple"]
    assert series == [("Qty", [3, 10, 1]), ("Total", [6, 20, 2])]


def test_formats_and_widths_round_trip_through_xlsx(tmp_path):
    s = grid()
    fmts = {(0, 0): CellFormat(bold=True, color="#F3E7D3", fill="#7A0E1B", align="center"),
            (1, 2): CellFormat(italic=True, underline=True, number='"€"#,##0.00')}
    path = tmp_path / "f.xlsx"
    save_xlsx(s, path, formats=fmts, col_widths={0: 180})
    ws = openpyxl.load_workbook(path).active
    assert ws["A1"].font.b and ws["A1"].fill.fgColor.rgb == "FF7A0E1B"
    assert ws["C2"].number_format == '"€"#,##0.00'
    sheet, back, widths = open_xlsx_full(path)
    assert back == fmts
    assert widths[0] == pytest.approx(180, abs=2)
    assert display(sheet.value("C2"), back[(1, 2)]) == "€6.00"


def test_csv_round_trip(tmp_path):
    s = grid()
    path = tmp_path / "g.csv"
    save_csv(s, path, {(1, 2): CellFormat(number="0.00")})
    text = path.read_text(encoding="utf-8").splitlines()
    assert text[0] == "Name,Qty,Total" and text[1] == "pear,3,6.00"
    back = open_csv(path)
    assert back.raw("A4") == "apple" and back.value("C5") == 28  # formulas become values
