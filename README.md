# TCsOffice

A personal office suite in Python and PySide6, dressed in crimson, gilt and
parchment: **Sheets** (a spreadsheet with a hand-written formula engine),
**Writer** (rich text that saves `.docx`) and **Slides** (presentations that
open and save `.pptx`). One undo/redo design runs through all three.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m office                # opens the app
pytest                          # 265 tests, no window needed
```

The fonts (Alegreya SC, EB Garamond, Grenze Gotisch) ship in
`office/assets/fonts` under the SIL Open Font License and load at startup, so
nothing needs installing. Install them on your system as well if you want Word
and PowerPoint to show saved files in the same type.

## Install it

Every push to `main` on GitHub builds the app and publishes a Release
(see `.github/workflows/release.yml`). Each release carries:

| File | What it is |
|---|---|
| `TCsOffice-Setup-<version>.exe` | Windows installer wizard: pick a folder, tick "Create a desktop shortcut", done. Installs per user, so no admin prompt. |
| `TCsOffice-<version>.apk` | Android (64-bit ARM phones and tablets). Allow "install unknown apps" for your browser or Files app the first time. |
| `TCsOffice-<version>-x86_64.AppImage` | Linux: `chmod +x` it and run. |

The version is the `VERSION` file plus the build number, e.g. `1.1.17`. Bump
`VERSION` (now `1.1`) for a bigger release.

## Updates

The updater is part of the app (`office/updater.py`); nothing extra to
install. A few seconds after start-up an installed copy asks GitHub for the
latest release of `TCsM23/TCsMOffice` (set in `office/version.py`). If it is
newer, a dialog shows the release notes with **Update now**, **Later** and
**Skip this version**. You can also check by hand from the ⋮ menu.

- **Windows:** downloads the new Setup and runs it silently. It asks you to
  save unsaved work, closes the app, installs over it and reopens it.
- **Linux AppImage:** downloads the new AppImage, swaps it in, restarts.
- **Android:** opens the new APK and Android's installer asks you to confirm
  (Android never lets an app update itself silently). Updates install over
  the old app only if every APK is signed with the same key, so add the
  `ANDROID_KEYSTORE_B64` and `ANDROID_KEYSTORE_PASSWORD` repository secrets.
- Running from source (`python -m office`) never checks unless
  `TCSOFFICE_CHECK_UPDATES=1` is set; there it opens the release page.

The repository must be public, because the app reads releases without a token.

## Build it yourself

```bash
pip install -r requirements.txt pyinstaller
pyinstaller packaging/tcsoffice.spec --noconfirm   # dist/TCsOffice/
# Windows: then compile packaging\windows\TCsOffice.iss with Inno Setup 6
# Linux:   packaging/linux/build_appimage.sh 1.0.0
# Android: see packaging/android/build_apk.py (Linux host, Qt's Android wheels, NDK r28c)
python tools/make_icon.py                          # redraws the icon and wizard art
```

The Android build uses Qt's own `pyside6-android-deploy`, so the phone runs
the same app as the desktop, with a compact header. It is the desktop
interface on a small screen, so a tablet or landscape phone is the
comfortable way to use it.

## Keys

| Where | Keys |
|---|---|
| Everywhere | Ctrl+Z undo, Ctrl+Y or Ctrl+Shift+Z redo, Ctrl+N new, Ctrl+O open, Ctrl+S save, Ctrl+Shift+S save as, Ctrl+Shift+E export PDF, Ctrl+F find, Ctrl+H replace, Ctrl+1/2/3 switch module, F5 present |
| Sheets | type to edit, Enter moves down, Delete clears, Ctrl+C / Ctrl+X / Ctrl+V, Ctrl+B / I / U, Ctrl+D fill down, Ctrl+R fill right, right-click for rows, columns and sorting |
| Writer | Ctrl+B / I / U, Ctrl+Shift+X strikethrough, Ctrl+Space clear formatting, Ctrl+L / E / R / J alignment, Ctrl+Shift+8 bullets, Ctrl+Shift+7 numbers, right-click a table for rows and columns |
| Slides | double-click or Enter to edit text (Tab moves to the next table cell), Esc to finish, arrows nudge (Shift for 10 pt), Delete, Ctrl+C / Ctrl+V / Ctrl+D shapes |
| Slide show | Space, arrows or click to move, Home/End, B to black the screen, Esc to leave |

## What each module does

You can also open a file by dropping it on the window or passing it on the
command line (`python -m office report.docx`); the right module opens it.
Every module exports a PDF from the ⋮ menu.

**Sheets.** Formulas with `+ - * / ^`, `&` for joining text, comparisons
(`= <> < > <= >=`), `TRUE`/`FALSE`, and about a hundred functions:

| Kind | Functions |
|---|---|
| Maths | SUM, PRODUCT, ROUND, ROUNDUP, ROUNDDOWN, TRUNC, INT, MOD, ABS, SQRT, POWER, EXP, LN, LOG, LOG10, PI, SIGN, CEILING, FLOOR, EVEN, ODD, FACT, SIN, COS, TAN, DEGREES, RADIANS |
| Statistics | AVERAGE, MIN, MAX, COUNT, COUNTA, COUNTBLANK, MEDIAN, MODE, STDEV, STDEVP, VAR, VARP, LARGE, SMALL, RANK |
| Conditional | SUMIF, SUMIFS, COUNTIF, COUNTIFS, AVERAGEIF, SUMPRODUCT, with criteria like `">10"`, `"<>done"` and wildcards `"app*"` |
| Lookup | VLOOKUP, HLOOKUP, XLOOKUP, INDEX, MATCH, CHOOSE, ROWS, COLUMNS |
| Logic | IF, IFS, IFERROR, IFNA, AND, OR, NOT, XOR, ISBLANK, ISNUMBER, ISTEXT, ISLOGICAL, ISERROR, ISNA, NA |
| Text | CONCAT, CONCATENATE, TEXTJOIN, LEFT, RIGHT, MID, LEN, UPPER, LOWER, PROPER, TRIM, SUBSTITUTE, FIND, SEARCH, REPT, EXACT, VALUE, TEXT |

Cells take bold, italic, underline, text and fill colours, alignment and a
number format (thousands, decimals, percent, euro, pound, dollar, peso,
scientific). Sort a block by the current column (blank cells stay at the
bottom, a header row is detected), fill down or right, and insert or delete
rows and columns: every formula is rewritten the way Excel does it, including
`$A$1` references, growing and shrinking ranges and `#REF!` for deleted
cells. Find and replace searches values and formulas. The status bar shows the
sum, average and count of a selection. Charts (column, bar, line, pie) are
drawn from the selection in the house palette and can be saved as a picture
or sent straight onto the current slide. A side panel shows the dependency
graph for the selected cell. Copy and paste shifts relative references the
way Excel does (`$A$1` stays put), cut moves formulas unchanged, and pasting
tab-separated text from other apps works too. Saves and opens `.xlsx` with
formulas, formatting and column widths kept, and `.csv`.

**Writer.** Body text and three heading levels; font, size, text colour,
highlight, bold, italic, underline and strikethrough; clear formatting;
bulleted and numbered lists (a second numbered list restarts at 1, in Word as
well); four alignments; tables with gilt rules (add and remove rows and
columns from the right-click menu); pictures; a centred fleuron ornament to
break sections; find and replace with match case and whole words (Replace all
is one undo step); a live word count and Export PDF. Saves and opens `.docx`,
tables and pictures included; the house fonts and crimson headings are
written into the file's styles.

**Slides.** Six layouts in the house style (Title, Title and Content,
Section Header, Two Content, Quote, Blank), text boxes, tables (a crimson
header row and banded rows), pictures, and shapes: rectangle, rounded
rectangle, ellipse, triangle, diamond, hexagon, star and arrow. Drag to move,
drag the gold corner to resize, double-click to edit text in place. Font,
size, bold/italic/underline, bullets, alignment, text colour, fill, outline,
slide background. Arrange: bring to front, send to back, duplicate, align
(one shape to the slide, several to each other) and distribute. Transitions
per slide (fade, push, wipe, cover, zoom), played in the slide show and saved
so PowerPoint plays them too. Find and replace across every slide.
Thumbnails, speaker notes, a full-screen slide show, Export PDF (one vector
page per slide) and Save slide as picture. Saves and opens `.pptx`:
PowerPoint files with placeholders, groups, pictures, tables, the shapes
above and solid fills come in; charts come in as a labelled box.

## Layout

```
office/
  undo.py            # Command, MacroCommand, UndoStack: shared by all three
  theme.py           # palette, fonts, the Qt stylesheet
  version.py         # this build's version and the GitHub repo updates come from
  updater.py         # the built-in updater
  sheets/
    engine/          # pure Python, never imports Qt
      refs.py lexer.py ast_nodes.py parser.py evaluator.py errors.py
      graph.py       # precedents/dependents, BFS, Kahn's sort, Tarjan for cycles
      shift.py       # move a formula for copy and paste
      sheet.py       # the facade: set(addr, raw), raw(addr), value(addr)
      library.py     # lookups, conditional sums, statistics, text functions
      numfmt.py      # Excel number formats ("#,##0.00", "0%", ...)
      restructure.py # rewrite formulas when rows or columns are inserted or deleted
    formats.py       # CellFormat: bold, colours, alignment, number format
    ops.py           # sort, fill, find, insert/delete, chart data (plain Python)
    commands.py      # SetCellsCommand, SetFormatsCommand
    chart.py         # the chart dialog and painter
    model.py view.py xlsx_io.py
  writer/
    document.py docx_io.py   # plain-Python model and .docx I/O
    qt_bridge.py view.py
  slides/
    model.py layouts.py commands.py pptx_io.py   # no Qt
    render.py view.py
  findbar.py         # the find-and-replace bar all three modules share
  app.py
packaging/           # PyInstaller spec, Inno Setup wizard, AppImage and APK scripts
tools/make_icon.py   # draws the icon and the installer artwork
.github/workflows/release.yml
tests/
```

Every module has the same split: a plain-Python core the tests drive directly,
and a thin Qt layer on top.

## How undo works

`office/undo.py` is the command pattern in about a hundred lines. A `Command`
has `redo()` and `undo()`; the `UndoStack` keeps a list and an index, drops the
redo tail when you push something new, remembers which index was last saved
(so "edited" disappears if you undo back to it), and lets a command
`merge_with` the next one so arrow-key nudges or notes typing become one step.

Each module has its own stack, so undo in Writer never touches your sheet:

- **Sheets:** every edit, paste, cut or clear is a `SetCellsCommand` holding
  `{addr: (old_raw, new_raw)}`. Undo writes the old raws back and the
  dependency graph recalculates just as it does for a normal edit. Formatting
  is a `SetFormatsCommand`; sort, fill and inserting or deleting rows are one
  `MacroCommand` of both, so each is a single undo step.
- **Slides:** add, delete, move and duplicate slides; add and delete shapes;
  reorder; and `SetAttrsCommand` for every property change (position, size,
  text, font, colour, background, notes).
- **Writer:** Qt's text engine already records exactly what each keystroke
  did, so each step it records becomes a `TextDocumentCommand` on our stack,
  and Ctrl+Z, the context menu and the header buttons all go through our stack.

## How recalculation works

`Sheet.set("A1", "7")` stores the raw text, re-parses it, replaces A1's edges
in the graph, then:

1. BFS over `dependents` from A1 collects everything downstream.
2. Kahn's algorithm orders that subset so every cell runs after what it reads.
3. Anything Kahn can't place is checked with Tarjan's algorithm. Cells that are
   truly on a cycle become `#CIRC!`. Cells that only *read* a cycle are still
   evaluated and pick up `#CIRC!` through normal error propagation.

`test_only_dependents_are_recalculated` spies on the evaluator to prove
unrelated cells are never touched, and `test_two_cell_loop_and_breaking_it`
checks that breaking a loop brings the `#CIRC!` cells back.

## Design decisions pinned by tests

- `=-2^2` is **4**, as in Excel: unary minus binds tighter than `^`.
- `=2^3^2` is 512 (right-associative).
- Precedence, loosest first: comparisons, `&`, `+ -`, `* /`, `^`, unary minus.
- `IF` only evaluates the branch it picks, so `=IF(A1=0, 0, 1/A1)` is safe.
- `ROUND` rounds half away from zero like Excel, not banker's rounding.
- Empty cells are 0 in arithmetic and `""` next to text; numeric text coerces.
- A formula that doesn't parse shows `#ERROR!` instead of being rejected.

## Known limits

- One sheet per workbook, no merged cells, no whole-column ranges like `A:A`,
  no dates or volatile functions (TODAY, NOW, RAND). Charts live in the chart
  dialog (or on a slide as a picture), not inside the `.xlsx`.
- Writer has no nested lists, headers and footers, footnotes or tracked
  changes. Pasted text comes in plain. Heading 4+ from Word opens as
  Heading 3, and merged table cells open as separate cells.
- Slides formatting is per shape, not per word, and table cells share one
  style. No animations within a slide, no rotation, no master slides. Opening a
  `.pptx` with theme colours (not plain RGB) falls back to black text and a
  white background.
