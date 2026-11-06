"""The house style: crimson, gilt and parchment, with gothic and baroque type.

Colours live here once; the Qt stylesheet, the grid model, the Writer
headings and the slide layouts all read from this module.
"""
from pathlib import Path

# ---- palette ---------------------------------------------------------------
NIGHT = "#1B0709"          # window backdrop, slide stage
OXBLOOD = "#3B060C"        # header gradient end
CRIMSON = "#7A0E1B"        # the main red
CRIMSON_DARK = "#5A0A14"
CRIMSON_BRIGHT = "#9C1426"
GILT = "#B08D57"           # gold leaf lines and highlights
GILT_LIGHT = "#D9BF8A"
PARCHMENT = "#F7F0E4"      # main surfaces
VELLUM = "#EFE4D0"         # secondary surfaces, headers
PAGE = "#FFFBF3"           # the Writer page
RULE = "#D8C6A5"           # borders
GRID = "#E4D6BC"           # spreadsheet gridlines
INK = "#2B1A17"            # text
MUTED = "#7A6656"
IVORY = "#F3E7D3"
ERROR = "#A3141F"
PRECEDENT = "#F1D3D3"      # cells a formula reads (rose)
DEPENDENT = "#EFDDB0"      # cells that read this one (pale gold)

# Kept for code written against the first prototype's names.
ACCENT, TEXT, SURFACE, SUBTLE, BORDER, BG = CRIMSON, INK, PARCHMENT, VELLUM, RULE, NIGHT

# ---- type ------------------------------------------------------------------
TITLE_FAMILY = "Alegreya SC"
BODY_FAMILY = "EB Garamond"
BLACKLETTER_FAMILY = "Grenze Gotisch"
MONO = "'JetBrains Mono', 'Cascadia Mono', Consolas, 'DejaVu Sans Mono', monospace"

ASSETS = Path(__file__).parent / "assets"
FONT_DIR = ASSETS / "fonts"
_DOWN = (ASSETS / "chevron-down.svg").as_posix()
_UP = (ASSETS / "chevron-up.svg").as_posix()


def load_fonts():
    """Register the bundled fonts with Qt. Safe to call more than once."""
    from PySide6.QtGui import QFontDatabase

    for path in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))


STYLESHEET = f"""
* {{ font-family: '{BODY_FAMILY}'; }}
QWidget {{ color: {INK}; font-size: 16px; }}
QMainWindow, QWidget#root {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2A0A0F, stop:1 {NIGHT});
}}
QDialog, QMessageBox {{ background: {PARCHMENT}; }}
QToolTip {{ background: {PARCHMENT}; color: {INK}; border: 1px solid {GILT}; padding: 4px; }}

/* ---- the card and its header ---- */
QFrame#card {{ background: {PARCHMENT}; border: 1px solid {GILT}; border-radius: 4px; }}
QFrame#header {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6A0D18, stop:1 {OXBLOOD});
    border-bottom: 1px solid {GILT};
    border-top-left-radius: 4px; border-top-right-radius: 4px;
}}
QFrame#header QLabel {{ color: {IVORY}; }}
QFrame#ornament {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {CRIMSON_DARK}, stop:0.32 {CRIMSON_DARK}, stop:0.33 {GILT}, stop:0.66 {GILT},
        stop:0.67 {PARCHMENT}, stop:1 {PARCHMENT});
    max-height: 3px; min-height: 3px; border: none;
}}
QLabel#logo {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {CRIMSON_BRIGHT}, stop:1 {CRIMSON_DARK});
    color: {GILT_LIGHT}; border: 1px solid {GILT}; border-radius: 3px;
    font-family: '{BLACKLETTER_FAMILY}'; font-size: 24px;
}}
QLabel#appName {{ font-family: '{BLACKLETTER_FAMILY}'; font-size: 26px; color: {GILT_LIGHT}; }}
QLabel#fileName {{ font-style: italic; font-size: 15px; color: #D8C3B0; }}

QFrame#segment {{ background: rgba(0,0,0,0.25); border: 1px solid #8E6B3F; border-radius: 3px; }}
QPushButton#tab {{
    font-family: '{TITLE_FAMILY}'; font-size: 14px; font-weight: 700; letter-spacing: 1px;
    color: {GILT_LIGHT}; background: transparent; border: none; border-radius: 2px;
    padding: 6px 18px;
}}
QPushButton#tab:hover {{ background: rgba(217,191,138,0.12); }}
QPushButton#tab:checked {{ background: {PARCHMENT}; color: {CRIMSON}; }}

QPushButton {{
    font-family: '{TITLE_FAMILY}'; font-size: 14px; font-weight: 700; letter-spacing: 0.5px;
    background: {PARCHMENT}; color: {CRIMSON}; border: 1px solid {GILT}; border-radius: 3px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background: {VELLUM}; }}
QPushButton:disabled {{ color: #B7A592; border-color: {RULE}; }}
QFrame#header QPushButton {{ background: transparent; color: {IVORY}; border-color: #8E6B3F; }}
QFrame#header QPushButton:hover {{ background: rgba(217,191,138,0.14); border-color: {GILT_LIGHT}; }}
QFrame#header QPushButton:disabled {{ color: #8C6B66; border-color: #5E2A2C; }}
QFrame#header QPushButton#primary, QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GILT_LIGHT}, stop:1 {GILT});
    color: {CRIMSON_DARK}; border: 1px solid #E7D3A6;
}}
QFrame#header QToolButton#more {{ color: {IVORY}; font-size: 20px; padding: 2px 6px; }}
QFrame#header QToolButton#more:hover {{ background: rgba(217,191,138,0.14); border-color: #8E6B3F; }}
QProgressBar {{ background: {PAGE}; border: 1px solid {RULE}; border-radius: 3px; height: 14px;
                text-align: center; }}
QProgressBar::chunk {{ background: {CRIMSON}; }}
QTextBrowser {{ background: {PAGE}; border: 1px solid {RULE}; }}
QFrame#header QPushButton#primary:hover {{ background: {GILT_LIGHT}; }}

/* ---- toolbars ---- */
QFrame#toolbar, QFrame#formulaBar {{ background: {VELLUM}; border-bottom: 1px solid {RULE}; }}
QFrame#vdivider {{ background: {RULE}; }}
QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 3px;
    padding: 3px 8px; min-width: 18px; color: {INK}; font-size: 16px;
}}
QToolButton:hover {{ background: {PARCHMENT}; border-color: {RULE}; }}
QToolButton:checked {{ background: {CRIMSON}; color: {IVORY}; border-color: {CRIMSON_DARK}; }}
QToolButton:disabled {{ color: #B7A592; }}
QToolButton::menu-indicator {{ image: none; }}
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {PAGE}; border: 1px solid {RULE}; border-radius: 3px; padding: 2px 8px;
    min-height: 22px; selection-background-color: {CRIMSON};
}}
QComboBox {{ min-width: 120px; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({_DOWN}); width: 10px; height: 6px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{ border: none; width: 16px; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_UP}); width: 9px; height: 5px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_DOWN}); width: 9px; height: 5px; }}
QComboBox QAbstractItemView {{ background: {PAGE}; selection-background-color: {CRIMSON};
                               selection-color: {IVORY}; border: 1px solid {GILT}; }}
QMenu {{ background: {PARCHMENT}; border: 1px solid {GILT}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px; }}
QMenu::item:selected {{ background: {CRIMSON}; color: {IVORY}; }}
QMenu::separator {{ height: 1px; background: {RULE}; margin: 4px 8px; }}

QLineEdit, QPlainTextEdit {{
    background: {PAGE}; border: 1px solid {RULE}; border-radius: 3px; padding: 4px 8px;
    selection-background-color: {CRIMSON}; selection-color: {IVORY};
}}
QLineEdit {{ font-family: {MONO}; font-size: 13px; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {CRIMSON}; }}
QLabel#fx {{ color: {CRIMSON}; font-style: italic; font-size: 18px; }}

/* ---- Sheets ---- */
QTableView {{
    background: #FBF6EC; gridline-color: {GRID}; border: none;
    font-family: '{BODY_FAMILY}'; font-size: 16px;
}}
QTableView::item:selected {{ background: #F3E3C3; }}
QTableView::item:focus {{ border: 2px solid {CRIMSON}; }}
QHeaderView::section {{
    background: {VELLUM}; color: {CRIMSON}; border: none;
    border-right: 1px solid {GRID}; border-bottom: 1px solid {GRID};
    padding: 3px; font-family: '{TITLE_FAMILY}'; font-size: 13px; font-weight: 700;
}}
QTableCornerButton::section {{ background: {VELLUM}; border: none; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {VELLUM}; border: none; margin: 0; }}
QScrollBar:vertical {{ width: 11px; }}
QScrollBar:horizontal {{ height: 11px; }}
QScrollBar::handle {{ background: #C9B48E; border-radius: 4px; min-height: 30px; min-width: 30px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {GILT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QFrame#depPanel {{ background: {VELLUM}; border-left: 1px solid {GILT}; }}
QLabel#eyebrow {{ color: {CRIMSON}; font-family: '{TITLE_FAMILY}'; font-size: 12px;
                  font-weight: 700; letter-spacing: 2px; }}
QLabel#cellTitle {{ font-family: '{TITLE_FAMILY}'; font-size: 22px; font-weight: 700; color: {INK}; }}
QLabel#mono {{ font-family: {MONO}; font-size: 12px; color: {MUTED}; }}
QLabel#sectionTitle {{ font-family: '{TITLE_FAMILY}'; font-size: 13px; font-weight: 700;
                       letter-spacing: 1px; color: {INK}; }}
QLabel#muted {{ color: {MUTED}; font-size: 15px; font-style: italic; }}
QFrame#planBox {{ background: {PAGE}; border: 1px solid {RULE}; border-left: 3px solid {CRIMSON};
                  border-radius: 2px; }}

QFrame#statusBar {{ background: {VELLUM}; border-top: 1px solid {RULE};
                    border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; }}

/* ---- Writer ---- */
QWidget#pageArea {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E8DAC0, stop:1 #DCCAA8); }}
QTextEdit#page {{ background: {PAGE}; border: 3px double {GILT}; selection-background-color: {CRIMSON};
                  selection-color: {IVORY}; }}

/* ---- Slides ---- */
QListWidget#thumbs {{ background: {VELLUM}; border: none; border-right: 1px solid {GILT}; outline: 0; }}
QListWidget#thumbs::item {{ color: {MUTED}; padding: 4px; border: 2px solid transparent; }}
QListWidget#thumbs::item:selected {{ background: transparent; color: {CRIMSON}; border: 2px solid {CRIMSON}; }}
QGraphicsView#stage {{ background: qradialgradient(cx:0.5, cy:0.45, radius:0.9, fx:0.5, fy:0.45,
                       stop:0 #3A0E14, stop:1 {NIGHT}); border: none; }}
QPlainTextEdit#notes {{ font-size: 16px; border: none; border-top: 1px solid {GILT};
                        border-radius: 0; background: {PAGE}; }}
"""
