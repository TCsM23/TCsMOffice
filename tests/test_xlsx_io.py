import openpyxl

from office.sheets.engine import Sheet
from office.sheets.xlsx_io import open_xlsx, save_xlsx


def test_round_trip_keeps_formulas(tmp_path):
    s = Sheet()
    s.set_many({"A1": "Item", "B1": "4", "C1": "2.5", "D1": "=B1*C1", "D2": "=SUM(D1:D1)"})
    path = tmp_path / "t.xlsx"
    save_xlsx(s, path)

    ws = openpyxl.load_workbook(path).active
    assert ws["D1"].value == "=B1*C1"
    assert ws["B1"].value == 4
    assert ws["A1"].value == "Item"

    s2 = open_xlsx(path)
    assert s2.raw("D1") == "=B1*C1"
    assert s2.value("D1") == 10
    assert s2.value("D2") == 10
    assert s2.value("A1") == "Item"


def test_opens_a_file_made_elsewhere(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = 3
    ws["A2"] = "=$A$1*2"
    ws["A3"] = "=VLOOKUP(1,B1:C2,2)"
    ws["A4"] = True
    ws["A5"] = "=WEBSERVICE(1)"
    path = tmp_path / "other.xlsx"
    wb.save(path)

    s = open_xlsx(path)
    assert s.value("A2") == 6
    assert s.display("A3") == "#N/A"  # VLOOKUP works now; B1:C2 is empty
    assert s.display("A5") == "#NAME?"  # functions we don't have
    assert s.value("A4") is True
