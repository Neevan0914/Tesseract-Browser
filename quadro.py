"""Quadro - Tesseract's AI search assistant: Claude with web search, in a side panel."""

import html
import os
import re
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QPalette, QTextDocument
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

MODEL = "claude-opus-5-5"
MAX_CONTINUATIONS = 5  # resumes of a long server-side search turn (pause_turn)
SETTINGS_KEY = "quadro/api_key"
FONT_FILE = Path(__file__).resolve().parent / "assets" / "fonts" / "BlackOpsOne-Regular.ttf"
KEYS_URL = "https://console.anthropic.com/settings/keys"

SYSTEM_PROMPT = (
    "You are Quadro, the AI search assistant built into the Tesseract web browser. "
    "Search the web whenever the answer depends on current, specific or factual information. "
    "Lead with the direct answer in a sentence or two, then add only the detail that helps. "
    "Your answer appears in a narrow side panel, so keep it short and use Markdown sparingly: "
    "short lists and bold for key terms, no tables or headings."
)
TOOLS = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]

# Set on the dock itself so it also reaches the custom title bar.
STYLESHEET = """
#quadro { background: #12151d; }
#quadroHeader { background: #161a23; border-bottom: 1px solid #232838; }
QLabel#quadroTitle { color: #bb9af7; font-family: "Black Ops One"; font-size: 22px; }
QPushButton {
    background: transparent; color: #c0caf5; border: 1px solid #2a3142;
    border-radius: 12px; padding: 4px 12px; font-size: 12px;
}
QPushButton:hover { border-color: #7aa2f7; }
QPushButton:disabled { color: #454c63; border-color: #232838; }
QPushButton#quadroPrimary { background: #3d59a1; border-color: #3d59a1; color: #e6e9ef; }
QPushButton#quadroPrimary:hover { background: #4a68b8; }
QTextBrowser {
    background: #12151d; color: #d5d9e3; border: none; padding: 6px 12px;
    font-size: 14px; selection-background-color: #3d59a1;
}
QLabel { color: #8a93a8; font-size: 13px; }
QLabel#quadroStatus { color: #7aa2f7; font-style: italic; padding: 0 14px; }
QLineEdit { margin-left: 0; }
"""


def saved_api_key() -> str:
    """ANTHROPIC_API_KEY wins; otherwise the key saved from the panel."""
    return os.environ.get("ANTHROPIC_API_KEY") or QSettings("Tesseract", "Tesseract").value(SETTINGS_KEY, "") or ""


LINK_COLOR = "#7aa2f7"


def _markdown_to_html(markdown: str) -> str:
    """Claude's Markdown answer as an HTML fragment for the transcript."""
    doc = QTextDocument()
    doc.setMarkdown(markdown)
    body = re.search(r"<body[^>]*>(.*)</body>", doc.toHtml(), re.S)
    # Qt colours links with the default palette's blue, unreadable on the dark panel.
    return re.sub(r"color:#0000ff", f"color:{LINK_COLOR}", body.group(1) if body else "")


class _Signals(QObject):
    # Every signal carries the request's generation number, so output from a
    # stopped or superseded request can be ignored.
    status = pyqtSignal(int, str)
    text = pyqtSignal(int, str)
    done = pyqtSignal(int, list, list, str)  # assistant messages, sources, stop note
    failed = pyqtSignal(int, str)


def _run_request(signals: _Signals, gen: int, api_key: str, history: list, cancelled) -> None:
    """Stream one answer from Claude. Runs on a daemon thread; talks back only via signals."""
    try:
        import anthropic
    except ImportError:
        signals.failed.emit(gen, "Quadro needs the Anthropic SDK. In the Tesseract folder run:\n"
                                 ".venv\\Scripts\\python -m pip install -r requirements.txt")
        return

    client = anthropic.Anthropic(api_key=api_key)
    messages = list(history)
    new_messages, sources, wrote_text = [], [], False
    try:
        for _ in range(MAX_CONTINUATIONS + 1):
            with client.beta.messages.stream(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
                output_config={"effort": "medium"},
                cache_control={"type": "ephemeral"},  # follow-up questions reuse the cached history
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # if Claude Opus 5.5 declines, Anthropic retries on its recommended model
            ) as stream:
                for event in stream:
                    if cancelled():
                        return
                    if event.type == "text":
                        signals.text.emit(gen, event.text)
                        wrote_text = True
                    elif event.type == "content_block_start" and event.content_block.type == "server_tool_use":
                        if wrote_text:
                            signals.text.emit(gen, "\n\n")
                        signals.status.emit(gen, "Searching the web…")
                    elif event.type == "content_block_stop" and event.content_block.type == "server_tool_use":
                        query = (event.content_block.input or {}).get("query")
                        if query:
                            signals.status.emit(gen, f"Searching: {query}")
                message = stream.get_final_message()

            if message.stop_reason == "refusal":
                signals.failed.emit(gen, "Quadro can't help with that request.")
                return
            # Append the full content (search results, thinking, citations) so the
            # next request continues from exactly what the model produced.
            assistant = {"role": "assistant", "content": message.content}
            messages.append(assistant)
            new_messages.append(assistant)
            for block in message.content:
                for citation in (getattr(block, "citations", None) or []):
                    url = getattr(citation, "url", None)
                    if url and url not in [u for _, u in sources]:
                        sources.append((getattr(citation, "title", None) or url, url))
            if message.stop_reason != "pause_turn":
                note = "Answer cut off at the length limit." if message.stop_reason == "max_tokens" else ""
                signals.done.emit(gen, new_messages, sources, note)
                return
        signals.done.emit(gen, new_messages, sources, "Search stopped after too many steps.")
    except anthropic.AuthenticationError:
        signals.failed.emit(gen, "Anthropic rejected the API key. Click “API key” above to enter a valid one.")
    except anthropic.PermissionDeniedError as e:
        signals.failed.emit(gen, f"This API key isn't allowed to do that: {e.message}")
    except anthropic.RateLimitError:
        signals.failed.emit(gen, "Quadro is being rate limited. Wait a minute and try again.")
    except anthropic.BadRequestError as e:
        signals.failed.emit(gen, f"Anthropic couldn't run the request: {e.message}")
    except anthropic.APIStatusError as e:
        signals.failed.emit(gen, f"Anthropic API error ({e.status_code}). Try again shortly.")
    except anthropic.APIConnectionError:
        signals.failed.emit(gen, "Couldn't reach Anthropic. Check your internet connection.")


class QuadroPanel(QDockWidget):
    """Chat panel docked beside the browser. Emits open_url for links clicked in answers."""

    open_url = pyqtSignal(QUrl)

    def __init__(self, parent=None) -> None:
        super().__init__("Quadro", parent)
        self.setObjectName("quadroDock")
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                         | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.setMinimumWidth(320)

        self.history = []   # messages sent to Claude
        self.turns = []     # what the transcript shows: dicts with role/text/sources/note/error
        self.generation = 0
        self.busy = False
        self.pending_query = ""
        self._cancel = lambda: False
        self.signals = _Signals()
        self.signals.status.connect(self._on_status)
        self.signals.text.connect(self._on_text)
        self.signals.done.connect(self._on_done)
        self.signals.failed.connect(self._on_failed)

        self.setStyleSheet(STYLESHEET)
        root = QWidget()
        root.setObjectName("quadro")
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        header = QWidget()
        header.setObjectName("quadroHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 10, 10)
        title = QLabel("Quadro")
        title.setObjectName("quadroTitle")
        QFontDatabase.addApplicationFont(str(FONT_FILE))  # "Black Ops One" for the title
        self.new_chat_button = QPushButton("New chat")
        self.new_chat_button.clicked.connect(self.new_chat)
        key_button = QPushButton("API key")
        key_button.clicked.connect(lambda: self._show_setup())
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.hide)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        for button in (self.new_chat_button, key_button, close_button):
            header_layout.addWidget(button)
        self.setTitleBarWidget(header)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_chat_page())
        self.pages.addWidget(self._build_setup_page())
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pages)
        self.setWidget(root)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(40)
        self._render_timer.timeout.connect(self._render)
        self._render()

    # Pages

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.anchorClicked.connect(self._on_link)
        palette = self.transcript.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(LINK_COLOR))
        self.transcript.setPalette(palette)
        self.status_label = QLabel("")
        self.status_label.setObjectName("quadroStatus")
        self.status_label.hide()

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Quadro anything")
        self.input.returnPressed.connect(self._send_from_input)
        self.send_button = QPushButton("Ask")
        self.send_button.setObjectName("quadroPrimary")
        self.send_button.clicked.connect(self._send_or_stop)
        row = QHBoxLayout()
        row.setContentsMargins(12, 8, 12, 12)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_button)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.status_label)
        layout.addLayout(row)
        return page

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        intro = QLabel(
            "Quadro answers questions by searching the web with Claude, Anthropic's AI model.<br><br>"
            "To turn it on, paste an Anthropic API key. Questions are sent to Anthropic and billed "
            "to that key's account. The key is saved for your user account on this computer.<br><br>"
            f'<a href="{KEYS_URL}" style="color:#7aa2f7">Get an API key from the Claude Console</a>'
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse
                                      | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        intro.linkActivated.connect(lambda url: self.open_url.emit(QUrl(url)))
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("sk-ant-…")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.returnPressed.connect(self._save_key)
        save = QPushButton("Save key")
        save.setObjectName("quadroPrimary")
        save.clicked.connect(self._save_key)
        self.forget_button = QPushButton("Remove saved key")
        self.forget_button.clicked.connect(self._forget_key)
        back = QPushButton("Back to chat")
        back.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.setup_note = QLabel("")
        self.setup_note.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(save)
        buttons.addWidget(self.forget_button)
        buttons.addStretch(1)
        buttons.addWidget(back)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(self.key_input)
        layout.addLayout(buttons)
        layout.addWidget(self.setup_note)
        layout.addStretch(1)
        return page

    def _show_setup(self, note: str = "") -> None:
        from_env = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_saved = bool(QSettings("Tesseract", "Tesseract").value(SETTINGS_KEY, ""))
        self.forget_button.setEnabled(has_saved)
        if from_env:
            note = note or "Using the key from the ANTHROPIC_API_KEY environment variable. A key saved here is ignored while that variable is set."
        elif has_saved and not note:
            note = "A key is saved. Paste a new one to replace it."
        self.setup_note.setText(note)
        self.key_input.clear()
        self.pages.setCurrentIndex(1)
        self.key_input.setFocus()

    def _save_key(self) -> None:
        key = self.key_input.text().strip()
        if not key:
            self.setup_note.setText("Paste a key first.")
            return
        QSettings("Tesseract", "Tesseract").setValue(SETTINGS_KEY, key)
        self.key_input.clear()
        self.pages.setCurrentIndex(0)
        if self.pending_query:
            query, self.pending_query = self.pending_query, ""
            self.ask(query)
        else:
            self.input.setFocus()

    def _forget_key(self) -> None:
        QSettings("Tesseract", "Tesseract").remove(SETTINGS_KEY)
        self._show_setup("Saved key removed.")

    # Public entry points

    def open_panel(self) -> None:
        self.show()
        self.raise_()
        if not saved_api_key():
            self._show_setup()
        else:
            self.pages.setCurrentIndex(0)
            self.input.setFocus()

    def ask(self, query: str) -> None:
        """Open the panel and ask `query` (or just focus the input when empty)."""
        query = query.strip()
        self.open_panel()
        if not query:
            return
        if not saved_api_key():
            self.pending_query = query
            return
        if self.busy:
            self.input.setText(query)
            return
        self._send(query)

    def new_chat(self) -> None:
        self._stop()
        self.history, self.turns = [], []
        self._render()
        self.input.setFocus()

    # Sending

    def _send_from_input(self) -> None:
        if not self.busy:
            self._send(self.input.text())

    def _send_or_stop(self) -> None:
        if self.busy:
            self._stop(note="Stopped.")
        else:
            self._send(self.input.text())

    def _send(self, query: str) -> None:
        query = query.strip()
        api_key = saved_api_key()
        if not query:
            return
        if not api_key:
            self.pending_query = query
            self._show_setup()
            return
        self.input.clear()
        self.history.append({"role": "user", "content": query})
        self.turns.append({"role": "user", "text": query})
        self.turns.append({"role": "assistant", "text": "", "sources": [], "note": "", "error": ""})
        self._set_busy(True, "Thinking…")
        self.generation += 1
        gen = self.generation
        self._cancel = lambda: gen != self.generation
        threading.Thread(target=_run_request, daemon=True,
                         args=(self.signals, gen, api_key, list(self.history), self._cancel)).start()
        self._render()

    def _stop(self, note: str = "") -> None:
        if not self.busy:
            return
        self.generation += 1  # the worker sees this and stops; late signals are ignored
        self.history.pop()    # the unanswered question doesn't go into the next request
        self.turns[-1]["note"] = note
        self._set_busy(False)
        self._render()

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self.busy = busy
        self.send_button.setText("Stop" if busy else "Ask")
        self.new_chat_button.setEnabled(True)
        self.status_label.setText(status)
        self.status_label.setVisible(busy and bool(status))

    # Worker signals

    def _on_status(self, gen: int, text: str) -> None:
        if gen == self.generation and self.busy:
            self.status_label.setText(text)
            self.status_label.show()

    def _on_text(self, gen: int, text: str) -> None:
        if gen == self.generation and self.busy:
            self.turns[-1]["text"] += text
            self.status_label.setText("Writing…")
            self._render_timer.start()

    def _on_done(self, gen: int, messages: list, sources: list, note: str) -> None:
        if gen != self.generation:
            return
        self.history.extend(messages)
        self.turns[-1]["sources"] = sources
        self.turns[-1]["note"] = note
        self._set_busy(False)
        self._render()

    def _on_failed(self, gen: int, message: str) -> None:
        if gen != self.generation:
            return
        self.history.pop()
        self.turns[-1]["error"] = message
        self._set_busy(False)
        self._render()

    def _on_link(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https"):
            self.open_url.emit(url)

    # Transcript

    def _render(self) -> None:
        bar = self.transcript.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 40
        if not self.turns:
            parts = ['<p style="color:#e6e9ef; font-size:15px; margin-top:6px"><b>Ask anything.</b></p>'
                     '<p style="color:#8a93a8">Quadro searches the web and answers with sources.</p>'
                     '<p style="color:#8a93a8">Try <i>What\'s new in Python 3.15?</i> or '
                     '<i>Best budget mechanical keyboards</i></p>']
        else:
            parts = []
            for turn in self.turns:
                if turn["role"] == "user":
                    parts.append('<table width="100%" cellpadding="10" style="margin-top:14px; margin-bottom:4px; '
                                 f'background-color:#1e2433"><tr><td style="color:#e6e9ef">'
                                 f'{html.escape(turn["text"])}</td></tr></table>')
                    continue
                parts.append('<p style="color:#bb9af7; font-weight:600; margin-top:12px; margin-bottom:2px">Quadro</p>')
                body = turn["text"].strip()
                if body:
                    parts.append(_markdown_to_html(body))
                elif not (turn["error"] or turn["note"]):
                    parts.append('<p style="color:#5d667c">…</p>')
                if turn["sources"]:
                    links = "".join(f'<li><a href="{html.escape(url, quote=True)}" style="color:{LINK_COLOR}">'
                                    f'{html.escape(title)}</a></li>' for title, url in turn["sources"])
                    parts.append('<p style="color:#8a93a8; margin-top:10px; margin-bottom:0">Sources</p>'
                                 f'<ol style="margin-top:2px">{links}</ol>')
                if turn["note"]:
                    parts.append(f'<p style="color:#8a93a8"><i>{html.escape(turn["note"])}</i></p>')
                if turn["error"]:
                    parts.append(f'<p style="color:#f7768e">{html.escape(turn["error"])}</p>')
        self.transcript.setHtml("".join(parts))
        if at_bottom or self.busy:
            bar.setValue(bar.maximum())
