import pytest

from office.sheets.engine.lexer import FormulaSyntaxError, tokenize


def kinds(text):
    return [(t.type, t.value) for t in tokenize(text)][:-1]  # drop EOF


def test_operators_and_numbers():
    assert kinds("1+2.5*3") == [
        ("NUMBER", 1.0), ("PLUS", "+"), ("NUMBER", 2.5), ("MUL", "*"), ("NUMBER", 3.0),
    ]
    assert kinds("1.5e3") == [("NUMBER", 1500.0)]
    assert kinds(".5") == [("NUMBER", 0.5)]


def test_cell_vs_ident():
    assert kinds("SUM(a1:B2)") == [
        ("IDENT", "SUM"), ("LPAREN", "("), ("CELL", "A1"), ("COLON", ":"),
        ("CELL", "B2"), ("RPAREN", ")"),
    ]
    assert kinds("$A$1") == [("CELL", "$A$1")]
    # Letters+digits followed by '(' is a function name, not a cell.
    assert kinds("LOG10(1)")[0] == ("IDENT", "LOG10")


def test_strings():
    assert kinds('"hi"') == [("STRING", "hi")]
    assert kinds('"say ""hi"""') == [("STRING", 'say "hi"')]


def test_whitespace_ignored():
    assert kinds("  A1 ^ 2 ") == [("CELL", "A1"), ("POW", "^"), ("NUMBER", 2.0)]


@pytest.mark.parametrize("bad", ['"open', "1 # 2", "A1 @ B1", "#OOPS"])
def test_errors(bad):
    with pytest.raises(FormulaSyntaxError):
        tokenize(bad)
