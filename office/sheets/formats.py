"""Cell formatting for Sheets: bold, italic, colours, alignment, number format.

Plain Python, kept beside the engine rather than inside it: formatting never
changes a value, only how the grid (and Excel) shows it.
"""
from dataclasses import dataclass, replace

from .engine.numfmt import GENERAL, format_number
from .engine.sheet import format_value


@dataclass(frozen=True)
class CellFormat:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None     # text colour "#RRGGBB"
    fill: str | None = None      # background colour
    align: str | None = None     # None (automatic) | left | center | right
    number: str = GENERAL        # an Excel number format code

    def with_(self, **changes) -> "CellFormat":
        return replace(self, **changes)

    @property
    def is_default(self) -> bool:
        return self == DEFAULT


DEFAULT = CellFormat()


def display(value, fmt: CellFormat | None) -> str:
    """The text a cell shows: its number format applied to numbers."""
    if fmt is not None and isinstance(value, float) and not isinstance(value, bool):
        text = format_number(value, fmt.number)
        if text is not None:
            return text
    return format_value(value)
