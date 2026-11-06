"""Rewrite formulas when rows or columns are inserted or deleted.

Unlike copy and paste, this moves absolute references too: inserting a row
above A5 turns both =A5 and =$A$5 into A6, exactly as Excel does. A reference
to a deleted cell becomes #REF!; a range that loses some rows shrinks, and a
range that loses all of them becomes #REF!.
"""
import re

from .lexer import CELL, COLON, FormulaSyntaxError, tokenize
from .refs import col_to_index, index_to_col

_PARTS = re.compile(r"^(\$?)([A-Z]+)(\$?)([0-9]+)$")


def _split(text):
    col_abs, letters, row_abs, digits = _PARTS.match(text).groups()
    return col_abs, col_to_index(letters), row_abs, int(digits) - 1


def _join(col_abs, col, row_abs, row):
    return f"{col_abs}{index_to_col(col)}{row_abs}{row + 1}"


def _move(index, at, count):
    """New index after inserting (count > 0) or deleting (count < 0) at `at`.
    None means the cell was deleted."""
    if index < at:
        return index
    if count > 0:
        return index + count
    if index < at - count:
        return None
    return index + count


def _ref(text, axis, at, count):
    ca, c, ra, r = _split(text)
    if axis == "row":
        r = _move(r, at, count)
    else:
        c = _move(c, at, count)
    return None if r is None or c is None else _join(ca, c, ra, r)


def _range(a, b, axis, at, count):
    sa, sb = _split(a), _split(b)
    i = 3 if axis == "row" else 1
    lo, hi = sorted((sa[i], sb[i]))
    new_lo, new_hi = _move(lo, at, count), _move(hi, at, count)
    if count < 0:
        if new_lo is None and new_hi is None:
            return None
        if new_lo is None:
            new_lo = at
        if new_hi is None:
            new_hi = at - 1
        if new_hi < new_lo:
            return None
    first, second = list(sa), list(sb)
    if sa[i] <= sb[i]:
        first[i], second[i] = new_lo, new_hi
    else:
        first[i], second[i] = new_hi, new_lo
    return _join(*first) + ":" + _join(*second)


def restructure_formula(raw: str, axis: str, at: int, count: int) -> str:
    """axis is "row" or "col"; at is zero-based; count > 0 inserts, < 0 deletes."""
    if not raw.startswith("=") or count == 0:
        return raw
    body = raw[1:]
    try:
        tokens = tokenize(body)
    except FormulaSyntaxError:
        return raw
    out, last, i = [], 0, 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == CELL:
            if (i + 2 < len(tokens) and tokens[i + 1].type == COLON
                    and tokens[i + 2].type == CELL):
                end_tok = tokens[i + 2]
                new = _range(tok.value, end_tok.value, axis, at, count)
                end = end_tok.pos + len(end_tok.value)
                i += 3
            else:
                new = _ref(tok.value, axis, at, count)
                end = tok.pos + len(tok.value)
                i += 1
            out.append(body[last:tok.pos])
            out.append("#REF!" if new is None else new)
            last = end
            continue
        i += 1
    out.append(body[last:])
    return "=" + "".join(out)
