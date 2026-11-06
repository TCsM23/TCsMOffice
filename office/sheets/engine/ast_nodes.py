"""AST node types produced by the parser."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Number:
    value: float


@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Bool:
    value: bool


@dataclass(frozen=True)
class ErrorLit:
    code: str


@dataclass(frozen=True)
class Name:
    """A bare word that isn't TRUE/FALSE or a function call. Evaluates to #NAME?."""
    name: str


@dataclass(frozen=True)
class CellRef:
    row: int
    col: int


@dataclass(frozen=True)
class RangeRef:
    start: CellRef
    end: CellRef

    def cells(self):
        """Every (row, col) in the rectangle, row by row. Works for B3:A1 too."""
        r0, r1 = sorted((self.start.row, self.end.row))
        c0, c1 = sorted((self.start.col, self.end.col))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                yield (r, c)


@dataclass(frozen=True)
class BinOp:
    op: str  # one of + - * / ^ & = <> < > <= >=
    left: object
    right: object


@dataclass(frozen=True)
class UnaryOp:
    op: str  # + or -
    operand: object


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple


def references(node) -> set[tuple[int, int]]:
    """All cells a formula reads, with ranges expanded. Feeds the dependency graph."""
    out = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, CellRef):
            out.add((n.row, n.col))
        elif isinstance(n, RangeRef):
            out.update(n.cells())
        elif isinstance(n, BinOp):
            stack += [n.left, n.right]
        elif isinstance(n, UnaryOp):
            stack.append(n.operand)
        elif isinstance(n, Call):
            stack.extend(n.args)
    return out
