#!/usr/bin/env python3
"""Tesseract - a minimal, modern web browser built on PyQt6 + QtWebEngine (Chromium)."""

import os
import sys
from pathlib import Path

# Chromium refuses to start its sandbox as root (common in containers/WSL).
# Must be set before QtWebEngine is imported.
if hasattr(os, "geteuid") and os.geteuid() == 0:
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt6.QtCore import QByteArray, QSize, Qt, QUrl
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError as exc:  # pragma: no cover - depends on the system
    sys.exit(
        f"Could not import QtWebEngine: {exc}\n"
        "Install it with:  pip install PyQt6-WebEngine\n"
        "On Linux you may also need system libraries; see README.md."
    )

APP_NAME = "Tesseract"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
HOME_URL = QUrl.fromLocalFile(str(ASSETS_DIR / "home.html"))
SEARCH_URL = "https://duckduckgo.com/?q={}"

# Feather-style stroke icons, rendered from inline SVG so no icon files are needed.
_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)
ICONS = {
    "back": '<polyline points="15 18 9 12 15 6"/>',
    "forward": '<polyline points="9 18 15 12 9 6"/>',
    "reload": '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    "stop": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
    '<polyline points="9 22 9 12 15 12 15 22"/>',
}

STYLESHEET = """
QMainWindow { background: #0f1117; }
QToolBar {
    background: #161a23;
    border: none;
    border-bottom: 1px solid #232838;
    padding: 6px 10px;
    spacing: 4px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
}
QToolButton:hover { background: #232a3a; }
QToolButton:pressed { background: #2c3448; }
QToolButton:disabled { background: transparent; }
QLineEdit {
    background: #0f1117;
    color: #e6e9ef;
    border: 1px solid #2a3142;
    border-radius: 16px;
    padding: 6px 16px;
    margin-left: 6px;
    font-size: 14px;
    selection-background-color: #3d59a1;
}
QLineEdit:focus { border: 1px solid #7aa2f7; }
QProgressBar {
    background: #161a23;
    border: none;
    max-height: 3px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #7aa2f7, stop:0.6 #bb9af7, stop:1 #f7768e);
}
"""


def make_icon(name: str) -> QIcon:
    """Build an icon with a normal and a dimmed (disabled) state."""
    icon = QIcon()
    for color, mode in (("#c0caf5", QIcon.Mode.Normal), ("#454c63", QIcon.Mode.Disabled)):
        pixmap = QPixmap()
        svg = _SVG.format(color=color, body=ICONS[name])
        pixmap.loadFromData(QByteArray(svg.encode()), "SVG")
        icon.addPixmap(pixmap, mode)
    return icon


def url_from_input(text: str) -> QUrl:
    """Turn whatever the user typed into a URL: a real address, or a web search."""
    text = text.strip()
    if not text:
        return HOME_URL
    has_scheme = "://" in text or text.startswith(("about:", "file:", "data:"))
    looks_like_host = " " not in text and ("." in text or text.startswith("localhost"))
    if has_scheme or looks_like_host:
        if not has_scheme and not text.startswith(("localhost", "127.")):
            text = "https://" + text  # Default to HTTPS like modern browsers.
        url = QUrl.fromUserInput(text)
        if url.isValid():
            return url
    return QUrl(SEARCH_URL.format(QUrl.toPercentEncoding(text).data().decode()))


class BrowserWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)

        self.view = QWebEngineView()

        self.back_action = self._add_action("back", "Back (Alt+Left)", self.view.back,
                                            QKeySequence.StandardKey.Back)
        self.forward_action = self._add_action("forward", "Forward (Alt+Right)", self.view.forward,
                                               QKeySequence.StandardKey.Forward)
        self.reload_action = self._add_action("reload", "Reload (F5)", self._reload_or_stop,
                                              QKeySequence.StandardKey.Refresh)
        self.home_action = self._add_action("home", "Home (Alt+Home)", self.go_home,
                                            QKeySequence("Alt+Home"))

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Search or enter address")
        self.address_bar.setClearButtonEnabled(True)
        self.address_bar.returnPressed.connect(self.navigate_to_input)

        focus_bar = QAction(self)
        focus_bar.setShortcuts([QKeySequence("Ctrl+L"), QKeySequence("F6")])
        focus_bar.triggered.connect(self._focus_address_bar)
        self.addAction(focus_bar)

        toolbar = QToolBar("Navigation")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        for action in (self.back_action, self.forward_action, self.reload_action, self.home_action):
            toolbar.addAction(action)
        toolbar.addWidget(self.address_bar)
        self.addToolBar(toolbar)

        # Thin loading bar sitting between the toolbar and the page.
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setRange(0, 100)
        self.progress.hide()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.progress)
        layout.addWidget(self.view)
        self.setCentralWidget(central)

        self.view.urlChanged.connect(self._on_url_changed)
        self.view.titleChanged.connect(self._on_title_changed)
        self.view.loadStarted.connect(self._on_load_started)
        self.view.loadProgress.connect(self._on_load_progress)
        self.view.loadFinished.connect(self._on_load_finished)

        self._loading = False
        self._update_nav_buttons()
        self.go_home()

    def _add_action(self, icon: str, tip: str, slot, shortcut) -> QAction:
        action = QAction(make_icon(icon), tip.split(" (")[0], self)
        action.setToolTip(tip)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    # Navigation

    def navigate_to_input(self) -> None:
        self.view.setUrl(url_from_input(self.address_bar.text()))
        self.view.setFocus()

    def go_home(self) -> None:
        self.view.setUrl(HOME_URL)

    def _reload_or_stop(self) -> None:
        if self._loading:
            self.view.stop()
        else:
            self.view.reload()

    def _focus_address_bar(self) -> None:
        self.address_bar.setFocus()
        self.address_bar.selectAll()

    # Web view signals

    def _on_url_changed(self, url: QUrl) -> None:
        # Fires for typed URLs, clicked links, redirects and back/forward alike.
        # The homepage shows an empty bar (with placeholder) like a new-tab page.
        self.address_bar.setText("" if url == HOME_URL else url.toString())
        self.address_bar.setCursorPosition(0)
        self._update_nav_buttons()

    def _on_title_changed(self, title: str) -> None:
        self.setWindowTitle(f"{title} - {APP_NAME}" if title and title != APP_NAME else APP_NAME)

    def _on_load_started(self) -> None:
        self._loading = True
        self.progress.setValue(0)
        self.progress.show()
        self.reload_action.setIcon(make_icon("stop"))
        self.reload_action.setToolTip("Stop (Esc)")

    def _on_load_progress(self, value: int) -> None:
        self.progress.setValue(value)

    def _on_load_finished(self, ok: bool) -> None:
        self._loading = False
        self.progress.hide()
        self.reload_action.setIcon(make_icon("reload"))
        self.reload_action.setToolTip("Reload (F5)")
        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        history = self.view.history()
        self.back_action.setEnabled(history.canGoBack())
        self.forward_action.setEnabled(history.canGoForward())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._loading:
            self.view.stop()
        else:
            super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = BrowserWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
