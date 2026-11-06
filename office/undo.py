"""Undo/redo with the command pattern, shared by Sheets, Writer and Slides.

A Command knows how to apply itself (redo) and how to reverse itself (undo).
The UndoStack keeps a list of commands and an index: everything left of the
index has been applied. Pushing a new command throws away the redo tail.

Pure Python, no Qt, so it's tested directly in tests/test_undo.py.
"""


class Command:
    text = ""  # shown as "Undo <text>"

    def redo(self):
        raise NotImplementedError

    def undo(self):
        raise NotImplementedError

    def merge_with(self, other) -> bool:
        """Absorb `other` (pushed right after self) into self. Return True if merged.

        Used so typing "hello" into one slide text box is a single undo step.
        """
        return False


class FunctionCommand(Command):
    """A command built from two callables. Handy for one-off actions."""

    def __init__(self, text, redo, undo):
        self.text = text
        self._redo, self._undo = redo, undo

    def redo(self):
        self._redo()

    def undo(self):
        self._undo()


class MacroCommand(Command):
    """Several commands that undo and redo as one step."""

    def __init__(self, text, commands):
        self.text = text
        self.commands = list(commands)

    def redo(self):
        for c in self.commands:
            c.redo()

    def undo(self):
        for c in reversed(self.commands):
            c.undo()


class UndoStack:
    def __init__(self, limit=500):
        self.limit = limit
        self._commands: list[Command] = []
        self._index = 0
        self._clean_index = 0
        self._listeners = []

    # ---- observing --------------------------------------------------------

    def subscribe(self, fn):
        """fn() is called after every push, undo, redo or clear."""
        self._listeners.append(fn)

    def _notify(self):
        for fn in list(self._listeners):
            fn()

    # ---- the stack --------------------------------------------------------

    def push(self, command: Command, already_done=False):
        """Run `command` and record it. Pass already_done=True when the change
        has happened already (e.g. Qt's text editor applied it)."""
        if not already_done:
            command.redo()
        del self._commands[self._index:]
        if self._clean_index > self._index:
            self._clean_index = -1  # the saved state can't be reached any more
        top = self._commands[-1] if self._commands else None
        if top is not None and self._index != self._clean_index and top.merge_with(command):
            pass
        else:
            self._commands.append(command)
            if len(self._commands) > self.limit:
                self._commands.pop(0)
                self._clean_index -= 1
        self._index = len(self._commands)
        self._notify()

    def undo(self):
        if not self.can_undo():
            return
        self._index -= 1
        self._commands[self._index].undo()
        self._notify()

    def redo(self):
        if not self.can_redo():
            return
        self._commands[self._index].redo()
        self._index += 1
        self._notify()

    def can_undo(self):
        return self._index > 0

    def can_redo(self):
        return self._index < len(self._commands)

    def undo_text(self):
        return self._commands[self._index - 1].text if self.can_undo() else ""

    def redo_text(self):
        return self._commands[self._index].text if self.can_redo() else ""

    def clear(self):
        self._commands.clear()
        self._index = self._clean_index = 0
        self._notify()

    # ---- "has this been saved?" ------------------------------------------

    def set_clean(self):
        self._clean_index = self._index
        self._notify()

    def is_clean(self):
        return self._index == self._clean_index

    def __len__(self):
        return len(self._commands)
