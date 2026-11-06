"""A tiny document model shared by the editor and the .docx reader/writer.

Keeping this separate from Qt means the .docx code is plain Python and can be
tested without a window, the same split as the Sheets engine.
"""
from dataclasses import dataclass, field

STYLES = ("normal", "h1", "h2", "h3", "bullet", "number")
ALIGNMENTS = ("left", "center", "right", "justify")


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    font: str | None = None        # None: the paragraph style's font
    size: float | None = None      # points; None: the style's size
    color: str | None = None       # "#RRGGBB"; None: the style's colour
    highlight: str | None = None   # background colour behind the text


@dataclass
class Paragraph:
    style: str = "normal"
    runs: list = field(default_factory=list)
    # Adjacent list paragraphs with the same list_id form one list. A new
    # list_id restarts numbering at 1.
    list_id: int | None = None
    align: str = "left"

    @property
    def text(self):
        return "".join(r.text for r in self.runs)

    @property
    def heading_level(self):
        return int(self.style[1]) if self.style in ("h1", "h2", "h3") else 0


@dataclass
class Table:
    """A grid of cells; each cell holds its own paragraphs."""
    rows: list = field(default_factory=list)   # rows[r][c] -> list[Paragraph]

    @property
    def text(self):
        return "\n".join("\t".join("\n".join(p.text for p in cell) for cell in row)
                         for row in self.rows)

    @classmethod
    def from_text(cls, rows):
        """Table.from_text([["a", "b"], ["c", "d"]]) for tests and starter content."""
        return cls([[[Paragraph("normal", [Run(t)] if t else [])] for t in row] for row in rows])


@dataclass
class Image:
    """A picture in its own paragraph. Width and height are in points."""
    data: bytes
    width: float
    height: float
    align: str = "center"
    text = ""
    style = "image"
