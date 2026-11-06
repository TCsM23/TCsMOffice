"""Starter content so the app doesn't open blank."""
from . import theme
from .sheets.engine import Sheet
from .sheets.formats import CellFormat
from .writer.document import Paragraph, Run, Table

SUPPLIES = {
    "A1": "Item", "B1": "Qty", "C1": "Price", "D1": "Total",
    "A2": "Bond paper (ream)", "B2": "4", "C2": "120", "D2": "=B2*C2",
    "A3": "Printer ink", "B3": "2", "C3": "350", "D3": "=B3*C3",
    "A4": "Folders", "B4": "10", "C4": "15", "D4": "=B4*C4",
    "A5": "Ballpens", "B5": "12", "C5": "8", "D5": "=B5*C5",
    "A6": "Subtotal", "D6": "=SUM(D2:D5)",
    "A7": "Tax 12%", "D7": "=D6*0.12",
    "A8": "Grand total", "D8": "=D6+D7",
    "A10": "Loop test", "B10": "=C10+1", "C10": "=B10+1",
}


def supplies_formats() -> dict:
    """A crimson header row and currency-style totals, to show off formatting."""
    header = CellFormat(bold=True, color=theme.IVORY, fill=theme.CRIMSON)
    money = CellFormat(number="#,##0.00")
    out = {(0, c): header for c in range(4)}
    out.update({(r, c): money for r in range(1, 8) for c in (2, 3)})
    out[(7, 0)] = CellFormat(bold=True)
    out[(7, 3)] = CellFormat(bold=True, number="#,##0.00", fill=theme.DEPENDENT)
    return out


def supplies_sheet() -> Sheet:
    sheet = Sheet()
    sheet.set_many(SUPPLIES)
    return sheet


def _bold_header(table: Table) -> Table:
    for cell in table.rows[0]:
        for para in cell:
            for run in para.runs:
                run.bold = True
    return table


def welcome_document() -> list:
    return [
        Paragraph("h1", [Run("Welcome to Writer", bold=True)], align="center"),
        Paragraph("normal", [
            Run("This page saves to "), Run(".docx", bold=True),
            Run(" and opens in Word or LibreOffice, headings in Alegreya SC and body in "
                "EB Garamond. Try "), Run("bold", bold=True), Run(", "),
            Run("italic", italic=True), Run(" and "), Run("underline", underline=True),
            Run(", then undo them all."),
        ], align="justify"),
        Paragraph("h2", [Run("What works", bold=True)]),
        Paragraph("bullet", [Run("Body text and three heading levels")], 1),
        Paragraph("bullet", [Run("Bulleted and numbered lists")], 1),
        Paragraph("bullet", [Run("Left, centre, right and justified paragraphs")], 1),
        Paragraph("bullet", [Run("Undo and redo, a word count, and export to PDF")], 1),
        Paragraph("bullet", [Run("Fonts, sizes, "), Run("colour", color=theme.CRIMSON), Run(", "),
                             Run("highlight", highlight="#F3E2A9"), Run(" and "),
                             Run("strikethrough", strike=True)], 1),
        Paragraph("bullet", [Run("Tables, pictures, and find and replace (Ctrl+H)")], 1),
        Paragraph("h2", [Run("New in 1.1", bold=True)]),
        _bold_header(Table.from_text([["Module", "What's new"],
                         ["Sheets", "Formatting, sorting, charts, 80 more functions"],
                         ["Writer", "Fonts, colours, tables, pictures, find and replace"],
                         ["Slides", "Transitions, tables, shapes, PDF export"]])),
        Paragraph("h2", [Run("Build order", bold=True)]),
        Paragraph("number", [Run("Formula engine")], 2),
        Paragraph("number", [Run("Grid UI")], 2),
        Paragraph("number", [Run("Save and open .xlsx")], 2),
        Paragraph("number", [Run("Writer")], 2),
        Paragraph("number", [Run("Undo and redo across every module")], 2),
        Paragraph("number", [Run("Slides, with .pptx")], 2),
    ]
