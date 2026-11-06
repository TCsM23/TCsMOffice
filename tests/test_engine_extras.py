import pytest

from office.sheets.engine import Sheet
from office.sheets.engine.errors import DIV0, NAME, REF, VALUE
from office.sheets.engine.evaluator import Evaluator
from office.sheets.engine.parser import parse
from office.sheets.engine.refs import parse_ref
from office.sheets.engine.shift import shift_formula


def run(formula, cells=None):
    data = {parse_ref(k): v for k, v in (cells or {}).items()}
    return Evaluator(lambda r, c: data.get((r, c))).evaluate(parse(formula))


@pytest.mark.parametrize("formula,expected", [
    ("1<2", True), ("2<=2", True), ("3<>3", False), ('"abc"="ABC"', True),
    ('1<"a"', True), ("TRUE>1", True), ("1+1=2", True),
    ('"a"&"b"', "ab"), ('1&2', "12"), ('"x"&1+2', "x3"), ("TRUE&\"\"", "TRUE"),
    ("IF(1>0, \"yes\", \"no\")", "yes"), ("IF(0, 1)", False),
    ("ROUND(2.5, 0)", 3), ("ROUND(-2.5, 0)", -3), ("ROUND(3.14159, 2)", 3.14),
    ("ABS(-4)", 4), ("SQRT(16)", 4), ("MOD(-7, 3)", 2), ("INT(-1.5)", -2),
    ("PRODUCT(2, 3, 4)", 24), ("AND(TRUE, 1)", True), ("OR(FALSE, 0)", False),
    ("NOT(FALSE)", True), ('CONCAT("a", 1, TRUE)', "a1TRUE"), ('LEN("four")', 4),
    ('UPPER("abc")', "ABC"), ('LOWER("ABC")', "abc"),
])
def test_new_operators_and_functions(formula, expected):
    assert run(formula) == expected


def test_if_is_lazy_and_errors_still_propagate():
    assert run("IF(A1=0, 0, 1/A1)") == 0
    assert run("IF(1/0, 1, 2)") == DIV0
    assert run('IF("x", 1, 2)') == VALUE
    assert run("IF(1)") == VALUE
    assert run("FOO") == NAME
    assert run("#REF!+1") == REF


def test_ranges_with_new_functions():
    cells = {"A1": 1.0, "A2": "t", "A3": True, "A4": None}
    assert run("COUNTA(A1:A4)", cells) == 3
    assert run("CONCAT(A1:A3)", cells) == "1tTRUE"
    assert run("AND(A1:A4)", cells) is True


def test_booleans_in_cells():
    s = Sheet()
    s.set("A1", "true")
    s.set("A2", "=A1+1")
    s.set("A3", "=A2>1")
    assert s.value("A1") is True
    assert s.value("A2") == 2
    assert s.display("A3") == "TRUE"


@pytest.mark.parametrize("raw,drow,dcol,expected", [
    ("=A1+B2", 1, 0, "=A2+B3"),
    ("=$A$1+A$1+$A1", 2, 2, "=$A$1+C$1+$A3"),
    ("=SUM(A1:A3)*2", 0, 1, "=SUM(B1:B3)*2"),
    ("=A1", -1, 0, "=#REF!"),
    ('="A1"&A1', 1, 0, '="A1"&A2'),
    ("plain text", 5, 5, "plain text"),
    ("=1+", 1, 1, "=1+"),
])
def test_shift_formula(raw, drow, dcol, expected):
    assert shift_formula(raw, drow, dcol) == expected


def test_shifted_ref_error_evaluates():
    s = Sheet()
    s.set("A1", shift_formula("=A1+1", -1, 0))
    assert s.value("A1") == REF
