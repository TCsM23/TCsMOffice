from office.sheets.engine import Sheet
from office.sheets.engine.errors import CIRC, DIV0, NAME, REF, SYNTAX


def test_literals():
    s = Sheet()
    s.set("A1", "5")
    s.set("A2", "hello")
    assert s.value("A1") == 5
    assert s.value("A2") == "hello"
    assert s.value("A3") is None
    assert s.raw("A1") == "5"


def test_recalc_on_change():
    s = Sheet()
    s.set("A1", "5")
    s.set("B1", "=A1*2")
    assert s.value("B1") == 10
    s.set("A1", "7")
    assert s.value("B1") == 14


def test_sum_with_empty_cell():
    s = Sheet()
    s.set("A1", "1")
    s.set("A3", "3")
    s.set("B1", "=SUM(A1:A3)")
    assert s.value("B1") == 4


def test_error_values_propagate():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("A2", "=A1+1")
    s.set("A3", "=FOO(1)")
    s.set("A4", "=1+")
    s.set("A5", "=A0+1")
    assert s.value("A1") == DIV0
    assert s.value("A2") == DIV0
    assert s.value("A3") == NAME
    assert s.value("A4") == SYNTAX
    assert s.value("A5") == REF


def test_self_reference_is_circular():
    s = Sheet()
    s.set("A1", "=A1")
    assert s.value("A1") == CIRC


def test_two_cell_loop_and_breaking_it():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    s.set("C1", "=A1*10")  # downstream of the loop
    assert s.value("A1") == CIRC
    assert s.value("B1") == CIRC
    assert s.value("C1") == CIRC
    assert s.cycles() == [["A1", "B1"]]
    # Break the loop: everything that was #CIRC! must come back.
    s.set("B1", "5")
    assert s.value("B1") == 5
    assert s.value("A1") == 6
    assert s.value("C1") == 60
    assert s.cycles() == []


def test_clearing_a_cell():
    s = Sheet()
    s.set("A1", "3")
    s.set("B1", "=A1")
    s.set("A1", "")
    assert s.value("B1") == 0
    assert "A1" not in s.used_addresses()


def test_only_dependents_are_recalculated(monkeypatch):
    """The proof that the dependency graph works: count evaluator calls."""
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=A1*10")      # depends on A1
    s.set("C1", "=B1+1")       # depends on A1 through B1
    s.set("B2", "=A2*10")      # unrelated to A1
    s.set("C2", "=SUM(B2:B3)")  # unrelated to A1

    evaluated = []
    original = s._evaluate_cell

    def spy(key):
        evaluated.append(key)
        original(key)

    monkeypatch.setattr(s, "_evaluate_cell", spy)
    changed = s.set("A1", "2")

    assert changed == ["A1", "B1", "C1"]
    assert [k for k in evaluated if s.cells[k].ast is not None] == [(0, 1), (0, 2)]
    assert s.value("C1") == 21
    assert s.value("C2") == 20


def test_diamond_evaluates_each_cell_once(monkeypatch):
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1+1")
    s.set("B2", "=A1+2")
    s.set("C1", "=B1+B2")
    calls = []
    original = s._evaluate_cell
    monkeypatch.setattr(s, "_evaluate_cell", lambda k: (calls.append(k), original(k)))
    s.set("A1", "10")
    assert sorted(calls) == sorted([(0, 0), (0, 1), (1, 1), (0, 2)])
    assert s.value("C1") == 23


def test_recalc_plan_for_side_panel():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1")
    s.set("C1", "=B1+A1")
    assert s.precedents("C1") == ["A1", "B1"]
    assert s.dependents("A1") == ["B1", "C1"]
    assert s.recalc_plan("A1") == ["B1", "C1"]
    assert s.recalc_plan("C1") == []


def test_mini_spreadsheet_from_the_mockup():
    s = Sheet()
    s.set_many({
        "B2": "4", "C2": "120", "D2": "=B2*C2",
        "B3": "2", "C3": "350", "D3": "=B3*C3",
        "B4": "10", "C4": "15", "D4": "=B4*C4",
        "B5": "12", "C5": "8", "D5": "=B5*C5",
        "D6": "=SUM(D2:D5)", "D7": "=D6*0.12", "D8": "=D6+D7",
        "B10": "=C10", "C10": "=B10",
    })
    assert s.display("D6") == "1426"
    assert s.display("D7") == "171.12"
    assert s.display("D8") == "1597.12"
    assert s.display("B10") == "#CIRC!"
