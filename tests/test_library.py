"""The wider function library: lookups, conditional sums, statistics, text."""
import pytest

from office.sheets.engine import Sheet
from office.sheets.engine.errors import NA, NUM, REF, VALUE
from office.sheets.engine.evaluator import Evaluator
from office.sheets.engine.library import criteria
from office.sheets.engine.numfmt import format_number
from office.sheets.engine.parser import parse
from office.sheets.engine.refs import parse_ref

TABLE = {
    "A1": "apple", "B1": 3.0, "C1": "red",
    "A2": "banana", "B2": 5.0, "C2": "yellow",
    "A3": "cherry", "B3": 7.0, "C3": "red",
    "A4": "apple", "B4": 1.0, "C4": "green",
}


def run(formula, cells=TABLE):
    data = {parse_ref(k): v for k, v in (cells or {}).items()}
    return Evaluator(lambda r, c: data.get((r, c))).evaluate(parse(formula))


@pytest.mark.parametrize("formula,expected", [
    ('VLOOKUP("banana", A1:C4, 2, FALSE)', 5),
    ('VLOOKUP("cherry", A1:C4, 3, FALSE)', "red"),
    ("VLOOKUP(6, B1:B3, 1)", 5),             # approximate: largest <= 6 in sorted data
    ('HLOOKUP(5, B1:B4, 1, FALSE)', NA),     # HLOOKUP searches the first row only
    ('INDEX(A1:C4, 3, 2)', 7), ('INDEX(A1:A4, 2)', "banana"),
    ('MATCH("cherry", A1:A4, 0)', 3), ('MATCH("zzz", A1:A4, 0)', NA),
    ('MATCH("ch*", A1:A4, 0)', 3),
    ('XLOOKUP("apple", A1:A4, B1:B4)', 3), ('XLOOKUP("kiwi", A1:A4, B1:B4, "none")', "none"),
    ('SUMIF(A1:A4, "apple", B1:B4)', 4), ('SUMIF(B1:B4, ">4")', 12),
    ('COUNTIF(C1:C4, "red")', 2), ('COUNTIF(B1:B4, "<>5")', 3),
    ('AVERAGEIF(A1:A4, "apple", B1:B4)', 2),
    ('SUMIFS(B1:B4, A1:A4, "apple", C1:C4, "green")', 1),
    ('COUNTIFS(C1:C4, "red", B1:B4, ">=7")', 1),
    ("SUMPRODUCT(B1:B4, B1:B4)", 84), ("COUNTBLANK(A1:A6)", 2),
    ("MEDIAN(B1:B4)", 4), ("LARGE(B1:B4, 2)", 5), ("SMALL(B1:B4, 1)", 1),
    ("RANK(5, B1:B4)", 2), ("STDEVP(2, 4, 4, 4, 5, 5, 7, 9)", 2), ("LARGE(B1:B4, 9)", NUM),
    ("ROWS(A1:C4)", 4), ("COLUMNS(A1:C4)", 3),
])
def test_lookups_and_conditionals(formula, expected):
    assert run(formula) == expected


@pytest.mark.parametrize("formula,expected", [
    ('LEFT("Gothic", 3)', "Got"), ('RIGHT("Baroque", 3)', "que"), ('MID("crimson", 2, 3)', "rim"),
    ('TRIM("  too   many  ")', "too many"), ('PROPER("gilt and parchment")', "Gilt And Parchment"),
    ('SUBSTITUTE("a-b-c", "-", "+")', "a+b+c"), ('SUBSTITUTE("a-b-c", "-", "+", 2)', "a-b+c"),
    ('FIND("o", "Gothic")', 2), ('FIND("O", "Gothic")', VALUE), ('SEARCH("O", "Gothic")', 2),
    ('REPT("❦", 3)', "❦❦❦"), ('EXACT("a", "A")', False), ('VALUE("1,234.5")', 1234.5),
    ('VALUE("12%")', 0.12), ('TEXT(0.256, "0.0%")', "25.6%"), ('TEXT(1234.5, "#,##0.00")', "1,234.50"),
    ('TEXTJOIN("-", TRUE, "a", "", "b")', "a-b"), ('CONCATENATE("x", 1)', "x1"),
    ("ROUNDUP(2.01, 0)", 3), ("ROUNDDOWN(-2.99, 0)", -2), ("CEILING(4.1, 0.5)", 4.5),
    ("FLOOR(4.9, 2)", 4), ("POWER(2, 10)", 1024), ("LOG10(1000)", 3), ("LOG(8, 2)", 3),
    ("LN(1)", 0), ("SIGN(-4)", -1), ("FACT(5)", 120), ("LOG(0)", NUM), ("EVEN(3)", 4), ("ODD(4)", 5),
    ("ISBLANK(Z9)", True), ("ISNUMBER(B1)", True), ("ISTEXT(B1)", False), ("ISERROR(1/0)", True),
    ("ISNA(NA())", True), ("XOR(TRUE, TRUE)", False),
    ('IFERROR(1/0, "safe")', "safe"), ("IFERROR(5, 0)", 5), ('IFNA(NA(), "n/a")', "n/a"),
    ('IFS(B1>5, "big", B1>2, "mid", TRUE, "small")', "mid"), ('IFS(FALSE, 1)', NA),
    ('CHOOSE(2, "a", "b", "c")', "b"), ('CHOOSE(4, "a")', VALUE),
])
def test_text_maths_and_logic(formula, expected):
    result = run(formula)
    if isinstance(expected, float) or (isinstance(expected, int) and not isinstance(expected, bool)):
        assert result == pytest.approx(expected)
    else:
        assert result == expected


def test_iferror_is_lazy():
    calls = []

    def get(r, c):
        calls.append((r, c))
        return 1.0
    Evaluator(get).evaluate(parse("IFERROR(A1, B1)"))
    assert calls == [(0, 0)]  # B1 is never read when A1 is fine


def test_vlookup_past_the_table_is_ref():
    assert run('VLOOKUP("apple", A1:B4, 3, FALSE)') == REF


def test_lookups_recalculate_through_the_graph():
    s = Sheet()
    s.set_many({"A1": "x", "B1": "10", "A2": "y", "B2": "20",
                "D1": '=VLOOKUP("y", A1:B2, 2, FALSE)', "D2": "=SUMIF(A1:A2,\"x\",B1:B2)"})
    assert s.value("D1") == 20 and s.value("D2") == 10
    s.set("B2", "25")
    assert s.value("D1") == 25
    assert sorted(s.precedents("D1")) == ["A1", "A2", "B1", "B2"]


@pytest.mark.parametrize("crit,value,ok", [
    (">5", 6.0, True), (">5", 5.0, False), ("<>x", "y", True), ("<>x", "X", False),
    ("ap*", "Apple", True), ("?at", "cat", True), ("?at", "chat", False), ("", None, True),
    ("<>", None, False), (5.0, 5.0, True), ("5", "5", True), (">=b", "c", True),
])
def test_criteria(crit, value, ok):
    assert criteria(crit)(value) is ok


@pytest.mark.parametrize("value,fmt,expected", [
    (1234.5, "General", None), (1234.5, "0", "1235"), (1234.5, "0.00", "1234.50"),
    (1234567.891, "#,##0.00", "1,234,567.89"), (0.125, "0%", "13%"), (0.125, "0.00%", "12.50%"),
    (1234.5, '"€"#,##0.00', "€1,234.50"), (-1234.5, '"₱"#,##0.00', "-₱1,234.50"),
    (1234.5, "0.00E+00", "1.23E+03"), (2.5, "0", "3"), (5, "mystery", None),
])
def test_number_formats(value, fmt, expected):
    assert format_number(value, fmt) == expected
