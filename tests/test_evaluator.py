import pytest

from office.sheets.engine.errors import DIV0, NAME, NUM, VALUE
from office.sheets.engine.evaluator import Evaluator
from office.sheets.engine.parser import parse
from office.sheets.engine.refs import parse_ref


def run(formula, cells=None):
    data = {parse_ref(k): v for k, v in (cells or {}).items()}
    return Evaluator(lambda r, c: data.get((r, c))).evaluate(parse(formula))


@pytest.mark.parametrize("formula,expected", [
    ("1+2*3", 7), ("(1+2)*3", 9), ("2^3^2", 512), ("-2^2", 4), ("2^-1", 0.5),
    ("10/4", 2.5), ("--3", 3), ("+3", 3),
])
def test_arithmetic(formula, expected):
    assert run(formula) == expected


def test_functions_with_ranges():
    cells = {"A1": 1.0, "A2": None, "A3": 5.0, "A4": "text"}
    assert run("SUM(A1:A4)", cells) == 6
    assert run("AVERAGE(A1:A4)", cells) == 3
    assert run("MIN(A1:A4)", cells) == 1
    assert run("MAX(A1:A4, 10)", cells) == 10
    assert run("COUNT(A1:A4)", cells) == 2
    assert run("sum(1,2,3)") == 6


def test_empty_is_zero_and_numeric_text_coerces():
    assert run("A1+1") == 1
    assert run("A1", {}) == 0
    assert run("A1*2", {"A1": "3"}) == 6


def test_errors_are_values():
    assert run("1/0") == DIV0
    assert run("FOO(1)") == NAME
    assert run('"a"+1') == VALUE
    assert run("A1:A2") == VALUE
    assert run("AVERAGE(A1:A2)") == DIV0
    assert run("(-8)^0.5") == NUM
    assert run("0^-1") == DIV0


def test_errors_propagate():
    assert run("A1+1", {"A1": DIV0}) == DIV0
    assert run("SUM(A1:A2)", {"A1": NAME}) == NAME
    assert run("-A1", {"A1": DIV0}) == DIV0
    # COUNT skips errors, like Excel.
    assert run("COUNT(A1:A2)", {"A1": DIV0, "A2": 1.0}) == 1
