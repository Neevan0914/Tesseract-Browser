# Tesseract-Browser
A browser built to run fast on anything.

Tesseract is a small, modern web browser written in Python with PyQt6 and the
Chromium-based QtWebEngine.

## Features

- Address bar: press Enter to load a URL, or type words to search (DuckDuckGo).
  Bare hostnames like `example.com` default to HTTPS.
- The address bar follows the page, so it updates on link clicks, redirects and back/forward.
- Thin gradient loading bar. While a page loads, Reload turns into Stop.
- Back / Forward / Reload / Home buttons, which grey out when unavailable.
- Homepage showing "Tesseract" in Black Ops One. The font is bundled in
  `assets/fonts`, so it works offline.
- Tabs: each tab is its own Chromium page with a favicon (a spinner while loading).
  Tabs can be dragged to reorder.
  - New tab: the `+` button, `Ctrl+T`, or double-click empty tab-bar space.
  - Close: the `×` button, middle-click, or `Ctrl+W`. Closing the last tab closes the window.
  - Links with `target=_blank` open in a new tab next to the page that opened them.
    Middle-click or `Ctrl+click` opens one in the background.
  - The toolbar, address bar and loading bar always follow the selected tab.
- Keyboard shortcuts:

  | Keys | Action |
  | --- | --- |
  | `Ctrl+L` / `F6` | Focus the address bar |
  | `Ctrl+T` / `Ctrl+W` | New tab / close tab |
  | `Ctrl+Tab` / `Ctrl+Shift+Tab` (or `Ctrl+PgDown` / `Ctrl+PgUp`) | Next / previous tab |
  | `Ctrl+1` … `Ctrl+8`, `Ctrl+9` | Jump to tab N, or to the last tab |
  | `Alt+Left` / `Alt+Right` | Back / forward |
  | `F5` / `Esc` | Reload / stop |
  | `Alt+Home` | Home |
  | `Ctrl+J` | Open or close Quadro |

## Quadro, the AI search assistant

Quadro answers questions by searching the web with Claude (Claude Opus 5.5 with web
search) and lists the pages it used as sources. Click a source to open it in a new tab.
Ask follow-up questions in the same chat, or click **New chat** to start over.

- **Open it:** type a question in the homepage search bar and click **AI search**, or type
  in the address bar and click the sparkle icon at its right, or press `Ctrl+J`.
- **API key:** Quadro needs an Anthropic API key, which you can create at
  [console.anthropic.com](https://console.anthropic.com/settings/keys). Paste it when
  Quadro asks. It's saved for your user account (on Windows, in the registry under
  `HKEY_CURRENT_USER\Software\Tesseract`). Remove it any time with **API key**, then
  **Remove saved key**. If the `ANTHROPIC_API_KEY` environment variable is set, Quadro
  uses that instead.
- **Cost and privacy:** each question is sent to Anthropic and billed to the key's account
  (tokens plus web searches). Quadro only sends what you type into it, never your
  browsing history or the pages you have open.
- **Safety:** only Tesseract's own homepage can open Quadro. Websites can't use it or
  spend your API credits.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python browser.py
```

## Linux system dependencies

The PyQt6 wheels bundle Qt itself, but Qt's X11 (xcb) platform plugin still needs
a few system libraries. If you see
`qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`, install them.
On Debian/Ubuntu:

```bash
sudo apt-get install -y libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
  libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-xinerama0 \
  libxcb-shape0 libxcb-randr0 libxcb-xkb1 libxcb-xfixes0 libnss3 libasound2t64
```

To find out exactly which library is missing, run:

```bash
QT_DEBUG_PLUGINS=1 python browser.py
```

Other common issues:

| Symptom | Fix |
| --- | --- |
| `Running as root without --no-sandbox is not supported` | `browser.py` sets `QTWEBENGINE_DISABLE_SANDBOX=1` automatically when run as root. |
| `could not connect to display` (SSH or containers) | Run with a virtual display: `xvfb-run -a python browser.py` |
| Blank/black page, or GPU errors on VMs | `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu" python browser.py` |
| Wayland issues | `QT_QPA_PLATFORM=xcb python browser.py` |

On headless machines, log lines like `Failed to create Vulkan instance`,
`Failed to connect to the bus` and `Failed to send GpuControl.CreateCommandBuffer`
are harmless. They mean there's no GPU or D-Bus, and Chromium falls back to software rendering.

## License

The Black Ops One font is licensed under the SIL Open Font License 1.1.
