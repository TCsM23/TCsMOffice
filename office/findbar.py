"""A find-and-replace bar shared by Writer, Sheets and Slides.

The bar knows nothing about documents. It calls three methods on its target:

    find(text, forward, match_case, whole_word) -> bool
    replace(text, new, match_case, whole_word) -> bool   # the current match
    replace_all(text, new, match_case, whole_word) -> int

Replace all is always one undo step, because each target wraps it in a
single command.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton,
)


class FindBar(QFrame):
    def __init__(self, target, parent=None, whole_word_label="Whole word"):
        super().__init__(parent)
        self.target = target
        self.setObjectName("findBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 5, 14, 5)
        lay.setSpacing(6)
        title = QLabel("FIND")
        title.setObjectName("eyebrow")
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find")
        self.find_edit.setClearButtonEnabled(True)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Replace with")
        self.case = QCheckBox("Match case")
        self.whole = QCheckBox(whole_word_label)
        prev_btn = QToolButton()
        prev_btn.setText("▲")
        prev_btn.setToolTip("Previous match (Shift+Enter)")
        next_btn = QToolButton()
        next_btn.setText("▼")
        next_btn.setToolTip("Next match (Enter)")
        self.replace_btn = QPushButton("Replace")
        self.replace_all_btn = QPushButton("Replace all")
        self.status = QLabel()
        self.status.setObjectName("muted")
        close = QToolButton()
        close.setText("✕")
        close.setToolTip("Close (Esc)")
        for w in (title, self.find_edit, prev_btn, next_btn, self.replace_edit,
                  self.replace_btn, self.replace_all_btn, self.case, self.whole):
            lay.addWidget(w)
        lay.addWidget(self.status, 1)
        lay.addWidget(close)
        self.find_edit.setMinimumWidth(180)
        self.replace_edit.setMinimumWidth(160)

        self.find_edit.returnPressed.connect(lambda: self.find(True))
        self.replace_edit.returnPressed.connect(self.replace)
        prev_btn.clicked.connect(lambda: self.find(False))
        next_btn.clicked.connect(lambda: self.find(True))
        self.replace_btn.clicked.connect(self.replace)
        self.replace_all_btn.clicked.connect(self.replace_all)
        close.clicked.connect(self.close_bar)
        self.find_edit.textChanged.connect(lambda _t: self.status.clear())
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close_bar,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Shift+Return"), self.find_edit, lambda: self.find(False),
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.hide()

    def _opts(self):
        return self.case.isChecked(), self.whole.isChecked()

    def open_bar(self, replace=False, text=""):
        self.show()
        if text:
            self.find_edit.setText(text)
        (self.replace_edit if replace and self.find_edit.text() else self.find_edit).setFocus()
        self.find_edit.selectAll()

    def close_bar(self):
        self.hide()
        if hasattr(self.target, "find_closed"):
            self.target.find_closed()

    def find(self, forward=True):
        text = self.find_edit.text()
        if not text:
            return False
        found = self.target.find(text, forward, *self._opts())
        self.status.setText("" if found else "Not found")
        return found

    def replace(self):
        text = self.find_edit.text()
        if not text:
            return
        self.target.replace(text, self.replace_edit.text(), *self._opts())
        self.find(True)

    def replace_all(self):
        text = self.find_edit.text()
        if not text:
            return
        n = self.target.replace_all(text, self.replace_edit.text(), *self._opts())
        self.status.setText(f"{n} replaced" if n else "Not found")
