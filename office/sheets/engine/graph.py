"""Dependency graph: who reads whom, recalc order, and cycle detection.

Two maps are kept in sync:
    precedents[cell] = cells this cell's formula reads
    dependents[cell] = cells whose formulas read this cell
"""
from collections import deque


class DependencyGraph:
    def __init__(self):
        self.precedents: dict = {}
        self.dependents: dict = {}

    def set_precedents(self, cell, refs):
        """Replace the edges coming into `cell`."""
        for old in self.precedents.pop(cell, ()):
            deps = self.dependents.get(old)
            if deps is not None:
                deps.discard(cell)
                if not deps:
                    del self.dependents[old]
        refs = set(refs)
        if refs:
            self.precedents[cell] = refs
            for ref in refs:
                self.dependents.setdefault(ref, set()).add(cell)

    def precedents_of(self, cell) -> set:
        return set(self.precedents.get(cell, ()))

    def dependents_of(self, cell) -> set:
        return set(self.dependents.get(cell, ()))

    def affected(self, starts) -> set:
        """The start cells plus every transitive dependent (BFS)."""
        seen = set(starts)
        queue = deque(seen)
        while queue:
            cell = queue.popleft()
            for dep in self.dependents.get(cell, ()):
                if dep not in seen:
                    seen.add(dep)
                    queue.append(dep)
        return seen

    def recalc_order(self, cells):
        """Topologically sort `cells` with Kahn's algorithm.

        Only edges between cells in the subset count. Returns (order, cyclic):
        `order` is safe to evaluate front to back, and `cyclic` holds the cells
        that sit on a cycle. Cells that merely depend on a cycle stay in `order`
        (after it) and pick up #CIRC! through normal error propagation.
        """
        cells = set(cells)
        order = self._kahn(cells)
        leftover = cells - set(order)
        if not leftover:
            return order, set()
        cyclic = self.cyclic_cells(leftover)
        # With the cycle members removed, what's left is acyclic again.
        order += self._kahn(leftover - cyclic)
        return order, cyclic

    def _kahn(self, cells):
        indegree = {c: 0 for c in cells}
        for c in cells:
            for p in self.precedents.get(c, ()):
                if p in cells:
                    indegree[c] += 1
        queue = deque(sorted(c for c, d in indegree.items() if d == 0))
        order = []
        while queue:
            c = queue.popleft()
            order.append(c)
            for dep in sorted(self.dependents.get(c, ())):
                if dep in indegree:
                    indegree[dep] -= 1
                    if indegree[dep] == 0:
                        queue.append(dep)
        return order

    def cycles(self, cells=None) -> list[set]:
        """Strongly connected components that form a cycle (Tarjan, iterative)."""
        cells = set(self.precedents) if cells is None else set(cells)
        index, low, on_stack = {}, {}, set()
        stack, result, counter = [], [], 0

        def neighbours(c):
            return sorted(d for d in self.dependents.get(c, ()) if d in cells)

        for root in sorted(cells):
            if root in index:
                continue
            work = [(root, iter(neighbours(root)))]
            index[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on_stack.add(root)
            while work:
                node, it = work[-1]
                advanced = False
                for nxt in it:
                    if nxt not in index:
                        index[nxt] = low[nxt] = counter
                        counter += 1
                        stack.append(nxt)
                        on_stack.add(nxt)
                        work.append((nxt, iter(neighbours(nxt))))
                        advanced = True
                        break
                    if nxt in on_stack:
                        low[node] = min(low[node], index[nxt])
                if advanced:
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = set()
                    while True:
                        c = stack.pop()
                        on_stack.discard(c)
                        component.add(c)
                        if c == node:
                            break
                    if len(component) > 1 or node in self.dependents.get(node, ()):
                        result.append(component)
        return result

    def cyclic_cells(self, cells=None) -> set:
        out = set()
        for comp in self.cycles(cells):
            out |= comp
        return out
