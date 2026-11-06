"""The facade the GUI talks to: set(addr, raw), raw(addr), value(addr)."""
from dataclasses import dataclass

from .ast_nodes import references
from .errors import CIRC, REF, SYNTAX, CellError
from .evaluator import Evaluator
from .graph import DependencyGraph
from .lexer import FormulaSyntaxError
from .parser import parse
from .refs import parse_ref, to_addr

# Excel's limits. A reference past these (or to row 0) is #REF!.
MAX_ROWS = 1_048_576
MAX_COLS = 16_384


@dataclass
class Cell:
    raw: str
    ast: object = None  # None for literals
    value: object = None


def literal_value(raw: str):
    """A cell without '=' holds a number, TRUE/FALSE, or text."""
    if raw.upper() in ("TRUE", "FALSE"):
        return raw.upper() == "TRUE"
    try:
        return float(raw)
    except ValueError:
        return raw


def format_value(v) -> str:
    """How a value is shown in the grid: 480 not 480.0, errors as their code."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return f"{v:.10g}"
    return str(v)


class Sheet:
    def __init__(self, max_rows=MAX_ROWS, max_cols=MAX_COLS):
        self.max_rows = max_rows
        self.max_cols = max_cols
        self.cells: dict[tuple[int, int], Cell] = {}
        self.graph = DependencyGraph()
        self._evaluator = Evaluator(self._get)

    # ---- public API (addresses as "A1") -------------------------------

    def set(self, addr: str, raw) -> list[str]:
        """Set a cell's raw text. Returns the addresses whose values were recomputed."""
        return self.set_many({addr: raw})

    def set_many(self, updates: dict) -> list[str]:
        """Set several cells, then recalc once. Used when opening a file."""
        changed = []
        for addr, raw in updates.items():
            key = parse_ref(addr)
            self._store(key, "" if raw is None else str(raw))
            changed.append(key)
        return [to_addr(*k) for k in self._recalc(changed)]

    def raw(self, addr: str) -> str:
        cell = self.cells.get(parse_ref(addr))
        return cell.raw if cell else ""

    def value(self, addr: str):
        cell = self.cells.get(parse_ref(addr))
        return cell.value if cell else None

    def display(self, addr: str) -> str:
        return format_value(self.value(addr))

    def precedents(self, addr: str) -> list[str]:
        return [to_addr(*k) for k in sorted(self.graph.precedents_of(parse_ref(addr)))]

    def dependents(self, addr: str) -> list[str]:
        return [to_addr(*k) for k in sorted(self.graph.dependents_of(parse_ref(addr)))]

    def recalc_plan(self, addr: str) -> list[str]:
        """What would be recomputed, in order, if `addr` changed (excluding itself)."""
        key = parse_ref(addr)
        order, cyclic = self.graph.recalc_order(self.graph.affected([key]))
        return [to_addr(*k) for k in order + sorted(cyclic) if k != key]

    def cycles(self) -> list[list[str]]:
        return [sorted(to_addr(*k) for k in comp) for comp in self.graph.cycles()]

    def used_addresses(self) -> list[str]:
        return [to_addr(*k) for k in sorted(self.cells)]

    # ---- internals (keys as (row, col)) --------------------------------

    def _store(self, key, raw: str):
        if raw == "":
            self.cells.pop(key, None)
            self.graph.set_precedents(key, ())
            return
        if raw.startswith("="):
            try:
                ast = parse(raw[1:])
            except FormulaSyntaxError:
                self.cells[key] = Cell(raw, None, SYNTAX)
                self.graph.set_precedents(key, ())
                return
            refs = {k for k in references(ast) if self._in_bounds(k)}
            self.cells[key] = Cell(raw, ast)
            self.graph.set_precedents(key, refs)
        else:
            self.cells[key] = Cell(raw, None, literal_value(raw))
            self.graph.set_precedents(key, ())

    def _recalc(self, starts):
        order, cyclic = self.graph.recalc_order(self.graph.affected(starts))
        for key in cyclic:
            if key in self.cells:
                self.cells[key].value = CIRC
        for key in order:
            self._evaluate_cell(key)
        return order + sorted(cyclic)

    def _evaluate_cell(self, key):
        cell = self.cells.get(key)
        if cell is None or cell.ast is None:
            return  # empty or literal: nothing to compute
        cell.value = self._evaluator.evaluate(cell.ast)

    def _in_bounds(self, key) -> bool:
        r, c = key
        return 0 <= r < self.max_rows and 0 <= c < self.max_cols

    def _get(self, row, col):
        if not self._in_bounds((row, col)):
            return REF
        cell = self.cells.get((row, col))
        return cell.value if cell else None


__all__ = ["Sheet", "Cell", "CellError", "format_value"]
