"""Main window: the crimson header with Sheets / Writer / Slides, Open, Undo, Redo, Save."""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import samples, theme, updater
from .version import UPDATE_REPO, __version__
from .sheets.view import SheetsPanel
from .slides.view import SlidesPanel
from .writer.view import WriterPanel

MODULES = [
    # (tab label, file filter, suffix)
    ("Sheets", "Excel workbook (*.xlsx);;CSV, comma-separated (*.csv)", ".xlsx"),
    ("Writer", "Word document (*.docx)", ".docx"),
    ("Slides", "PowerPoint presentation (*.pptx)", ".pptx"),
]
# Which module opens a file, by its extension.
SUFFIX_MODULE = {".xlsx": 0, ".xlsm": 0, ".csv": 0, ".docx": 1, ".pptx": 2}
ALL_FILES = "TCsOffice files (*.xlsx *.xlsm *.csv *.docx *.pptx)"


def app_icon() -> QIcon:
    icon = QIcon()
    for name in ("icon.png", "icon-512.png"):
        path = theme.ASSETS / name
        if path.exists():
            icon.addFile(str(path))
    return icon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TCsOffice")
        self.setWindowIcon(app_icon())
        self.resize(1280, 780)

        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 14)
        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)
        outer.addWidget(card)
        self.setCentralWidget(root)

        card_lay.addWidget(self._build_header())
        ornament = QFrame()
        ornament.setObjectName("ornament")
        card_lay.addWidget(ornament)

        self.stack = QStackedWidget()
        self.sheets = SheetsPanel()
        self.writer = WriterPanel()
        self.slides = SlidesPanel()
        for panel in (self.sheets, self.writer, self.slides):
            self.stack.addWidget(panel)
            panel.titleChanged.connect(self._refresh_header)
            panel.undo_stack.subscribe(self._refresh_header)
        card_lay.addWidget(self.stack, 1)

        self.sheets.load_sheet(samples.supplies_sheet(), formats=samples.supplies_formats())
        self.writer.load(samples.welcome_document())
        self.writer.pdf_btn.clicked.connect(self.export_pdf)
        self.sheets.chartToSlides.connect(self.chart_to_slides)
        self.setAcceptDrops(True)

        self.tabs.idClicked.connect(self.switch_to)
        self.new_btn.clicked.connect(self.new_file)
        self.open_btn.clicked.connect(self.open_file)
        self.save_btn.clicked.connect(lambda: self.save_file())
        self.undo_btn.clicked.connect(lambda: self.current().undo_stack.undo())
        self.redo_btn.clicked.connect(lambda: self.current().undo_stack.redo())
        self.updater = updater.Updater(self)

        def shortcut(keys, slot):
            for k in keys if isinstance(keys, (list, tuple)) else [keys]:
                QShortcut(QKeySequence(k), self, slot)
        shortcut(QKeySequence.StandardKey.New, self.new_file)
        shortcut(QKeySequence.StandardKey.Open, self.open_file)
        shortcut(QKeySequence.StandardKey.Find, lambda: self.current().open_find(False))
        shortcut("Ctrl+H", lambda: self.current().open_find(True))
        shortcut("Ctrl+Shift+E", self.export_pdf)
        shortcut(QKeySequence.StandardKey.Save, lambda: self.save_file())
        shortcut(QKeySequence.StandardKey.SaveAs, lambda: self.save_file(save_as=True))
        shortcut(QKeySequence.StandardKey.Undo, self.undo_btn.click)
        redo_keys = QKeySequence.keyBindings(QKeySequence.StandardKey.Redo)
        # Two shortcuts on the same keys cancel each other out, so only add
        # Ctrl+Y where the platform's Redo doesn't already include it (Linux, macOS).
        if QKeySequence("Ctrl+Y") not in redo_keys:
            redo_keys.append(QKeySequence("Ctrl+Y"))
        shortcut(redo_keys, self.redo_btn.click)
        shortcut("F5", self._present)
        for i in range(len(MODULES)):
            shortcut(f"Ctrl+{i + 1}", lambda i=i: self.switch_to(i))
        self._refresh_header()

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 10, 14, 10)
        logo = QLabel()
        logo.setFixedSize(34, 38)
        logo.setPixmap(app_icon().pixmap(38, 38))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        names = QVBoxLayout()
        names.setSpacing(0)
        app_name = QLabel("TCsOffice")
        app_name.setObjectName("appName")
        self.file_label = QLabel()
        self.file_label.setObjectName("fileName")
        names.addWidget(app_name)
        names.addWidget(self.file_label)
        h.addWidget(logo)
        h.addSpacing(8)
        h.addLayout(names)
        h.addStretch(1)

        segment = QFrame()
        segment.setObjectName("segment")
        seg = QHBoxLayout(segment)
        seg.setContentsMargins(3, 3, 3, 3)
        seg.setSpacing(2)
        self.tabs = QButtonGroup(self)
        for i, (label, _f, _s) in enumerate(MODULES):
            b = QPushButton(label.upper())
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"{label} (Ctrl+{i + 1})")
            self.tabs.addButton(b, i)
            seg.addWidget(b)
        self.tabs.button(0).setChecked(True)
        h.addWidget(segment)
        h.addStretch(1)

        self.new_btn = QPushButton("New")
        self.new_btn.setToolTip("A blank file in this module (Ctrl+N)")
        self.open_btn = QPushButton("Open")
        self.open_btn.setToolTip("Open a workbook, document or presentation (Ctrl+O)")
        self.undo_btn = QPushButton("↶ Undo")
        self.redo_btn = QPushButton("Redo ↷")
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        for b in (self.new_btn, self.open_btn, self.undo_btn, self.redo_btn, self.save_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            h.addWidget(b)

        self.more_btn = QToolButton()
        self.more_btn.setObjectName("more")
        self.more_btn.setText("⋮")
        self.more_btn.setToolTip("More")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more_btn)
        menu.addAction("Save as…\tCtrl+Shift+S", lambda: self.save_file(save_as=True))
        menu.addAction("Export PDF…\tCtrl+Shift+E", self.export_pdf)
        self.slide_png_action = menu.addAction("Save slide as picture…", self.export_slide_png)
        menu.addAction("Find and replace…\tCtrl+H", lambda: self.current().open_find(True))
        menu.addSeparator()
        menu.addAction("Check for updates…", lambda: self.updater.check(manual=True))
        menu.addAction("About TCsOffice", self.about)
        self.more_btn.setMenu(menu)
        h.addWidget(self.more_btn)
        return header

    def current(self):
        return self.stack.currentWidget()

    def switch_to(self, index):
        self.stack.setCurrentIndex(index)
        self.tabs.button(index).setChecked(True)
        self._refresh_header()

    def _refresh_header(self):
        panel = self.current()
        stack = panel.undo_stack
        self.file_label.setText(panel.display_name())
        self.undo_btn.setEnabled(stack.can_undo())
        self.redo_btn.setEnabled(stack.can_redo())
        self.undo_btn.setToolTip(f"Undo {stack.undo_text()} (Ctrl+Z)" if stack.can_undo() else "")
        self.redo_btn.setToolTip(f"Redo {stack.redo_text()} (Ctrl+Y)" if stack.can_redo() else "")
        label = MODULES[self.stack.currentIndex()][0]
        self.setWindowTitle(f"{panel.display_name()} — TCsOffice {label}")
        if hasattr(self, "slide_png_action"):
            self.slide_png_action.setVisible(self.stack.currentIndex() == 2)

    def _present(self):
        self.switch_to(2)
        self.slides.present()

    def _confirm_discard(self, panel, label):
        if not panel.modified:
            return True
        answer = QMessageBox.question(self, "Unsaved changes",
                                      f"{label} has unsaved changes. Discard them?")
        return answer == QMessageBox.StandardButton.Yes

    def new_file(self):
        i = self.stack.currentIndex()
        panel = self.current()
        if self._confirm_discard(panel, MODULES[i][0]):
            panel.new_file()
            self._refresh_header()

    def open_file(self, path=None):
        i = self.stack.currentIndex()
        if not path:
            filters = f"{ALL_FILES};;{MODULES[i][1]}"
            path, _ = QFileDialog.getOpenFileName(self, "Open", "", filters)
        if not path:
            return False
        target = SUFFIX_MODULE.get(os.path.splitext(str(path))[1].lower(), i)
        panel = self.stack.widget(target)
        if not self._confirm_discard(panel, MODULES[target][0]):
            return False
        self.switch_to(target)
        try:
            panel.open_file(path)
        except Exception as exc:  # a broken file shouldn't take the app down
            QMessageBox.warning(self, "Couldn't open file", f"{path}\n\n{exc}")
            return False
        self._refresh_header()
        return True

    def save_file(self, save_as=False):
        i = self.stack.currentIndex()
        panel = self.current()
        path = panel.path
        if save_as or path is None:
            path, chosen = QFileDialog.getSaveFileName(self, "Save", "", MODULES[i][1])
            if not path:
                return
            ext = os.path.splitext(path)[1].lower()
            if SUFFIX_MODULE.get(ext) != i:
                path += ".csv" if "csv" in (chosen or "").lower() else MODULES[i][2]
        try:
            panel.save_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't save file", f"{path}\n\n{exc}")
        self._refresh_header()

    def export_pdf(self, path=None):
        panel = self.current()
        if not path:
            stem = panel.path.stem if panel.path else "Untitled"
            path, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{stem}.pdf", "PDF (*.pdf)")
        if path:
            if not str(path).lower().endswith(".pdf"):
                path = str(path) + ".pdf"
            try:
                panel.export_pdf(path)
            except Exception as exc:
                QMessageBox.warning(self, "Couldn't export PDF", f"{path}\n\n{exc}")

    def export_slide_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save slide as picture", "slide.png",
                                              "PNG (*.png)")
        if path:
            self.slides.export_slide_png(path if path.lower().endswith(".png") else path + ".png")

    def chart_to_slides(self, png: bytes):
        """Sheets' chart dialog sent a picture: put it on the current slide."""
        self.switch_to(2)
        self.slides.insert_image_data(png, "Insert chart")

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and all(os.path.splitext(u.toLocalFile())[1].lower() in SUFFIX_MODULE
                        for u in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls()[:1]:
            self.open_file(url.toLocalFile())

    def make_compact(self):
        """Phone screens: shorter header buttons and slimmer margins."""
        self.centralWidget().layout().setContentsMargins(0, 0, 0, 0)
        self.undo_btn.setText("↶")
        self.redo_btn.setText("↷")
        self.new_btn.hide()
        self.file_label.hide()

    def about(self):
        QMessageBox.about(
            self, "About TCsOffice",
            f"<h3>TCsOffice v{__version__}</h3>"
            "<p>Sheets, Writer and Slides in crimson, gilt and parchment.</p>"
            f"<p>Updates come from <a href='https://github.com/{UPDATE_REPO}/releases'>"
            f"github.com/{UPDATE_REPO}</a>.</p>")

    def closeEvent(self, event):
        unsaved = [MODULES[i][0] for i, p in enumerate((self.sheets, self.writer, self.slides))
                   if p.modified]
        if unsaved:
            answer = QMessageBox.question(
                self, "Unsaved changes",
                f"{', '.join(unsaved)} {'has' if len(unsaved) == 1 else 'have'} unsaved "
                "changes. Close anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()


def create_app(argv=None):
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("TCsOffice")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    theme.load_fonts()
    app.setStyleSheet(theme.STYLESHEET)
    return app


def main():
    app = create_app()
    window = MainWindow()
    # Opened with a file ("Open with TCsOffice", or a file dropped on the icon).
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.exists(args[0]):
        window.open_file(args[0])
    if updater.current_platform() == "android":
        window.make_compact()
        window.showMaximized()
    else:
        window.show()
    # Installed builds look for a newer release; `python -m office` doesn't
    # unless asked to, so working on the code never nags.
    if updater.is_frozen() or os.environ.get("TCSOFFICE_CHECK_UPDATES"):
        window.updater.check_later()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
