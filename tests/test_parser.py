import pytest

from office.sheets.engine.ast_nodes import (
    BinOp, Call, CellRef, Number, RangeRef, UnaryOp, references,
)
from office.sheets.engine.lexer import FormulaSyntaxError
from office.sheets.engine.parser import parse


def test_precedence():
    assert parse("1+2*3") == BinOp("+", Number(1), BinOp("*", Number(2), Number(3)))


def test_power_is_right_associative():
    assert parse("2^3^2") == BinOp("^", Number(2), BinOp("^", Number(3), Number(2)))


def test_unary_minus_binds_tighter_than_power():
    # Design decision, pinned: =-2^2 is (-2)^2 like Excel, not -(2^2) like Python.
    assert parse("-2^2") == BinOp("^", UnaryOp("-", Number(2)), Number(2))


def test_ranges_and_calls():
    tree = parse("SUM(A1:A3, B1)")
    assert tree == Call("SUM", (RangeRef(CellRef(0, 0), CellRef(2, 0)), CellRef(0, 1)))
    assert references(tree) == {(0, 0), (1, 0), (2, 0), (0, 1)}
    assert parse("NOW()") == Call("NOW", ())


@pytest.mark.parametrize("bad", ["", "1+", "(1", "SUM(1,)", "A1:", "1 2", "SUM 1"])
def test_syntax_errors(bad):
    with pytest.raises(FormulaSyntaxError):
        parse(bad)
