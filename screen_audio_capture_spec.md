# Screen + Audio Capture Tool for Claude Feedback

## Overview

Build a Python desktop tool that captures screen frames and microphone audio via hotkeys, buffers them locally, and sends them to Claude for feedback. The tool runs silently in the background while the user tests their app or game.

---

## Project Structure

```
claude_capture/
├── main.py          # Hotkey listener + orchestration
├── capture.py       # Screen capture + rolling logic
├── audio.py         # Mic buffer + Faster-Whisper transcription
├── export.py        # Grid PNG and multi-page PDF export
├── sender.py        # Claude API integration
└── requirements.txt
```

---

## Dependencies

```txt
mss
Pillow
pyaudio
faster-whisper
pynput
anthropic
fpdf2
numpy
```

---

## Hotkey Bindings

| Key | Action |
|-----|---------|
| `F9` (tap) | Single screen capture → add to buffer |
| `F9` (hold) | Rolling screen capture every 0.5 sec until released |
| `F10` (tap) | Single audio chunk (last ~5 sec) → transcribe → add to buffer |
| `F11` (tap) | Single screen + audio → add to buffer |
| `F11` (hold) | Rolling screen + audio every 3 sec until released |
| `F12` | Export buffer → send to Claude |
| `Shift+F12` | Toggle export mode (Grid PNG ↔ Multi-page PDF) |
| `Ctrl+F12` | Clear buffer without sending |

---

## Buffer Entry Format

Each item added to the buffer should be a dict:

```python
{
    "timestamp": "00:00:12",        # Elapsed time string
    "frame": <PIL.Image object>,    # Screenshot
    "transcript": "string or None"  # Whisper transcription if audio captured
}
```

- Max buffer size: **20 frames** (drop oldest when exceeded)
- Deduplicate frames using image hashing — skip a frame if it is visually identical to the previous one (use `ImageChops.difference` or a perceptual hash)

---

## Module Specs

### `capture.py`

- Use `mss` for fast screen capture
- `capture_screen()` → returns a `PIL.Image`
- `start_rolling_screen(interval=0.5)` → starts a background thread capturing every 0.5 sec, appending to buffer
- `stop_rolling()` → stops the rolling thread
- Frame deduplication: compare current frame hash to previous; skip if identical

### `audio.py`

- Use `pyaudio` to continuously record mic input into a rolling ring buffer (keep last 15 sec of audio at all times)
- `get_audio_chunk(seconds=5)` → pulls last N seconds from the rolling buffer, returns raw audio bytes
- `transcribe(audio_bytes)` → runs Faster-Whisper on the audio, returns transcript string
- Faster-Whisper model: use `"base"` by default, allow config to switch to `"small"` or `"medium"`
- Run transcription in a thread pool so it doesn't block the main loop

### `export.py`

Two export modes:

#### Mode A: Annotated Grid PNG
- Arrange buffer frames in a 2-column grid
- Each cell: frame image resized to fit, with a label bar below showing timestamp + transcript snippet (truncated to ~80 chars)
- Use `Pillow` to draw text labels with a dark background bar
- Output: single PNG file saved to a temp path

#### Mode B: Multi-Page PDF
- One page per buffer entry
- Full-size frame at top of page
- Timestamp and full transcript text printed below the image
- Use `fpdf2` for PDF generation
- Output: single PDF file saved to a temp path

Both modes should return the output file path.

### `sender.py`

- `send_to_claude(file_path, export_mode, user_context="")` 
- Read the exported file (PNG or PDF) and base64 encode it
- Send to Claude via the Anthropic Python SDK using `claude-sonnet-4-20250514`
- Include a system prompt that tells Claude it is receiving a sequence of annotated screen captures with voice commentary from a developer testing their app, and to provide specific, actionable feedback
- Print Claude's response to the terminal (and optionally copy to clipboard)
- Handle API errors gracefully with a retry on failure

### `main.py`

- Use `pynput` for hotkey detection
- Track hold vs tap with timestamps (hold = key held > 300ms)
- Maintain a global `buffer = []` and `export_mode = "grid"` (default)
- On `Shift+F12`: toggle `export_mode` between `"grid"` and `"pdf"`, print current mode to terminal
- On `Ctrl+F12`: clear buffer, print confirmation
- On `F12`: call `export.py` with current mode → call `sender.py` → optionally clear buffer after send (make this a configurable option)
- Print a status line to terminal on every action (e.g. `[00:00:12] Frame captured. Buffer: 3 items.`)

---

## Configuration (top of main.py or a config.py)

```python
WHISPER_MODEL = "base"          # base | small | medium
AUDIO_CHUNK_SECONDS = 5         # how many seconds of audio to pull per capture
ROLLING_SCREEN_INTERVAL = 0.5   # seconds between frames in rolling screen mode
ROLLING_AUDIO_INTERVAL = 3.0    # seconds between captures in rolling audio+screen mode
MAX_BUFFER_SIZE = 20            # max frames before oldest is dropped
CLEAR_BUFFER_AFTER_SEND = False # whether to auto-clear after sending to Claude
EXPORT_MODE = "grid"            # default export mode: grid | pdf
ANTHROPIC_API_KEY = ""          # or load from env var ANTHROPIC_API_KEY
```

---

## Claude System Prompt (in sender.py)

```
You are a development assistant reviewing a sequence of annotated screen captures from a developer testing their application or game. Each frame includes a timestamp and optionally a voice transcript of what the developer was saying or noticing at that moment. Provide specific, actionable feedback on what you observe — bugs, UI issues, unexpected behavior, or anything worth flagging. Be concise and direct.
```

---

## Notes

- The tool should work on Windows (primary target: Dell Precision 3591)
- All processing is local except the final Claude API call
- Faster-Whisper runs on GPU if CUDA is available, otherwise CPU fallback
- No GUI required — terminal output only
- Keep dependencies minimal and avoid anything that requires admin/elevated permissions to install
