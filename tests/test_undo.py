from office.undo import Command, FunctionCommand, MacroCommand, UndoStack


class Append(Command):
    def __init__(self, target, item):
        self.target, self.item = target, item
        self.text = f"add {item}"

    def redo(self):
        self.target.append(self.item)

    def undo(self):
        self.target.pop()


class Typing(Command):
    """Merges with the next Typing on the same target, like keystrokes."""

    def __init__(self, box, before, after):
        self.box, self.before, self.after = box, before, after
        self.text = "typing"

    def redo(self):
        self.box["text"] = self.after

    def undo(self):
        self.box["text"] = self.before

    def merge_with(self, other):
        if isinstance(other, Typing) and other.box is self.box:
            self.after = other.after
            return True
        return False


def test_undo_redo_and_redo_tail_is_dropped():
    data, s = [], UndoStack()
    s.push(Append(data, 1))
    s.push(Append(data, 2))
    assert data == [1, 2]
    s.undo()
    assert data == [1]
    assert s.redo_text() == "add 2"
    s.push(Append(data, 3))  # new branch: "add 2" is gone
    assert not s.can_redo()
    s.undo(); s.undo()
    assert data == []
    assert not s.can_undo()
    s.undo()  # no-op
    s.redo(); s.redo()
    assert data == [1, 3]


def test_merge_and_clean_state():
    box, s = {"text": ""}, UndoStack()
    s.push(Typing(box, "", "h"))
    s.push(Typing(box, "h", "hi"))
    assert len(s) == 1
    s.set_clean()
    assert s.is_clean()
    s.push(Typing(box, "hi", "hi!"))  # doesn't merge across a save
    assert len(s) == 2 and not s.is_clean()
    s.undo()
    assert box["text"] == "hi" and s.is_clean()
    s.undo()
    assert box["text"] == ""


def test_macro_and_already_done_and_listeners():
    data, s, calls = [], UndoStack(), []
    s.subscribe(lambda: calls.append(1))
    s.push(MacroCommand("two", [Append(data, "a"), Append(data, "b")]))
    data.append("x")
    s.push(FunctionCommand("x", lambda: data.append("x"), data.pop), already_done=True)
    assert data == ["a", "b", "x"]
    s.undo(); s.undo()
    assert data == []
    assert len(calls) == 4


def test_limit():
    data, s = [], UndoStack(limit=3)
    for i in range(5):
        s.push(Append(data, i))
    assert len(s) == 3
    s.undo(); s.undo(); s.undo()
    assert data == [0, 1]
