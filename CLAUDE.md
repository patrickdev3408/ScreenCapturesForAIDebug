# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A Windows desktop tool that captures screen frames + microphone audio via global
hotkeys, buffers them locally, and exports an annotated **grid PNG** or **multi-page
PDF**. Primary use: quickly show Claude (in another session) what an app/game is
doing without manually screenshotting and typing explanations.

GitHub (private): https://github.com/patrickdev3408/ScreenCapturesForAIDebug
Shared with a few friends — keep setup dead-simple (clone → double-click).

## Layout

```
AIScreenHelper/                 <- repo root (git here)
├─ Start Capture.bat            <- self-bootstrapping launcher (creates venv + installs on 1st run)
├─ SETUP.txt                    <- friend-facing 2-step quick guide
├─ screen_audio_capture_spec.md <- original spec
└─ claude_capture/              <- the app
   ├─ main.py          # hotkey listener (win32 hook) + orchestration
   ├─ capture.py       # mss screen capture + rolling-capture thread
   ├─ audio.py         # sounddevice mic ring buffer + F8 recording + Faster-Whisper
   ├─ state.py         # shared thread-safe buffer (dedup, elapsed clock)
   ├─ export.py        # grid PNG (Mode A) / multi-page PDF (Mode B)
   ├─ sender.py        # Anthropic API send (Alt+F12 path)
   ├─ clipboard_util.py# Windows clipboard (image/file/text via PowerShell)
   ├─ config.py        # all tunables
   ├─ requirements.txt
   ├─ README.md        # full docs
   └─ .venv/           # gitignored; recreated by the launcher
```

## Hotkeys

| Key | Action |
|-----|--------|
| F8 tap | Voice note: screenshot + start recording; tap again to stop, transcribe, attach text to that frame |
| F9 tap / hold | Single / rolling screen capture |
| F10 tap | ~5 s audio chunk (from ring buffer) → transcribe |
| F11 tap / hold | Single / rolling screen + audio |
| F12 | Export → **copy to clipboard** (free; paste into chat) |
| Alt+F12 | Export → **send to Claude API** (paid; needs `ANTHROPIC_API_KEY`) |
| Shift+F12 | Toggle grid ↔ pdf |
| Ctrl+F12 | Clear buffer |

## Key architecture decisions (don't regress these)

- **Audio backend is `sounddevice`, NOT `pyaudio`.** pyaudio has no prebuilt wheel
  for current Python and needs a C++ compiler; sounddevice bundles PortAudio.
- **F8–F12 are SUPPRESSED at the OS hook level** (`win32_event_filter` +
  `suppress_event()` in `main.py`). Reason: otherwise holding F11 toggles the
  focused app's fullscreen on key-repeat ("screen shaking"), F12 opens dev tools,
  etc. pynput can't both fire `on_press` AND suppress per-key, so F-key handling
  lives in the filter, dispatched to a single worker thread (`_worker`) to keep the
  hook callback fast. Modifiers (Ctrl/Shift/Alt) are tracked but never suppressed.
- **Privacy: transcription is fully local.** Faster-Whisper downloads model weights
  from Hugging Face once, then `audio.py` sets `HF_HUB_OFFLINE=1` (via a filesystem
  cache check at import) so no network request is ever made again. Audio/screens are
  never uploaded. The ONLY outbound path is the optional Alt+F12 API call.
- **Default workflow is free:** F12 → clipboard → paste into claude.ai/Claude Code
  (covered by subscription). The API path is opt-in and billed separately.
- **Trailing-word fix:** Whisper clips final words on abrupt endings, so `transcribe`
  pads trailing silence (`TRANSCRIBE_SILENCE_PAD`) and F8-stop keeps capturing a
  short settle window (`VOICE_NOTE_STOP_SETTLE`).

## Config (claude_capture/config.py)

`WHISPER_MODEL` (currently `"small"`), audio chunk/ring seconds, rolling intervals,
`MAX_BUFFER_SIZE`, `EXPORT_MODE`, `CLAUDE_MODEL`, `ANTHROPIC_API_KEY` (env override),
and the two anti-clip knobs above.

## Running / testing

- Run the app: double-click `Start Capture.bat`, or
  `claude_capture/.venv/Scripts/python.exe claude_capture/main.py`.
- The global hotkey hook and the mic can't be exercised headless. Test logic by
  importing modules and calling functions with the venv python; mock `audio.*` for
  the mic and the win32 filter with a fake `_listener` exposing `suppress_event()`.
- Quick import check: `.venv/Scripts/python.exe -c "import main"`.

## Notes

- Windows-only (uses win32 hook + PowerShell clipboard). Platform target: Dell
  Precision 3591.
- CPU-only Whisper (no CUDA libs installed). A CPU-thread cap was discussed but not
  added — revisit if transcription stutters a game under test.
- Commit messages end with the Co-Authored-By trailer; commit/push only when asked.
