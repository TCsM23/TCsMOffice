"""Convert between "A1"-style addresses and zero-based (row, col) pairs.

Column letters are bijective base 26: A=1 ... Z=26, AA=27. There is no zero
digit, which is why the conversion subtracts 1 inside the loop.
"""
import re

_REF_RE = re.compile(r"^\$?([A-Za-z]+)\$?([0-9]+)$")


def col_to_index(letters: str) -> int:
    """'A' -> 0, 'Z' -> 25, 'AA' -> 26."""
    n = 0
    for ch in letters.upper():
        if not "A" <= ch <= "Z":
            raise ValueError(f"bad column letters: {letters!r}")
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def index_to_col(index: int) -> str:
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA'."""
    if index < 0:
        raise ValueError(f"negative column index: {index}")
    n = index + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def split_ref(addr: str) -> tuple[int, int]:
    """Like parse_ref but lets row 0 through (as -1) so the evaluator can say #REF!."""
    m = _REF_RE.match(addr.strip())
    if not m:
        raise ValueError(f"not a cell reference: {addr!r}")
    return int(m.group(2)) - 1, col_to_index(m.group(1))


def parse_ref(addr: str) -> tuple[int, int]:
    """'B3' -> (2, 1). A '$' (absolute marker) is accepted and ignored."""
    row, col = split_ref(addr)
    if row < 0:
        raise ValueError(f"row must be 1 or more: {addr!r}")
    return row, col


def to_addr(row: int, col: int) -> str:
    """(2, 1) -> 'B3'."""
    return f"{index_to_col(col)}{row + 1}"


def is_ref(text: str) -> bool:
    return bool(_REF_RE.match(text))
