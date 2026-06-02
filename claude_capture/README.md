# Claude Screen + Audio Capture

A background desktop tool that captures screen frames and microphone audio via
hotkeys, buffers them locally, and sends an annotated grid/PDF to Claude for
feedback. Useful for quickly showing Claude what your app/game is doing without
manually taking screenshots and typing explanations.

## Quick start (Windows)

1. Install **Python 3.11+** from <https://www.python.org/downloads/> — during
   install, tick **"Add python.exe to PATH"**. (Skip if you already have it.)
2. Download this repo: green **Code** button → **Download ZIP**, then unzip.
   (Or `git clone https://github.com/patrickdev3408/ScreenCapturesForAIDebug.git`.)
3. Double-click **`Start Capture.bat`**.

That's it. The first launch sets everything up automatically (creates a Python
environment and installs dependencies — a one-time few-minute wait). Every launch
after that starts instantly. Capture with the hotkeys below, press **F12** to copy
to your clipboard, and **Ctrl+V** it into your Claude chat.

> You do **not** need an API key for the normal (F12 → clipboard) workflow.

## Hotkeys

| Key | Action |
|-----|--------|
| `F8` tap | **Voice note:** grab a screenshot + start recording; tap again to stop, transcribe, and attach the text to that frame |
| `F9` tap | Single screen capture |
| `F9` hold | Rolling screen capture (every 0.5 s) until released |
| `F10` tap | Single audio chunk (~5 s) → transcribe → buffer |
| `F11` tap | Single screen + audio |
| `F11` hold | Rolling screen + audio (every 3 s) until released |
| `F12` | Export buffer → **copy to clipboard** so you can paste it into a chat (free) |
| `Alt+F12` | Export buffer → **send to Claude API** and print feedback (uses API credits) |
| `Shift+F12` | Toggle export mode (Grid PNG ↔ Multi-page PDF) |
| `Ctrl+F12` | Clear buffer without sending |
| `Ctrl+C` (in terminal) | Quit |

## Setup

```powershell
cd claude_capture
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set your API key (PowerShell):

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

…or edit `ANTHROPIC_API_KEY` in `config.py`.

## Run

```powershell
python main.py
```

The tool runs in the terminal and listens for the global hotkeys while you use
any other app. Status lines print on every action.

## Clipboard vs API — and cost

- **F12 → clipboard (free).** Exports the buffer and copies it to the clipboard.
  In **grid** mode the PNG is copied as an image, so you just press **Ctrl+V** in
  your Claude chat (claude.ai or Claude Code) to paste it — covered by your normal
  subscription, no API key needed. In **pdf** mode the file is copied as a file
  attachment instead.
- **Alt+F12 → Claude API (paid).** Sends the export to Claude via the Anthropic
  API and prints feedback in the terminal. This is billed per-token on a
  pay-as-you-go API account and is **not** covered by a Claude.ai subscription, so
  it needs `ANTHROPIC_API_KEY`.

Tip: keep export mode on **grid** for the paste-into-chat workflow — a single
image pastes cleanly into web/desktop chats, whereas a PDF only pastes into apps
that accept file attachments.

## A note on the hotkeys

While the tool is running, **F9–F12 are captured globally and suppressed** — they
drive the capture tool and do *not* reach whatever app is focused. This is
deliberate: otherwise holding **F11** would toggle the focused app in and out of
fullscreen on every key-repeat (the "screen shaking" effect), and F12 would open
browser dev tools. Modifier keys (Ctrl/Shift/Alt) are never suppressed, so normal
typing is unaffected.

The trade-off: if you rely on F9–F12 for something else (e.g. F12 dev tools, F11
fullscreen), quit the capture tool (Ctrl+C in its window) to get those keys back.

## Privacy

All capture and transcription happens locally. Faster-Whisper downloads its
model weights from Hugging Face **once** (the first run), then loads from the
local cache with no network access — your audio and screenshots are never
uploaded. The only outbound data path is the optional **Alt+F12** API call.

## Configuration

All tunables live in `config.py`: Whisper model size, audio chunk length,
rolling intervals, max buffer size, default export mode, whether to auto-clear
after export, and the Claude model.

## Notes

- All processing is local except the final Claude API call.
- Faster-Whisper uses GPU (CUDA) if available, otherwise falls back to CPU.
- The first transcription loads the Whisper model and may take a few seconds.
- No admin/elevated permissions required.

### Audio backend

The microphone is captured with `sounddevice` (bundled PortAudio) rather than
`pyaudio`. pyaudio has no prebuilt wheel for current Python versions and would
require the Visual C++ Build Tools to compile; sounddevice installs as a wheel
with no build step and provides the same capability. The transcription API
(`get_audio_chunk` / `transcribe`) is unchanged.
