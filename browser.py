#!/usr/bin/env python3
"""Tesseract - a minimal, modern web browser built on PyQt6 + QtWebEngine (Chromium)."""

import os
import sys
from pathlib import Path

# Chromium refuses to start its sandbox as root (common in containers/WSL).
# Must be set before QtWebEngine is imported.
if hasattr(os, "geteuid") and os.geteuid() == 0:
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt6.QtCore import QByteArray, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QStackedWidget,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage
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
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
    '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 '
    '15.3 15.3 0 0 1 4-10z"/>',
    "loading": '<circle cx="12" cy="12" r="9" stroke-opacity="0.25"/><path d="M21 12a9 9 0 0 0-9-9"/>',
}

STYLESHEET = """
QMainWindow, #tabStrip { background: #0f1117; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    color: #8a93a8;
    border: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-top: 6px;
    margin-right: 2px;
    padding: 7px 4px 7px 10px;
}
QTabBar::tab:selected { background: #161a23; }
QTabBar::tab:hover:!selected { background: #171b25; }
QTabBar::scroller { width: 48px; }
QTabBar QToolButton { background: #0f1117; border-radius: 0; }
QLabel#tabTitle { color: #8a93a8; font-size: 13px; }
QLabel#tabTitle[current="true"] { color: #e6e9ef; }
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
QTabBar QToolButton#tabClose { background: transparent; padding: 2px; border-radius: 5px; }
QTabBar QToolButton#tabClose:hover { background: #2c3448; }
QToolButton#newTab { margin: 6px 0 0 4px; }
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


class TabBar(QTabBar):
    """Tab bar with browser conventions: middle-click closes, double-click empty space opens."""

    newTabRequested = pyqtSignal()

    def mouseReleaseEvent(self, event) -> None:
        index = self.tabAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.MiddleButton and index >= 0:
            self.tabCloseRequested.emit(index)
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.tabAt(event.position().toPoint()) < 0:
            self.newTabRequested.emit()
        else:
            super().mouseDoubleClickEvent(event)


class TabLabel(QWidget):
    """Favicon + left-aligned, elided title. Replaces QTabBar's centred text."""

    TITLE_WIDTH = 150

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        self.title_label = QLabel()
        self.title_label.setObjectName("tabTitle")
        self.title_label.setFixedWidth(self.TITLE_WIDTH)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)

    def set_icon(self, icon: QIcon) -> None:
        self.icon_label.setPixmap(icon.pixmap(16, 16))

    def set_title(self, title: str) -> None:
        self.title = title
        metrics = self.title_label.fontMetrics()
        self.title_label.setText(metrics.elidedText(title, Qt.TextElideMode.ElideRight, self.TITLE_WIDTH))

    def set_current(self, current: bool) -> None:
        self.title_label.setProperty("current", current)
        self.title_label.style().unpolish(self.title_label)
        self.title_label.style().polish(self.title_label)


class BrowserTab(QWebEngineView):
    """One page. Tracks its own load state so the shared toolbar can show it on tab switch."""

    def __init__(self, browser: "BrowserWindow") -> None:
        super().__init__()
        self.browser = browser
        self.loading = False
        self.load_progress = 0

    def createWindow(self, window_type):
        # target=_blank links, window.open(), Ctrl+click and middle-click all land here.
        background = window_type == QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        return self.browser.new_tab(background=background, opener=self)


class BrowserWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)

        # Tab strip on top, Chrome-style: tabs followed by a "+" button.
        self.tab_bar = TabBar()
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self.close_tab)
        self.tab_bar.newTabRequested.connect(self.open_new_tab)

        new_tab_button = QToolButton()
        new_tab_button.setObjectName("newTab")
        new_tab_button.setIcon(make_icon("plus"))
        new_tab_button.setIconSize(QSize(16, 16))
        new_tab_button.setToolTip("New tab (Ctrl+T)")
        new_tab_button.clicked.connect(self.open_new_tab)

        tab_strip = QWidget()
        tab_strip.setObjectName("tabStrip")
        tab_strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip_layout = QHBoxLayout(tab_strip)
        strip_layout.setContentsMargins(8, 0, 8, 0)
        strip_layout.setSpacing(0)
        strip_layout.addWidget(self.tab_bar)
        strip_layout.addWidget(new_tab_button)
        strip_layout.addStretch(1)

        self.back_action = self._add_action("back", "Back (Alt+Left)", lambda: self.current_view().back(),
                                            QKeySequence.StandardKey.Back)
        self.forward_action = self._add_action("forward", "Forward (Alt+Right)",
                                               lambda: self.current_view().forward(),
                                               QKeySequence.StandardKey.Forward)
        self.reload_action = self._add_action("reload", "Reload (F5)", self._reload_or_stop,
                                              QKeySequence.StandardKey.Refresh)
        self.home_action = self._add_action("home", "Home (Alt+Home)", self.go_home,
                                            QKeySequence("Alt+Home"))

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Search or enter address")
        self.address_bar.setClearButtonEnabled(True)
        self.address_bar.returnPressed.connect(self.navigate_to_input)

        toolbar = QToolBar("Navigation")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        for action in (self.back_action, self.forward_action, self.reload_action, self.home_action):
            toolbar.addAction(action)
        toolbar.addWidget(self.address_bar)

        # Thin loading bar sitting between the toolbar and the page.
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setRange(0, 100)
        self.progress.hide()

        self.stack = QStackedWidget()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(tab_strip)
        layout.addWidget(toolbar)
        layout.addWidget(self.progress)
        layout.addWidget(self.stack)
        self.setCentralWidget(central)

        self._add_shortcut(["Ctrl+L", "F6"], self._focus_address_bar)
        self._add_shortcut(["Ctrl+T"], self.open_new_tab)
        self._add_shortcut(["Ctrl+W", "Ctrl+F4"], lambda: self.close_tab(self.tab_bar.currentIndex()))
        self._add_shortcut(["Ctrl+Tab", "Ctrl+PgDown"], lambda: self._cycle_tab(1))
        self._add_shortcut(["Ctrl+Shift+Tab", "Ctrl+PgUp"], lambda: self._cycle_tab(-1))
        for n in range(1, 9):
            # triggered() passes `checked` first, so it must not land in `n`.
            self._add_shortcut([f"Ctrl+{n}"], lambda _checked=False, n=n: self._select_tab(n - 1))
        self._add_shortcut(["Ctrl+9"], lambda: self._select_tab(self.tab_bar.count() - 1))

        self.new_tab(HOME_URL)

    def _add_action(self, icon: str, tip: str, slot, shortcut) -> QAction:
        action = QAction(make_icon(icon), tip.split(" (")[0], self)
        action.setToolTip(tip)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    def _add_shortcut(self, keys: list, slot) -> None:
        action = QAction(self)
        action.setShortcuts([QKeySequence(k) for k in keys])
        action.triggered.connect(slot)
        self.addAction(action)

    # Tabs

    def current_view(self) -> BrowserTab:
        return self.stack.currentWidget()

    def _view_at(self, index: int):
        return self.tab_bar.tabData(index)

    def tab_label(self, index: int) -> TabLabel:
        return self.tab_bar.tabButton(index, QTabBar.ButtonPosition.LeftSide)

    def _index_of(self, view: BrowserTab) -> int:
        for i in range(self.tab_bar.count()):
            if self._view_at(i) is view:
                return i
        return -1

    def new_tab(self, url: QUrl = None, background: bool = False, opener: BrowserTab = None) -> BrowserTab:
        view = BrowserTab(self)
        view.urlChanged.connect(lambda u, v=view: self._on_url_changed(v, u))
        view.titleChanged.connect(lambda t, v=view: self._on_title_changed(v, t))
        view.iconChanged.connect(lambda _, v=view: self._refresh_tab_icon(v))
        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadProgress.connect(lambda p, v=view: self._on_load_progress(v, p))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(v))
        self.stack.addWidget(view)

        # Tabs opened from a page go right after it, like Chrome; others go at the end.
        if opener is not None:
            index = self.tab_bar.insertTab(self._index_of(opener) + 1, "")
        else:
            index = self.tab_bar.addTab("")
        self.tab_bar.setTabData(index, view)
        label = TabLabel()
        label.set_icon(make_icon("globe"))
        label.set_title("New Tab")
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, label)

        close_button = QToolButton()
        close_button.setObjectName("tabClose")
        close_button.setIcon(make_icon("stop"))
        close_button.setIconSize(QSize(12, 12))
        close_button.setToolTip("Close tab (Ctrl+W)")
        close_button.clicked.connect(lambda _, v=view: self.close_tab(self._index_of(v)))
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, close_button)

        if not background:
            self.tab_bar.setCurrentIndex(index)
            # The very first tab became current before its data was set; sync it now.
            self._on_tab_changed(index)
        if url is not None:
            view.setUrl(url)
        return view

    def open_new_tab(self) -> None:
        self.new_tab(HOME_URL)
        self._focus_address_bar()

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        if self.tab_bar.count() == 1:
            self.close()  # Closing the last tab closes the window, like Chrome.
            return
        view = self._view_at(index)
        self.tab_bar.removeTab(index)
        self.stack.removeWidget(view)
        view.deleteLater()

    def _cycle_tab(self, step: int) -> None:
        count = self.tab_bar.count()
        self.tab_bar.setCurrentIndex((self.tab_bar.currentIndex() + step) % count)

    def _select_tab(self, index: int) -> None:
        if 0 <= index < self.tab_bar.count():
            self.tab_bar.setCurrentIndex(index)

    def _on_tab_changed(self, index: int) -> None:
        view = self._view_at(index) if index >= 0 else None
        if view is None:
            return
        self.stack.setCurrentWidget(view)
        for i in range(self.tab_bar.count()):
            if self.tab_label(i):
                self.tab_label(i).set_current(i == index)
        self._show_url(view.url())
        self._update_window_title(view.title())
        self._update_nav_buttons()
        self._update_load_state()
        if not self.address_bar.hasFocus():
            view.setFocus()

    # Navigation (always acts on the current tab)

    def navigate_to_input(self) -> None:
        view = self.current_view()
        view.setUrl(url_from_input(self.address_bar.text()))
        view.setFocus()

    def go_home(self) -> None:
        self.current_view().setUrl(HOME_URL)

    def _reload_or_stop(self) -> None:
        view = self.current_view()
        if view.loading:
            view.stop()
        else:
            view.reload()

    def _focus_address_bar(self) -> None:
        self.address_bar.setFocus()
        self.address_bar.selectAll()

    # Web view signals. Every tab reports in; the toolbar only follows the current one.

    def _on_url_changed(self, view: BrowserTab, url: QUrl) -> None:
        # Fires for typed URLs, clicked links, redirects and back/forward alike.
        if view is self.current_view():
            self._show_url(url)
            self._update_nav_buttons()

    def _on_title_changed(self, view: BrowserTab, title: str) -> None:
        index = self._index_of(view)
        if index < 0:
            return
        text = title or view.url().toString() or "New Tab"
        self.tab_label(index).set_title(text)
        self.tab_bar.setTabToolTip(index, text)
        if view is self.current_view():
            self._update_window_title(title)

    def _on_load_started(self, view: BrowserTab) -> None:
        view.loading = True
        view.load_progress = 0
        self._refresh_tab_icon(view)
        if view is self.current_view():
            self._update_load_state()

    def _on_load_progress(self, view: BrowserTab, value: int) -> None:
        view.load_progress = value
        if view is self.current_view():
            self.progress.setValue(value)

    def _on_load_finished(self, view: BrowserTab) -> None:
        view.loading = False
        self._refresh_tab_icon(view)
        if view is self.current_view():
            self._update_load_state()
            self._update_nav_buttons()

    # Toolbar / tab presentation

    def _show_url(self, url: QUrl) -> None:
        # The homepage shows an empty bar (with placeholder) like a new-tab page.
        self.address_bar.setText("" if url == HOME_URL else url.toString())
        self.address_bar.setCursorPosition(0)

    def _update_window_title(self, title: str) -> None:
        self.setWindowTitle(f"{title} - {APP_NAME}" if title and title != APP_NAME else APP_NAME)

    def _refresh_tab_icon(self, view: BrowserTab) -> None:
        index = self._index_of(view)
        if index < 0:
            return
        if view.loading:
            icon = make_icon("loading")
        elif not view.icon().isNull():
            icon = view.icon()
        else:
            icon = make_icon("globe")
        self.tab_label(index).set_icon(icon)

    def _update_load_state(self) -> None:
        view = self.current_view()
        self.progress.setVisible(view.loading)
        self.progress.setValue(view.load_progress)
        self.reload_action.setIcon(make_icon("stop" if view.loading else "reload"))
        self.reload_action.setToolTip("Stop (Esc)" if view.loading else "Reload (F5)")

    def _update_nav_buttons(self) -> None:
        history = self.current_view().history()
        self.back_action.setEnabled(history.canGoBack())
        self.forward_action.setEnabled(history.canGoForward())

    def keyPressEvent(self, event) -> None:
        view = self.current_view()
        if event.key() == Qt.Key.Key_Escape and view.loading:
            view.stop()
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
