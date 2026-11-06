"""The presentation model: slides holding positioned shapes. No Qt here.

Coordinates are in points on a 960 x 540 slide (16:9, the same 13.33 x 7.5
inch page PowerPoint uses), so a 24 pt font is 24 units tall.
"""
import copy
import itertools
from dataclasses import dataclass, field

SLIDE_W = 960.0
SLIDE_H = 540.0

# Drawn shapes beyond rectangles and ellipses (see render.shape_path).
SHAPES = ("rounded", "triangle", "diamond", "star", "arrow", "hexagon")
# Slide-show transitions, also written to .pptx so PowerPoint plays them.
TRANSITIONS = ("none", "fade", "push", "wipe", "cover", "zoom")

_ids = itertools.count(1)


def new_id() -> int:
    return next(_ids)


@dataclass
class TextStyle:
    font: str = "EB Garamond"
    size: float = 22.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "#2B1A17"
    align: str = "left"     # left | center | right
    valign: str = "top"     # top | middle | bottom


@dataclass
class Shape:
    kind: str                       # text | rect | ellipse | image | table, or a shape in SHAPES
    x: float
    y: float
    w: float
    h: float
    text: str = ""                  # paragraphs separated by "\n"
    bullets: bool = False
    style: TextStyle = field(default_factory=TextStyle)
    fill: str | None = None         # "#RRGGBB" or None for no fill
    line: str | None = None         # outline colour or None
    line_width: float = 1.0
    image: bytes | None = None
    role: str = ""                  # "title", "body", "" (used by layouts and outline)
    id: int = field(default_factory=new_id)

    # Tables keep their cells in `text`: rows on lines, cells split by tabs.
    def table_cells(self) -> list:
        rows = [line.split("\t") for line in self.text.split("\n")] if self.text else [[""]]
        width = max(len(r) for r in rows)
        return [r + [""] * (width - len(r)) for r in rows]

    def clone(self) -> "Shape":
        twin = copy.deepcopy(self)
        twin.id = new_id()
        return twin


@dataclass
class Slide:
    shapes: list = field(default_factory=list)
    background: str = "#F5EDE0"
    notes: str = ""
    transition: str = "none"        # one of TRANSITIONS
    id: int = field(default_factory=new_id)

    def shape(self, shape_id):
        return next((s for s in self.shapes if s.id == shape_id), None)

    def title(self) -> str:
        for s in self.shapes:
            if s.role == "title" and s.text.strip():
                return s.text.strip().split("\n")[0]
        for s in self.shapes:
            if s.text.strip():
                return s.text.strip().split("\n")[0]
        return ""

    def clone(self) -> "Slide":
        return Slide([s.clone() for s in self.shapes], self.background, self.notes,
                     self.transition)


@dataclass
class Presentation:
    slides: list = field(default_factory=list)
    width: float = SLIDE_W
    height: float = SLIDE_H
