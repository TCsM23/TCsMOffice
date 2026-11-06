"""Slide layouts in the suite's house style: parchment, crimson and gilt."""
from .model import SLIDE_H, SLIDE_W, Shape, Slide, TextStyle

PARCHMENT = "#F5EDE0"
NIGHT = "#22090D"
CRIMSON = "#7A0E1B"
INK = "#2B1A17"
GILT = "#B08D57"
IVORY = "#F3E7D3"
TITLE_FONT = "Alegreya SC"
BODY_FONT = "EB Garamond"
DISPLAY_FONT = "Grenze Gotisch"

LAYOUTS = ["Title", "Title and Content", "Section Header", "Two Content", "Quote", "Blank"]


def _frame(color=GILT):
    """A double gilt rule around the slide edge."""
    return [
        Shape("rect", 18, 18, SLIDE_W - 36, SLIDE_H - 36, line=color, line_width=2.0),
        Shape("rect", 26, 26, SLIDE_W - 52, SLIDE_H - 52, line=color, line_width=0.75),
    ]


def _title(text, y=36, h=78, size=34.0, color=CRIMSON, align="left", x=64, w=SLIDE_W - 128):
    return Shape("text", x, y, w, h, text=text, role="title",
                 style=TextStyle(TITLE_FONT, size, bold=True, color=color, align=align,
                                 valign="middle"))


def _rule(y, x=64, w=SLIDE_W - 128, color=GILT):
    return Shape("rect", x, y, w, 2, fill=color)


def _body(text, x=64, y=140, w=SLIDE_W - 128, h=340, size=24.0, bullets=True):
    return Shape("text", x, y, w, h, text=text, bullets=bullets, role="body",
                 style=TextStyle(BODY_FONT, size, color=INK))


def make_slide(layout: str, title="", body="", subtitle="") -> Slide:
    if layout == "Title":
        return Slide(_frame() + [
            _title(title or "Click to add a title", y=150, h=120, size=50, align="center"),
            _rule(290, x=380, w=200),
            Shape("text", 120, 310, SLIDE_W - 240, 70, text=subtitle or "Subtitle", role="body",
                  style=TextStyle(BODY_FONT, 26, italic=True, color=INK, align="center")),
        ], PARCHMENT)
    if layout == "Title and Content":
        return Slide([_title(title or "Title"), _rule(118),
                      _body(body or "First point\nSecond point")], PARCHMENT)
    if layout == "Section Header":
        return Slide(_frame(GILT) + [
            _title(title or "Section", y=190, h=110, size=46, color=GILT, align="center"),
            Shape("text", 120, 300, SLIDE_W - 240, 60, text=subtitle or "", role="body",
                  style=TextStyle(BODY_FONT, 24, italic=True, color=IVORY, align="center")),
        ], NIGHT)
    if layout == "Two Content":
        half = (SLIDE_W - 128 - 32) / 2
        return Slide([_title(title or "Title"), _rule(118),
                      _body(body or "Left point", w=half),
                      _body(subtitle or "Right point", x=64 + half + 32, w=half)], PARCHMENT)
    if layout == "Quote":
        return Slide(_frame() + [
            Shape("text", 110, 120, SLIDE_W - 220, 220, text=body or "“A quotation.”",
                  role="body",
                  style=TextStyle(BODY_FONT, 38, italic=True, color=CRIMSON, align="center",
                                  valign="middle")),
            Shape("text", 110, 360, SLIDE_W - 220, 50, text=subtitle or "— Author",
                  style=TextStyle(TITLE_FONT, 18, color=INK, align="center")),
        ], PARCHMENT)
    return Slide([], PARCHMENT)


def sample_presentation():
    from .model import Presentation
    return Presentation([
        make_slide("Title", "TCsOffice", subtitle="Sheets · Writer · Slides"),
        make_slide("Title and Content", "What it does",
                   "A spreadsheet with its own formula engine\n"
                   "A writer that speaks .docx\n"
                   "Slides that open and save .pptx\n"
                   "One undo stack design across all three"),
        make_slide("Section Header", "The Engine", subtitle="Lexer, parser, evaluator, graph"),
        make_slide("Quote", body="“Make it work, make it right, make it fast.”",
                   subtitle="— Kent Beck"),
    ])
