"""Undoable edits for Sheets. Every change to the grid goes through one of these."""
from ..undo import Command


class SetCellsCommand(Command):
    """Set several cells at once. changes = {addr: (old_raw, new_raw)}."""

    def __init__(self, model, changes: dict, text: str):
        self.model = model
        self.changes = changes
        self.text = text

    def redo(self):
        self.model.apply({a: new for a, (_old, new) in self.changes.items()})

    def undo(self):
        self.model.apply({a: old for a, (old, _new) in self.changes.items()})


class SetFormatsCommand(Command):
    """Change cell formats. changes = {(row, col): (old_format, new_format)};
    None means the default format."""

    def __init__(self, model, changes: dict, text: str):
        self.model = model
        self.changes = changes
        self.text = text

    def redo(self):
        self.model.apply_formats({k: new for k, (_old, new) in self.changes.items()})

    def undo(self):
        self.model.apply_formats({k: old for k, (old, _new) in self.changes.items()})
