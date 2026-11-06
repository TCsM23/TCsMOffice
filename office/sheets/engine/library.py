"""The wider function library: lookups, conditional sums, statistics, text and
information functions. Each one is added to evaluator.FUNCTIONS by name.

Arguments arrive already evaluated: a scalar (float, str, bool, None, or
CellError) or an evaluator._Range (a flat list with .rows and .cols).
"""
import math
import re
import statistics

from .errors import DIV0, NA, NUM, VALUE, CellError
from .evaluator import (
    FUNCTIONS, _Range, _compare_key, _exactly, _flatten, _numbers, _to_bool, _to_number,
    _to_text,
)
from .numfmt import format_number


def register(name):
    def deco(fn):
        FUNCTIONS[name] = fn
        return fn
    return deco


def _first_error(*values):
    for v in values:
        if isinstance(v, CellError):
            return v
    return None


def _nums(*values):
    """Coerce scalars to numbers. Returns a list, or the first error."""
    out = []
    for v in values:
        n = _to_number(v)
        if isinstance(n, CellError):
            return v if isinstance(v, CellError) else n
        out.append(n)
    return out


def _as_range(v):
    if isinstance(v, _Range):
        return v
    r = _Range([v])
    r.rows = r.cols = 1
    return r


def _arity(lo, hi, fn):
    """Accept lo..hi arguments; scalars only; errors propagate."""
    def wrapper(args):
        if not lo <= len(args) <= hi:
            return VALUE
        for a in args:
            if isinstance(a, CellError):
                return a
            if isinstance(a, _Range):
                return VALUE
        return fn(*args)
    return wrapper


# ---- criteria (SUMIF, COUNTIF, ...) ----------------------------------------

_OPS = ("<>", ">=", "<=", "=", ">", "<")


def _wildcard(pattern):
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "~" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE | re.DOTALL)


def criteria(crit):
    """Turn a criterion like 5, ">10", "<>done" or "app*" into a predicate."""
    if isinstance(crit, (float, bool)):
        return lambda v: (v is not None and not isinstance(v, CellError)
                          and _compare_key(v, crit) == _compare_key(crit, v))
    text = _to_text(crit)
    op = next((o for o in _OPS if text.startswith(o)), "")
    rest = text[len(op):]
    op = op or "="
    try:
        target = float(rest)
    except ValueError:
        target = None
    if target is not None:
        def numeric(v):
            if isinstance(v, str):
                try:
                    v = float(v)
                except ValueError:
                    return op == "<>"
            if not isinstance(v, float) or isinstance(v, bool):
                return op == "<>"
            return {"=": v == target, "<>": v != target, ">": v > target, "<": v < target,
                    ">=": v >= target, "<=": v <= target}[op]
        return numeric
    if rest == "":
        if op == "=":
            return lambda v: v is None or v == ""
        return lambda v: v is not None and v != ""
    if op in ("=", "<>"):
        rx = _wildcard(rest)
        match = lambda v: isinstance(v, str) and bool(rx.match(v))  # noqa: E731
        return match if op == "=" else (lambda v: not match(v))
    low = rest.lower()

    def textual(v):
        if not isinstance(v, str):
            return False
        a = v.lower()
        return {">": a > low, "<": a < low, ">=": a >= low, "<=": a <= low}[op]
    return textual


def _pairs(args):
    """(range, criterion) pairs for COUNTIFS / SUMIFS. None if shapes don't match."""
    if len(args) % 2:
        return None
    pairs = [(_as_range(r), criteria(c)) for r, c in zip(args[::2], args[1::2])]
    sizes = {len(r) for r, _ in pairs}
    return pairs if len(sizes) == 1 else None


def _mask(pairs):
    n = len(pairs[0][0])
    return [all(pred(rng[i]) for rng, pred in pairs) for i in range(n)]


@register("COUNTIF")
def _countif(args):
    if len(args) != 2:
        return VALUE
    if isinstance(args[1], CellError):
        return args[1]
    pred = criteria(args[1])
    return float(sum(1 for v in _as_range(args[0]) if pred(v)))


@register("COUNTIFS")
def _countifs(args):
    pairs = _pairs(args)
    if not pairs:
        return VALUE
    return float(sum(_mask(pairs)))


def _sum_matching(values, mask):
    total = []
    for v, ok in zip(values, mask):
        if ok:
            if isinstance(v, CellError):
                return v
            if isinstance(v, float) and not isinstance(v, bool):
                total.append(v)
    return total


@register("SUMIF")
def _sumif(args):
    if len(args) not in (2, 3):
        return VALUE
    rng = _as_range(args[0])
    sum_rng = _as_range(args[2]) if len(args) == 3 else rng
    if len(sum_rng) != len(rng):
        return VALUE
    pred = criteria(args[1])
    vals = _sum_matching(sum_rng, [pred(v) for v in rng])
    return vals if isinstance(vals, CellError) else float(math.fsum(vals))


@register("AVERAGEIF")
def _averageif(args):
    if len(args) not in (2, 3):
        return VALUE
    rng = _as_range(args[0])
    avg_rng = _as_range(args[2]) if len(args) == 3 else rng
    if len(avg_rng) != len(rng):
        return VALUE
    pred = criteria(args[1])
    vals = _sum_matching(avg_rng, [pred(v) for v in rng])
    if isinstance(vals, CellError):
        return vals
    return math.fsum(vals) / len(vals) if vals else DIV0


@register("SUMIFS")
def _sumifs(args):
    if len(args) < 3:
        return VALUE
    sum_rng = _as_range(args[0])
    pairs = _pairs(args[1:])
    if not pairs or len(pairs[0][0]) != len(sum_rng):
        return VALUE
    vals = _sum_matching(sum_rng, _mask(pairs))
    return vals if isinstance(vals, CellError) else float(math.fsum(vals))


@register("SUMPRODUCT")
def _sumproduct(args):
    if not args:
        return VALUE
    ranges = [_as_range(a) for a in args]
    if len({len(r) for r in ranges}) != 1:
        return VALUE
    total = []
    for items in zip(*ranges):
        err = _first_error(*items)
        if err:
            return err
        p = 1.0
        for v in items:
            p *= v if isinstance(v, float) and not isinstance(v, bool) else 0.0
        total.append(p)
    return float(math.fsum(total))


@register("COUNTBLANK")
def _countblank(args):
    return float(sum(1 for v in _flatten(args) if v is None or v == ""))


# ---- statistics ------------------------------------------------------------

def _stat(fn, minimum=1):
    def wrapper(args):
        xs = _numbers(args)
        if isinstance(xs, CellError):
            return xs
        if len(xs) < minimum:
            return DIV0
        return float(fn(xs))
    return wrapper


FUNCTIONS.update({
    "MEDIAN": _stat(statistics.median),
    "STDEV": _stat(statistics.stdev, 2),
    "STDEV.S": _stat(statistics.stdev, 2),
    "STDEVP": _stat(statistics.pstdev),
    "STDEV.P": _stat(statistics.pstdev),
    "VAR": _stat(statistics.variance, 2),
    "VAR.S": _stat(statistics.variance, 2),
    "VARP": _stat(statistics.pvariance),
    "VAR.P": _stat(statistics.pvariance),
})


@register("MODE")
def _mode(args):
    xs = _numbers(args)
    if isinstance(xs, CellError):
        return xs
    counts = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    best = max(counts.values(), default=0)
    if best < 2:
        return NA
    return next(x for x in xs if counts[x] == best)


def _kth(largest):
    def fn(args):
        if len(args) != 2:
            return VALUE
        xs = _numbers([args[0]] if isinstance(args[0], _Range) else [args[0]])
        if isinstance(xs, CellError):
            return xs
        k = _to_number(args[1])
        if isinstance(k, CellError):
            return k
        k = int(math.ceil(k))
        if not 1 <= k <= len(xs):
            return NUM
        return sorted(xs, reverse=largest)[k - 1]
    return fn


FUNCTIONS["LARGE"] = _kth(True)
FUNCTIONS["SMALL"] = _kth(False)


@register("RANK")
def _rank(args):
    if len(args) not in (2, 3):
        return VALUE
    x = _to_number(args[0])
    if isinstance(x, CellError):
        return x
    xs = _numbers([args[1]])
    if isinstance(xs, CellError):
        return xs
    ascending = len(args) == 3 and _to_bool(args[2]) is True
    if x not in xs:
        return NA
    better = sum(1 for v in xs if (v < x if ascending else v > x))
    return float(better + 1)


# ---- maths -----------------------------------------------------------------

def _num_fn(lo, hi, fn):
    def inner(*args):
        nums = _nums(*args)
        return nums if isinstance(nums, CellError) else fn(*nums)
    return _arity(lo, hi, inner)


def _log(x, base=10.0):
    if x <= 0 or base <= 0 or base == 1:
        return NUM
    return math.log(x, base)


def _power(a, b):
    if a == 0 and b < 0:
        return DIV0
    try:
        r = a ** b
    except OverflowError:
        return NUM
    return NUM if isinstance(r, complex) else float(r)


def _round_dir(x, digits=0.0, up=True):
    f = 10 ** int(digits)
    v = abs(x) * f
    v = math.ceil(v - 1e-9) if up else math.floor(v + 1e-9)
    return math.copysign(v / f, x)


def _to_multiple(x, sig=1.0, up=True):
    if sig == 0:
        return 0.0
    if x > 0 and sig < 0:
        return NUM
    q = x / sig
    return (math.ceil(q - 1e-12) if up else math.floor(q + 1e-12)) * sig


FUNCTIONS.update({
    "POWER": _num_fn(2, 2, _power),
    "EXP": _num_fn(1, 1, lambda x: NUM if x > 709 else math.exp(x)),
    "LN": _num_fn(1, 1, lambda x: NUM if x <= 0 else math.log(x)),
    "LOG": _num_fn(1, 2, _log),
    "LOG10": _num_fn(1, 1, lambda x: _log(x, 10.0)),
    "PI": _arity(0, 0, lambda: math.pi),
    "SIGN": _num_fn(1, 1, lambda x: float((x > 0) - (x < 0))),
    "ROUNDUP": _num_fn(1, 2, lambda x, d=0.0: _round_dir(x, d, True)),
    "ROUNDDOWN": _num_fn(1, 2, lambda x, d=0.0: _round_dir(x, d, False)),
    "TRUNC": _num_fn(1, 2, lambda x, d=0.0: _round_dir(x, d, False)),
    "CEILING": _num_fn(1, 2, lambda x, s=1.0: _to_multiple(x, s, True)),
    "FLOOR": _num_fn(1, 2, lambda x, s=1.0: _to_multiple(x, s, False)),
    "EVEN": _num_fn(1, 1, lambda x: math.copysign(math.ceil(abs(x) / 2) * 2, x)),
    "ODD": _num_fn(1, 1, lambda x: math.copysign(
        (lambda n: n if n % 2 else n + 1)(math.ceil(abs(x))), x)),
    "FACT": _num_fn(1, 1, lambda x: NUM if x < 0 or x > 170
                    else float(math.factorial(int(x)))),
    "DEGREES": _num_fn(1, 1, math.degrees),
    "RADIANS": _num_fn(1, 1, math.radians),
    "SIN": _num_fn(1, 1, math.sin),
    "COS": _num_fn(1, 1, math.cos),
    "TAN": _num_fn(1, 1, math.tan),
})


# ---- text ------------------------------------------------------------------

def _text_fn(lo, hi, fn):
    return _arity(lo, hi, fn)


def _left(t, n=1.0):
    n = _to_number(n)
    if isinstance(n, CellError):
        return n
    return VALUE if n < 0 else _to_text(t)[:int(n)]


def _right(t, n=1.0):
    n = _to_number(n)
    if isinstance(n, CellError):
        return n
    if n < 0:
        return VALUE
    t = _to_text(t)
    return t[len(t) - int(n):] if int(n) else ""


def _mid(t, start, n):
    nums = _nums(start, n)
    if isinstance(nums, CellError):
        return nums
    start, n = int(nums[0]), int(nums[1])
    if start < 1 or n < 0:
        return VALUE
    return _to_text(t)[start - 1:start - 1 + n]


def _substitute(t, old, new, instance=None):
    t, old, new = _to_text(t), _to_text(old), _to_text(new)
    if old == "":
        return t
    if instance is None:
        return t.replace(old, new)
    k = _to_number(instance)
    if isinstance(k, CellError):
        return k
    k = int(k)
    if k < 1:
        return VALUE
    idx = -1
    for _ in range(k):
        idx = t.find(old, idx + 1)
        if idx < 0:
            return t
    return t[:idx] + new + t[idx + len(old):]


def _find(case_sensitive):
    def fn(needle, hay, start=1.0):
        s = _to_number(start)
        if isinstance(s, CellError):
            return s
        needle, hay = _to_text(needle), _to_text(hay)
        if not case_sensitive:
            needle, hay = needle.lower(), hay.lower()
        if s < 1 or s > len(hay) + 1:
            return VALUE
        i = hay.find(needle, int(s) - 1)
        return VALUE if i < 0 else float(i + 1)
    return fn


def _value(t):
    if isinstance(t, float):
        return t
    s = _to_text(t).strip().replace(",", "")
    pct = s.endswith("%")
    s = s.rstrip("%").lstrip("$€£₱")
    try:
        n = float(s)
    except ValueError:
        return VALUE
    return n / 100 if pct else n


def _text(v, fmt):
    n = _to_number(v)
    if isinstance(n, CellError):
        return _to_text(v)
    out = format_number(n, _to_text(fmt))
    return _to_text(n) if out is None else out


def _proper(t):
    return re.sub(r"[A-Za-zÀ-ÿ]+", lambda m: m.group(0).capitalize(), _to_text(t))


def _rept(t, n):
    n = _to_number(n)
    if isinstance(n, CellError):
        return n
    return VALUE if n < 0 else _to_text(t) * int(n)


FUNCTIONS.update({
    "LEFT": _text_fn(1, 2, _left),
    "RIGHT": _text_fn(1, 2, _right),
    "MID": _text_fn(3, 3, _mid),
    "TRIM": _text_fn(1, 1, lambda t: " ".join(_to_text(t).split())),
    "PROPER": _text_fn(1, 1, _proper),
    "SUBSTITUTE": _text_fn(3, 4, _substitute),
    "FIND": _text_fn(2, 3, _find(True)),
    "SEARCH": _text_fn(2, 3, _find(False)),
    "REPT": _text_fn(2, 2, _rept),
    "EXACT": _text_fn(2, 2, lambda a, b: _to_text(a) == _to_text(b)),
    "VALUE": _text_fn(1, 1, _value),
    "TEXT": _text_fn(2, 2, _text),
    "CONCATENATE": FUNCTIONS["CONCAT"],
})


@register("TEXTJOIN")
def _textjoin(args):
    if len(args) < 3:
        return VALUE
    err = _first_error(args[0], args[1])
    if err:
        return err
    delim = _to_text(args[0])
    skip = _to_bool(args[1])
    if isinstance(skip, CellError):
        return skip
    parts = []
    for v in _flatten(args[2:]):
        if isinstance(v, CellError):
            return v
        t = _to_text(v)
        if t == "" and skip:
            continue
        parts.append(t)
    return delim.join(parts)


# ---- information and logic -------------------------------------------------

def _info(test):
    def fn(args):
        if len(args) != 1:
            return VALUE
        v = args[0]
        if isinstance(v, _Range):
            v = v[0] if len(v) == 1 else None
        return test(v)
    return fn


FUNCTIONS.update({
    "ISBLANK": _info(lambda v: v is None),
    "ISNUMBER": _info(lambda v: isinstance(v, float) and not isinstance(v, bool)),
    "ISTEXT": _info(lambda v: isinstance(v, str)),
    "ISLOGICAL": _info(lambda v: isinstance(v, bool)),
    "ISERROR": _info(lambda v: isinstance(v, CellError)),
    "ISNA": _info(lambda v: v == NA),
    "NA": _arity(0, 0, lambda: NA),
    "TRUE": _arity(0, 0, lambda: True),
    "FALSE": _arity(0, 0, lambda: False),
})


@register("XOR")
def _xor(args):
    values = []
    for v in _flatten(args):
        if isinstance(v, CellError):
            return v
        if v is None or (isinstance(v, str) and v.upper() not in ("TRUE", "FALSE")):
            continue
        values.append(_to_bool(v))
    return (sum(values) % 2 == 1) if values else VALUE


# ---- lookup ----------------------------------------------------------------

def _equal(a, b):
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return bool(_wildcard(b).match(a)) if any(c in b for c in "*?~") else a.lower() == b.lower()
    return _compare_key(a, b) == _compare_key(b, a)


def _same_kind(a, b):
    num = lambda v: isinstance(v, float) and not isinstance(v, bool)  # noqa: E731
    return (num(a) and num(b)) or (isinstance(a, str) and isinstance(b, str)) or (
        isinstance(a, bool) and isinstance(b, bool))


def _approx_index(values, target, descending=False):
    """Binary-search style: the last position whose value <= target (sorted data)."""
    best = None
    for i, v in enumerate(values):
        if v is None or not _same_kind(v, target):
            continue
        k, t = _compare_key(v, target), _compare_key(target, v)
        if (k <= t) if not descending else (k >= t):
            best = i
        else:
            break
    return best


def _match_index(values, target, mode):
    if mode == 0:
        return next((i for i, v in enumerate(values) if _equal(v, target)), None)
    return _approx_index(values, target, descending=mode < 0)


@register("MATCH")
def _match(args):
    if len(args) not in (2, 3):
        return VALUE
    target, rng = args[0], _as_range(args[1])
    if isinstance(target, CellError):
        return target
    mode = 1.0 if len(args) == 2 else _to_number(args[2])
    if isinstance(mode, CellError):
        return mode
    i = _match_index(list(rng), target, int(mode))
    return NA if i is None else float(i + 1)


def _lookup(vertical):
    def fn(args):
        if len(args) not in (3, 4):
            return VALUE
        target, table = args[0], _as_range(args[1])
        if isinstance(target, CellError):
            return target
        idx = _to_number(args[2])
        if isinstance(idx, CellError):
            return idx
        approx = True if len(args) == 3 else _to_bool(args[3])
        if isinstance(approx, CellError):
            return approx
        idx = int(idx)
        span = table.cols if vertical else table.rows
        if idx < 1:
            return VALUE
        if idx > span:
            return CellError("#REF!")
        n = table.rows if vertical else table.cols
        keys = [table.at(i, 0) if vertical else table.at(0, i) for i in range(n)]
        i = _match_index(keys, target, 1 if approx else 0)
        if i is None:
            return NA
        v = table.at(i, idx - 1) if vertical else table.at(idx - 1, i)
        return 0.0 if v is None else v
    return fn


FUNCTIONS["VLOOKUP"] = _lookup(True)
FUNCTIONS["HLOOKUP"] = _lookup(False)


@register("XLOOKUP")
def _xlookup(args):
    if len(args) not in (3, 4):
        return VALUE
    target, keys, results = args[0], _as_range(args[1]), _as_range(args[2])
    if isinstance(target, CellError):
        return target
    if len(keys) != len(results):
        return VALUE
    i = _match_index(list(keys), target, 0)
    if i is None:
        return args[3] if len(args) == 4 else NA
    v = results[i]
    return 0.0 if v is None else v


@register("INDEX")
def _index(args):
    if len(args) not in (2, 3):
        return VALUE
    rng = _as_range(args[0])
    nums = _nums(*args[1:])
    if isinstance(nums, CellError):
        return nums
    r = int(nums[0])
    c = int(nums[1]) if len(nums) == 2 else 1
    if rng.rows == 1 and len(nums) == 1:  # a single row: the index picks the column
        r, c = 1, r
    if r < 1 or c < 1 or r > rng.rows or c > rng.cols:
        return CellError("#REF!")
    v = rng.at(r - 1, c - 1)
    return 0.0 if v is None else v


@register("ROWS")
def _rows(args):
    return float(_as_range(args[0]).rows) if len(args) == 1 else VALUE


@register("COLUMNS")
def _columns(args):
    return float(_as_range(args[0]).cols) if len(args) == 1 else VALUE


# Keep _exactly imported for callers that extend this module.
__all__ = ["criteria", "register", "_exactly"]
