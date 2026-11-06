from office.sheets.engine.graph import DependencyGraph


def test_edges_are_replaced():
    g = DependencyGraph()
    g.set_precedents("B", {"A"})
    g.set_precedents("B", {"C"})
    assert g.dependents_of("A") == set()
    assert g.dependents_of("C") == {"B"}


def test_topological_order():
    g = DependencyGraph()
    g.set_precedents("B", {"A"})
    g.set_precedents("C", {"A", "B"})
    g.set_precedents("D", {"C"})
    order, cyclic = g.recalc_order(g.affected(["A"]))
    assert order == ["A", "B", "C", "D"]
    assert cyclic == set()


def test_cycle_detection_separates_cycle_from_downstream():
    g = DependencyGraph()
    g.set_precedents("A", {"B"})
    g.set_precedents("B", {"A"})
    g.set_precedents("C", {"B"})  # reads the loop but isn't in it
    order, cyclic = g.recalc_order(g.affected(["A"]))
    assert cyclic == {"A", "B"}
    assert order == ["C"]


def test_self_loop_and_path_between_two_cycles():
    g = DependencyGraph()
    g.set_precedents("S", {"S"})
    g.set_precedents("A", {"B"}); g.set_precedents("B", {"A"})
    g.set_precedents("M", {"A"})  # between two cycles, on neither
    g.set_precedents("X", {"M", "Y"}); g.set_precedents("Y", {"X"})
    assert g.cyclic_cells() == {"S", "A", "B", "X", "Y"}
