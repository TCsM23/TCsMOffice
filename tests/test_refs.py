import pytest

from office.sheets.engine.refs import col_to_index, index_to_col, parse_ref, to_addr


@pytest.mark.parametrize("letters,index", [
    ("A", 0), ("Z", 25), ("AA", 26), ("AZ", 51), ("BA", 52), ("ZZ", 701), ("AAA", 702),
])
def test_columns_round_trip(letters, index):
    assert col_to_index(letters) == index
    assert index_to_col(index) == letters


def test_parse_and_format():
    assert parse_ref("A1") == (0, 0)
    assert parse_ref("Z1") == (0, 25)
    assert parse_ref("AA1") == (0, 26)
    assert parse_ref("b3") == (2, 1)
    assert parse_ref("$C$4") == (3, 2)
    assert to_addr(2, 1) == "B3"


@pytest.mark.parametrize("bad", ["", "1A", "A", "A0", "A-1", "A1B"])
def test_bad_refs(bad):
    with pytest.raises(ValueError):
        parse_ref(bad)
