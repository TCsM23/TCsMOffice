"""The built-in updater: ask GitHub for the newest release and offer to install it.

The release workflow publishes every push to main as a GitHub Release with
one asset per platform. On start-up the app asks the GitHub API for the
latest release; if it is newer than this build, a dialog asks whether to
update. Saying yes downloads the right asset and hands over to it:

- Windows: runs the new Setup wizard silently, which closes this copy,
  installs over it and starts the new one.
- Linux AppImage: swaps the AppImage file in place and restarts.
- Android: hands the .apk to the system installer (Android always asks).
- Running from source: opens the release page.

The version logic and asset choice are plain Python so the tests can drive
them without a network or a window.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .version import UPDATE_REPO, __version__

API_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"


# ---- plain Python ----------------------------------------------------------
def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.10' -> (1, 2, 10). Anything that isn't a number is ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:4])


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def current_platform() -> str:
    if hasattr(sys, "getandroidapilevel") or "ANDROID_ARGUMENT" in os.environ:
        return "android"
    if sys.platform.startswith("win"):
        return "windows"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    if sys.platform == "darwin":
        return "macos"
    return "source"


ASSET_SUFFIX = {"windows": ".exe", "appimage": ".AppImage", "android": ".apk"}


@dataclass
class Release:
    version: str
    notes: str
    page_url: str
    asset_name: str | None = None
    asset_url: str | None = None
    asset_size: int = 0


def release_from_json(data: dict, platform: str) -> Release:
    """Pick the version, notes and this platform's download out of the API answer."""
    rel = Release(version=data.get("tag_name", "").lstrip("vV"),
                  notes=(data.get("body") or "").strip(),
                  page_url=data.get("html_url", ""))
    suffix = ASSET_SUFFIX.get(platform)
    if suffix:
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(suffix):
                rel.asset_name = asset["name"]
                rel.asset_url = asset.get("browser_download_url")
                rel.asset_size = asset.get("size", 0)
                break
    return rel


def is_frozen() -> bool:
    """True when running from an installed build rather than `python -m office`."""
    return bool(getattr(sys, "frozen", False)) or current_platform() in ("android", "appimage")


# ---- Qt --------------------------------------------------------------------
from PySide6.QtCore import QObject, QProcess, QSettings, QTimer, QUrl, Qt, Signal  # noqa: E402
from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QTextBrowser, QVBoxLayout,
)


def _request(url: str) -> QNetworkRequest:
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", f"TCsOffice/{__version__}".encode())
    req.setRawHeader(b"Accept", b"application/vnd.github+json")
    req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                     QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
    return req


class Updater(QObject):
    """Checks GitHub once and drives the dialog. Keep one per main window."""

    checked = Signal(str)  # a short status line, for the manual "check" path

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.net = QNetworkAccessManager(self)
        self.settings = QSettings("TCsM", "TCsOffice")
        self._manual = False

    # -- checking --
    def check_later(self, ms: int = 2500):
        """Check quietly a moment after start-up, so the window paints first."""
        QTimer.singleShot(ms, lambda: self.check(manual=False))

    def check(self, manual: bool = True):
        self._manual = manual
        reply = self.net.get(_request(API_URL))
        reply.finished.connect(lambda: self._on_checked(reply))

    def _on_checked(self, reply: QNetworkReply):
        reply.deleteLater()
        if reply.error() != QNetworkReply.NetworkError.NoError:
            if self._manual:
                QMessageBox.information(self.window, "Updates",
                                        "Couldn't reach GitHub to check for updates.\n\n"
                                        f"{reply.errorString()}")
            return
        import json
        try:
            rel = release_from_json(json.loads(bytes(reply.readAll()).decode()),
                                    current_platform())
        except (ValueError, KeyError):
            return
        if not is_newer(rel.version):
            if self._manual:
                QMessageBox.information(self.window, "Updates",
                                        f"You have the newest edition (v{__version__}).")
            return
        if not self._manual and self.settings.value("skip_version") == rel.version:
            return
        self._offer(rel)

    # -- asking --
    def _offer(self, rel: Release):
        dlg = UpdateDialog(rel, self.window)
        answer = dlg.exec()
        if answer == UpdateDialog.SKIP:
            self.settings.setValue("skip_version", rel.version)
        elif answer == QDialog.DialogCode.Accepted:
            self._install(rel)

    # -- installing --
    def _install(self, rel: Release):
        platform = current_platform()
        if not is_frozen() or not rel.asset_url:
            QDesktopServices.openUrl(QUrl(rel.page_url))
            return
        if platform == "android":
            # Android only lets the system installer replace an app, and it
            # always asks; the browser downloads the .apk and offers it.
            QDesktopServices.openUrl(QUrl(rel.asset_url))
            return
        DownloadDialog(self, rel, platform).exec()

    def hand_over(self, path: Path, platform: str):
        """The new build is on disk: start it and close this copy."""
        if not self.window.close():  # the user kept unsaved work open
            return
        if platform == "windows":
            # Inno Setup: closes running copies, installs over them, and its
            # [Run] entry starts the new version when it finishes.
            QProcess.startDetached(str(path), ["/SILENT", "/SP-", "/NOCANCEL",
                                               "/CLOSEAPPLICATIONS"])
        elif platform == "appimage":
            target = Path(os.environ["APPIMAGE"])
            os.chmod(path, 0o755)
            os.replace(path, target)
            QProcess.startDetached(str(target), [])
        QApplication.quit()


class UpdateDialog(QDialog):
    SKIP = 2

    def __init__(self, rel: Release, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A new edition of TCsOffice")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        title = QLabel(f"TCsOffice v{rel.version} is ready")
        title.setObjectName("cellTitle")
        sub = QLabel(f"You have v{__version__}. Update now? Your open files are kept "
                     "safe: you'll be asked to save anything unsaved first.")
        sub.setWordWrap(True)
        sub.setObjectName("muted")
        lay.addWidget(title)
        lay.addWidget(sub)
        if rel.notes:
            notes = QTextBrowser()
            notes.setMarkdown(rel.notes)
            notes.setMaximumHeight(180)
            lay.addWidget(notes)
        row = QHBoxLayout()
        skip = QPushButton("Skip this version")
        later = QPushButton("Later")
        go = QPushButton("Update now")
        go.setObjectName("primary")
        go.setDefault(True)
        skip.clicked.connect(lambda: self.done(self.SKIP))
        later.clicked.connect(self.reject)
        go.clicked.connect(self.accept)
        row.addWidget(skip)
        row.addStretch(1)
        row.addWidget(later)
        row.addWidget(go)
        lay.addLayout(row)


class DownloadDialog(QDialog):
    def __init__(self, updater: Updater, rel: Release, platform: str):
        super().__init__(updater.window)
        self.updater, self.rel, self.platform = updater, rel, platform
        self.setWindowTitle("Downloading update")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Fetching {rel.asset_name}…"))
        self.bar = QProgressBar()
        self.bar.setRange(0, max(rel.asset_size, 0))
        lay.addWidget(self.bar)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignRight)

        folder = Path(tempfile.gettempdir()) / "TCsOffice-update"
        folder.mkdir(exist_ok=True)
        if platform == "appimage":  # same filesystem as the AppImage, so os.replace works
            folder = Path(os.environ["APPIMAGE"]).parent
        self.target = folder / (rel.asset_name + ".part")
        self.file = open(self.target, "wb")
        self.reply = updater.net.get(_request(rel.asset_url))
        self.reply.readyRead.connect(lambda: self.file.write(bytes(self.reply.readAll())))
        self.reply.downloadProgress.connect(self._progress)
        self.reply.finished.connect(self._finished)
        self.rejected.connect(self.reply.abort)

    def _progress(self, got, total):
        if total > 0:
            self.bar.setRange(0, total)
        self.bar.setValue(got)

    def _finished(self):
        self.file.write(bytes(self.reply.readAll()))
        self.file.close()
        ok = self.reply.error() == QNetworkReply.NetworkError.NoError
        error = self.reply.errorString()
        self.reply.deleteLater()
        if not ok:
            self.target.unlink(missing_ok=True)
            if self.isVisible():
                QMessageBox.warning(self, "Update failed", f"The download stopped:\n\n{error}")
                self.reject()
            return
        final = self.target.with_suffix("") if self.platform != "appimage" \
            else self.target.with_name(self.rel.asset_name + ".new")
        os.replace(self.target, final)
        self.accept()
        self.updater.hand_over(final, self.platform)
