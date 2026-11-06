"""Move a formula by (drow, dcol), the way copy and paste does in Excel.

=A1+$B$1 copied one row down becomes =A2+$B$1: relative parts move, parts
with a '$' stay put. A reference pushed off the top or left edge becomes #REF!.
"""
import re

from .lexer import CELL, FormulaSyntaxError, tokenize
from .refs import col_to_index, index_to_col

_PARTS = re.compile(r"^(\$?)([A-Z]+)(\$?)([0-9]+)$")


def shift_ref(text: str, drow: int, dcol: int) -> str:
    col_abs, letters, row_abs, digits = _PARTS.match(text).groups()
    col = col_to_index(letters) + (0 if col_abs else dcol)
    row = int(digits) - 1 + (0 if row_abs else drow)
    if col < 0 or row < 0:
        return "#REF!"
    return f"{col_abs}{index_to_col(col)}{row_abs}{row + 1}"


def shift_formula(raw: str, drow: int, dcol: int) -> str:
    if not raw.startswith("=") or (drow == 0 and dcol == 0):
        return raw
    body = raw[1:]
    try:
        tokens = tokenize(body)
    except FormulaSyntaxError:
        return raw
    out, last = [], 0
    for tok in tokens:
        if tok.type == CELL:
            end = tok.pos + len(tok.value)
            out.append(body[last:tok.pos])
            out.append(shift_ref(tok.value, drow, dcol))
            last = end
    out.append(body[last:])
    return "=" + "".join(out)
