"""Undoable edits for Slides. Each one calls on_change() so the view redraws."""
from ..undo import Command


class _SlidesCommand(Command):
    def __init__(self, on_change):
        self.on_change = on_change or (lambda: None)


class AddSlideCommand(_SlidesCommand):
    def __init__(self, pres, index, slide, on_change=None, text="New slide"):
        super().__init__(on_change)
        self.pres, self.index, self.slide, self.text = pres, index, slide, text

    def redo(self):
        self.pres.slides.insert(self.index, self.slide)
        self.on_change()

    def undo(self):
        self.pres.slides.remove(self.slide)
        self.on_change()


class DeleteSlideCommand(_SlidesCommand):
    text = "Delete slide"

    def __init__(self, pres, index, on_change=None):
        super().__init__(on_change)
        self.pres, self.index = pres, index
        self.slide = pres.slides[index]

    def redo(self):
        self.pres.slides.remove(self.slide)
        self.on_change()

    def undo(self):
        self.pres.slides.insert(self.index, self.slide)
        self.on_change()


class MoveSlideCommand(_SlidesCommand):
    text = "Move slide"

    def __init__(self, pres, src, dst, on_change=None):
        super().__init__(on_change)
        self.pres, self.src, self.dst = pres, src, dst

    def _move(self, a, b):
        slide = self.pres.slides.pop(a)
        self.pres.slides.insert(b, slide)
        self.on_change()

    def redo(self):
        self._move(self.src, self.dst)

    def undo(self):
        self._move(self.dst, self.src)


class AddShapeCommand(_SlidesCommand):
    def __init__(self, slide, shape, on_change=None, text="Insert shape"):
        super().__init__(on_change)
        self.slide, self.shape, self.text = slide, shape, text

    def redo(self):
        self.slide.shapes.append(self.shape)
        self.on_change()

    def undo(self):
        self.slide.shapes.remove(self.shape)
        self.on_change()


class DeleteShapesCommand(_SlidesCommand):
    text = "Delete"

    def __init__(self, slide, shapes, on_change=None):
        super().__init__(on_change)
        self.slide = slide
        # Remember positions so undo puts them back at the same depth.
        self.entries = sorted((slide.shapes.index(s), s) for s in shapes)

    def redo(self):
        for _i, s in self.entries:
            self.slide.shapes.remove(s)
        self.on_change()

    def undo(self):
        for i, s in self.entries:
            self.slide.shapes.insert(i, s)
        self.on_change()


class ReorderShapeCommand(_SlidesCommand):
    """Bring to front / send to back."""

    def __init__(self, slide, shape, to_front, on_change=None):
        super().__init__(on_change)
        self.slide, self.shape, self.to_front = slide, shape, to_front
        self.old_index = slide.shapes.index(shape)
        self.text = "Bring to front" if to_front else "Send to back"

    def redo(self):
        self.slide.shapes.remove(self.shape)
        if self.to_front:
            self.slide.shapes.append(self.shape)
        else:
            self.slide.shapes.insert(0, self.shape)
        self.on_change()

    def undo(self):
        self.slide.shapes.remove(self.shape)
        self.slide.shapes.insert(self.old_index, self.shape)
        self.on_change()


class SetAttrsCommand(_SlidesCommand):
    """Change attributes on objects: [(obj, name, old, new), ...].

    Works for shapes (x, y, text...), their TextStyle (size, color...) and
    slides (background, notes). Commands with the same merge_key merge, so
    nudging a shape with the arrow keys is one undo step.
    """

    def __init__(self, changes, text, on_change=None, merge_key=None):
        super().__init__(on_change)
        self.changes = list(changes)
        self.text = text
        self.merge_key = merge_key

    def redo(self):
        for obj, name, _old, new in self.changes:
            setattr(obj, name, new)
        self.on_change()

    def undo(self):
        for obj, name, old, _new in reversed(self.changes):
            setattr(obj, name, old)
        self.on_change()

    def merge_with(self, other):
        if (self.merge_key is None or not isinstance(other, SetAttrsCommand)
                or other.merge_key != self.merge_key):
            return False
        mine = {(id(o), n): i for i, (o, n, _a, _b) in enumerate(self.changes)}
        for obj, name, old, new in other.changes:
            i = mine.get((id(obj), name))
            if i is None:
                self.changes.append((obj, name, old, new))
            else:
                o, n, first_old, _ = self.changes[i]
                self.changes[i] = (o, n, first_old, new)
        return True


def set_attrs(objs_and_values, text, on_change=None, merge_key=None):
    """Build a SetAttrsCommand from [(obj, name, new_value), ...], skipping no-ops."""
    changes = [(o, n, getattr(o, n), v) for o, n, v in objs_and_values if getattr(o, n) != v]
    return SetAttrsCommand(changes, text, on_change, merge_key) if changes else None
