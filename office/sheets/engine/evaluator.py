"""Walk an AST and compute a value.

The evaluator never touches the sheet. It gets a lookup callback,
get(row, col) -> value, so it can be tested with a plain dict.

Values are: float, str, bool, None (an empty cell) or CellError.
"""
import math

from .ast_nodes import (
    BinOp, Bool, Call, CellRef, ErrorLit, Name, Number, RangeRef, Str, UnaryOp,
)
from .errors import DIV0, NAME, NUM, VALUE, CellError


class _Range(list):
    """A range evaluates to a flat list of values, row by row. Only functions
    accept one. `rows` and `cols` give its shape, for lookups like VLOOKUP."""

    rows = 0
    cols = 0

    def at(self, r, c):
        return self[r * self.cols + c]


def _to_number(v):
    """Coerce for arithmetic. Empty is 0, TRUE is 1, numeric text like "3" is 3."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return VALUE
    return VALUE


def _to_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return f"{int(v)}" if v.is_integer() and abs(v) < 1e15 else f"{v:.10g}"
    return str(v)


def _to_bool(v):
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return v != 0
    if isinstance(v, str) and v.upper() in ("TRUE", "FALSE"):
        return v.upper() == "TRUE"
    return VALUE


def _compare_key(v, other):
    """Excel orders numbers < text < booleans; text compares case-insensitively.
    An empty cell acts as 0, "" or FALSE depending on what it's compared with."""
    if v is None:
        v = "" if isinstance(other, str) else (False if isinstance(other, bool) else 0.0)
    if isinstance(v, bool):
        return (2, v)
    if isinstance(v, str):
        return (1, v.lower())
    return (0, v)


_COMPARE = {
    "=": lambda a, b: a == b, "<>": lambda a, b: a != b,
    "<": lambda a, b: a < b, ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
}


def _flatten(args):
    for a in args:
        if isinstance(a, _Range):
            yield from a
        else:
            yield a


def _numbers(args):
    """Flatten function arguments into numbers, Excel style.

    Inside a range, text, booleans and empty cells are skipped. A direct
    argument must be a number (or numeric text, or TRUE/FALSE). The first error
    found is returned instead.
    """
    out = []
    for a in args:
        if isinstance(a, CellError):
            return a
        if isinstance(a, _Range):
            for v in a:
                if isinstance(v, CellError):
                    return v
                if isinstance(v, float):
                    out.append(v)
        else:
            n = _to_number(a)
            if isinstance(n, CellError):
                return n
            out.append(n)
    return out


def _numeric(fn):
    """Decorator: run fn on the list of numbers, or pass an error through."""
    def wrapper(args):
        nums = _numbers(args)
        return nums if isinstance(nums, CellError) else fn(nums)
    return wrapper


def _exactly(n, fn):
    """Decorator for fixed-arity functions: wrong count is #VALUE!, errors propagate."""
    def wrapper(args):
        if len(args) != n:
            return VALUE
        for a in args:
            if isinstance(a, CellError):
                return a
            if isinstance(a, _Range):
                return VALUE
        return fn(*args)
    return wrapper


def _num1(fn):
    def inner(x):
        n = _to_number(x)
        return n if isinstance(n, CellError) else fn(n)
    return _exactly(1, inner)


def _text1(fn):
    return _exactly(1, lambda x: fn(_to_text(x)))


def _round(x, digits):
    x, digits = _to_number(x), _to_number(digits)
    for n in (x, digits):
        if isinstance(n, CellError):
            return n
    factor = 10 ** int(digits)
    # Round half away from zero, like Excel (Python's round() is banker's rounding).
    return math.copysign(math.floor(abs(x) * factor + 0.5) / factor, x)


def _mod(a, b):
    a, b = _to_number(a), _to_number(b)
    for n in (a, b):
        if isinstance(n, CellError):
            return n
    return DIV0 if b == 0 else a - b * math.floor(a / b)


def _logical(combine):
    def fn(args):
        values = []
        for v in _flatten(args):
            if isinstance(v, CellError):
                return v
            if v is None or (isinstance(v, str) and v.upper() not in ("TRUE", "FALSE")):
                continue  # Excel skips blanks and text in AND/OR
            values.append(_to_bool(v))
        return combine(values) if values else VALUE
    return fn


def _not(x):
    b = _to_bool(x)
    return b if isinstance(b, CellError) else not b


def _concat(args):
    parts = []
    for v in _flatten(args):
        if isinstance(v, CellError):
            return v
        parts.append(_to_text(v))
    return "".join(parts)


def _counta(args):
    return float(sum(1 for v in _flatten(args) if v is not None))


def _count(args):
    """Counts numbers. Like Excel, errors and text are not counted (and don't propagate)."""
    n = 0
    for a in args:
        values = a if isinstance(a, _Range) else [a]
        n += sum(1 for v in values if isinstance(v, float))
    return float(n)


# Adding a function is one line here.
FUNCTIONS = {
    "SUM": _numeric(lambda xs: float(math.fsum(xs))),
    "AVERAGE": _numeric(lambda xs: math.fsum(xs) / len(xs) if xs else DIV0),
    "MIN": _numeric(lambda xs: min(xs) if xs else 0.0),
    "MAX": _numeric(lambda xs: max(xs) if xs else 0.0),
    "PRODUCT": _numeric(lambda xs: float(math.prod(xs)) if xs else 0.0),
    "COUNT": _count,
    "COUNTA": _counta,
    "ABS": _num1(abs),
    "SQRT": _num1(lambda x: NUM if x < 0 else math.sqrt(x)),
    "INT": _num1(lambda x: float(math.floor(x))),
    "ROUND": _exactly(2, _round),
    "MOD": _exactly(2, _mod),
    "AND": _logical(all),
    "OR": _logical(any),
    "NOT": _exactly(1, _not),
    "CONCAT": _concat,
    "LEN": _text1(lambda t: float(len(t))),
    "UPPER": _text1(str.upper),
    "LOWER": _text1(str.lower),
}

# IF is a special form: only the chosen branch is evaluated, so
# =IF(A1=0, 0, 1/A1) never even computes the division when A1 is 0.
SPECIAL_FORMS = {"IF", "IFERROR", "IFNA", "IFS", "CHOOSE"}


class Evaluator:
    def __init__(self, get, functions=None):
        self.get = get
        self.functions = FUNCTIONS if functions is None else functions

    def evaluate(self, node):
        """Top-level entry: the value a cell displays."""
        result = self.visit(node)
        if result is None:  # =A1 where A1 is empty shows 0
            return 0.0
        if isinstance(result, _Range):  # a bare =A1:A3
            return VALUE
        return result

    def visit(self, node):
        method = getattr(self, "visit_" + type(node).__name__)
        return method(node)

    def visit_Number(self, node: Number):
        return node.value

    def visit_Str(self, node: Str):
        return node.value

    def visit_Bool(self, node: Bool):
        return node.value

    def visit_ErrorLit(self, node: ErrorLit):
        return CellError(node.code)

    def visit_Name(self, node: Name):
        return NAME

    def visit_CellRef(self, node: CellRef):
        return self.get(node.row, node.col)

    def visit_RangeRef(self, node: RangeRef):
        out = _Range(self.get(r, c) for r, c in node.cells())
        out.rows = abs(node.end.row - node.start.row) + 1
        out.cols = abs(node.end.col - node.start.col) + 1
        return out

    def visit_UnaryOp(self, node: UnaryOp):
        v = self.visit(node.operand)
        if isinstance(v, _Range):
            return VALUE
        n = _to_number(v)
        if isinstance(n, CellError):
            return v if isinstance(v, CellError) else n
        return -n if node.op == "-" else n

    def visit_BinOp(self, node: BinOp):
        left = self.visit(node.left)
        right = self.visit(node.right)
        # Errors propagate: the leftmost error wins.
        for v in (left, right):
            if isinstance(v, CellError):
                return v
            if isinstance(v, _Range):
                return VALUE
        op = node.op
        if op == "&":
            return _to_text(left) + _to_text(right)
        if op in _COMPARE:
            return _COMPARE[op](_compare_key(left, right), _compare_key(right, left))
        a, b = _to_number(left), _to_number(right)
        for n in (a, b):
            if isinstance(n, CellError):
                return n
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return DIV0 if b == 0 else a / b
        if op == "^":
            if a == 0 and b < 0:
                return DIV0
            try:
                result = a ** b
            except OverflowError:
                return NUM
            if isinstance(result, complex):  # (-8)^0.5
                return NUM
            return float(result)
        raise ValueError(f"unknown operator {op}")

    def visit_Call(self, node: Call):
        if node.name in SPECIAL_FORMS:
            return getattr(self, "special_" + node.name)(node.args)
        fn = self.functions.get(node.name)
        if fn is None:
            return NAME
        args = [self.visit(a) for a in node.args]
        return fn(args)

    def special_IF(self, args):
        if len(args) not in (2, 3):
            return VALUE
        cond = self.visit(args[0])
        if isinstance(cond, CellError):
            return cond
        if isinstance(cond, _Range):
            return VALUE
        truth = _to_bool(cond)
        if isinstance(truth, CellError):
            return truth
        if truth:
            return self.visit(args[1])
        return self.visit(args[2]) if len(args) == 3 else False

    def _scalar(self, node):
        v = self.visit(node)
        return VALUE if isinstance(v, _Range) else v

    def special_IFERROR(self, args):
        if len(args) != 2:
            return VALUE
        v = self._scalar(args[0])
        return self.visit(args[1]) if isinstance(v, CellError) else v

    def special_IFNA(self, args):
        if len(args) != 2:
            return VALUE
        v = self._scalar(args[0])
        return self.visit(args[1]) if v == CellError("#N/A") else v

    def special_IFS(self, args):
        """IFS(cond1, value1, cond2, value2, ...): the first true condition wins."""
        if not args or len(args) % 2:
            return VALUE
        for cond_node, value_node in zip(args[::2], args[1::2]):
            cond = self._scalar(cond_node)
            if isinstance(cond, CellError):
                return cond
            truth = _to_bool(cond)
            if isinstance(truth, CellError):
                return truth
            if truth:
                return self.visit(value_node)
        return CellError("#N/A")

    def special_CHOOSE(self, args):
        if len(args) < 2:
            return VALUE
        n = _to_number(self._scalar(args[0]))
        if isinstance(n, CellError):
            return n
        i = int(n)
        if not 1 <= i < len(args):
            return VALUE
        return self.visit(args[i])


# The bigger function library lives in its own module and adds itself to
# FUNCTIONS. Imported last because it uses the helpers above.
from . import library  # noqa: E402,F401  (registers itself)
