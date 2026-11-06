"""Spreadsheet errors are values, not Python exceptions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CellError:
    code: str

    def __str__(self):
        return self.code


DIV0 = CellError("#DIV/0!")
NAME = CellError("#NAME?")
VALUE = CellError("#VALUE!")
REF = CellError("#REF!")
NUM = CellError("#NUM!")
CIRC = CellError("#CIRC!")
SYNTAX = CellError("#ERROR!")  # the formula did not parse
NA = CellError("#N/A")  # a lookup found nothing
