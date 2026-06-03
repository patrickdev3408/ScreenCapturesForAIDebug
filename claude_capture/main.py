"""Hotkey listener + orchestration for the Claude screen/audio capture tool.

Hotkeys (see README / spec):
  F8  tap        toggle a voice note: grab one screenshot + start recording;
                 tap again to stop, transcribe, and attach the text to that frame
  F9  tap        single screen capture
  F9  hold       rolling screen capture (every ROLLING_SCREEN_INTERVAL s)
  F10 tap        single audio chunk -> transcribe -> add to buffer
  F11 tap        single screen + audio
  F11 hold       rolling screen + audio (every ROLLING_AUDIO_INTERVAL s)
  F12            export buffer -> copy to clipboard
  Alt+F12        export buffer -> send to Claude API
  Shift+F12      toggle export mode (grid <-> pdf)
  Ctrl+F12       clear buffer without sending

F8-F12 are intercepted at the OS hook level and SUPPRESSED, so they drive this
tool only and never leak to the focused app (F11 = fullscreen, F12 = dev tools,
etc.). Modifier keys are watched but never suppressed, so typing is unaffected.
"""

import queue
import threading
import time

from pynput import keyboard

import config
import capture
import audio
import export
import sender
import state
import clipboard_util

export_mode = config.EXPORT_MODE

# --- Low-level key identity (Windows virtual-key codes) ---
_VK = {0x77: "f8", 0x78: "f9", 0x79: "f10", 0x7A: "f11", 0x7B: "f12"}

# WM_KEYDOWN / WM_SYSKEYDOWN (the SYS* variants fire while Alt is held, e.g. Alt+F12)
# and their key-up counterparts.
_WM_DOWN = {0x100, 0x104}
_WM_UP = {0x101, 0x105}

# Modifier virtual-key codes (generic + left/right variants). Watched, never suppressed.
_CTRL_VK = {0x11, 0xA2, 0xA3}
_SHIFT_VK = {0x10, 0xA0, 0xA1}
_ALT_VK = {0x12, 0xA4, 0xA5}
_MOD_VK = _CTRL_VK | _SHIFT_VK | _ALT_VK

_mods = set()            # modifier vkCodes currently down
_phys_down = set()       # our f-key vkCodes currently physically down (dedupes auto-repeat)

# Per-key hold-detection state (keyed by name "f9" / "f11").
_held = set()
_hold_timers = {}        # name -> threading.Timer pending hold activation
_hold_active = {}        # name -> bool, True once rolling started for that key
_simple_held = set()     # "f8" / "f10" / "f12" guard so a press fires once

_listener = None         # set in main(); the filter calls _listener.suppress_event()
_voice_entry = None      # buffer entry the current F8 voice note will attach to
_voice_stopping = False  # True while an F8 stop is settling/transcribing


# --------------------------------------------------------------------------
# Status helpers
# --------------------------------------------------------------------------

def status(msg):
    print(f"[{state.elapsed_str()}] {msg}")


def _buf(msg):
    status(f"{msg} Buffer: {state.count()} items.")


# --------------------------------------------------------------------------
# Capture actions
# --------------------------------------------------------------------------

def single_screen():
    frame = capture.capture_screen()
    added, count, _ = state.add_entry(frame)
    if added:
        _buf("Frame captured.")
    else:
        status(f"Frame skipped (duplicate). Buffer: {count} items.")


def single_audio():
    if not audio.is_available():
        status("Audio capture unavailable (no mic / pyaudio).")
        return
    chunk = audio.get_audio_chunk(config.AUDIO_CHUNK_SECONDS)
    # Audio-only entry: no frame, transcript filled in when ready.
    _, _, entry = state.add_entry(None, transcript="(transcribing...)", dedup=False)
    _buf("Audio captured, transcribing...")

    def _done(text):
        state.set_transcript(entry, text or "(no speech detected)")
        status(f'Transcript: "{text[:80]}"' if text else "Transcript: (no speech detected)")

    audio.transcribe_async(chunk, _done)


def single_screen_audio():
    frame = capture.capture_screen()
    added, count, entry = state.add_entry(frame)
    if not added:
        status(f"Frame skipped (duplicate). Buffer: {count} items.")
        return
    _buf("Frame + audio captured.")
    if audio.is_available():
        chunk = audio.get_audio_chunk(config.AUDIO_CHUNK_SECONDS)

        def _done(text):
            state.set_transcript(entry, text)
            if text:
                status(f'Transcript attached: "{text[:80]}"')

        audio.transcribe_async(chunk, _done)


def toggle_voice_note():
    """F8: first tap grabs a screenshot AND starts recording; second tap stops,
    transcribes the whole recording, and attaches the text to that screenshot."""
    global _voice_entry, _voice_stopping
    if not audio.is_available():
        status("Voice note needs a microphone — audio is unavailable.")
        return
    if _voice_stopping:
        return  # a previous stop is still settling/transcribing

    if not audio.is_recording():
        # START: capture the frame now, then record until the next F8.
        frame = capture.capture_screen()
        _, count, entry = state.add_entry(
            frame, transcript="(recording voice note...)", dedup=False
        )
        _voice_entry = entry
        audio.start_recording()
        status(f"[REC] Screenshot taken + recording voice note... tap F8 to stop. Buffer: {count} items.")
    else:
        # STOP: let the tail of the sentence land, then transcribe and attach to
        # the frame grabbed at start. Done on a thread so the hotkey loop is free.
        _voice_stopping = True
        entry = _voice_entry
        _voice_entry = None
        status("Voice note stopping...")

        def _finish():
            global _voice_stopping
            try:
                time.sleep(config.VOICE_NOTE_STOP_SETTLE)  # keep capturing the tail
                data = audio.stop_recording()
                secs = audio.recording_seconds(data)
                status(f"Voice note captured ({secs:.1f}s), transcribing...")
                text = audio.transcribe(data)
                state.set_transcript(entry, text or "(no speech detected)")
                if text:
                    status(f'Voice note attached: "{text[:80]}"')
                else:
                    status("Voice note: (no speech detected)")
            finally:
                _voice_stopping = False

        threading.Thread(target=_finish, daemon=True).start()


def _rolling_screen_audio_capture(frame):
    """on_capture callback for F11 hold: add frame, then transcribe recent audio."""
    added, _count, entry = state.add_entry(frame)
    if not added:
        return
    _buf("Rolling frame + audio captured.")
    if audio.is_available():
        chunk = audio.get_audio_chunk(config.AUDIO_CHUNK_SECONDS)
        audio.transcribe_async(chunk, lambda text: state.set_transcript(entry, text))


# --------------------------------------------------------------------------
# Hold / tap dispatch
# --------------------------------------------------------------------------

def _begin_hold(name):
    """Fired by the hold timer if the key is still down past the threshold."""
    if name not in _held:
        return
    _hold_active[name] = True
    if name == "f9":
        if capture.start_rolling_screen(config.ROLLING_SCREEN_INTERVAL):
            status("Rolling screen capture STARTED (release F9 to stop).")
    elif name == "f11":
        if capture.start_rolling_screen(
            config.ROLLING_AUDIO_INTERVAL, on_capture=_rolling_screen_audio_capture
        ):
            status("Rolling screen+audio capture STARTED (release F11 to stop).")


def _taphold_down(name):
    if name in _held:
        return  # ignore auto-repeat
    _held.add(name)
    _hold_active[name] = False
    timer = threading.Timer(config.HOLD_THRESHOLD_MS / 1000.0, _begin_hold, args=(name,))
    _hold_timers[name] = timer
    timer.start()


def _taphold_up(name):
    _held.discard(name)
    timer = _hold_timers.pop(name, None)
    if timer is not None:
        timer.cancel()

    if _hold_active.get(name):
        _hold_active[name] = False
        capture.stop_rolling()
        status("Rolling capture STOPPED.")
    else:
        # It was a tap.
        if name == "f9":
            single_screen()
        elif name == "f11":
            single_screen_audio()


# --------------------------------------------------------------------------
# F12 family + F10
# --------------------------------------------------------------------------

def _do_export(to_clipboard, to_api):
    entries = state.snapshot()
    if not entries:
        status("Buffer empty, nothing to export.")
        return
    try:
        path, mode = export.export_buffer(entries, export_mode)
        status(f"Exported {len(entries)} entries as {mode.upper()} -> {path}")
    except Exception as exc:
        status(f"Export failed: {exc}")
        return

    # Run anything slow (PowerShell clipboard call, network) off the listener
    # thread so hotkeys stay responsive.
    def _handle():
        if to_clipboard:
            if mode == "grid":
                if clipboard_util.copy_image(path):
                    status("Copied image to clipboard — paste into your chat with Ctrl+V.")
            else:  # pdf can't be pasted as an image; copy it as a file attachment
                if clipboard_util.copy_file(path):
                    status("Copied PDF file to clipboard — paste it into a chat that accepts files.")
        if to_api:
            sender.send_to_claude(path, mode)
        if config.CLEAR_BUFFER_AFTER_SEND:
            state.clear()
            status("Buffer cleared after export.")

    threading.Thread(target=_handle, daemon=True).start()


def _toggle_mode():
    global export_mode
    export_mode = "pdf" if export_mode == "grid" else "grid"
    status(f"Export mode -> {export_mode.upper()}")


def _on_f12():
    if _mods & _CTRL_VK:
        state.clear()
        status("Buffer cleared.")
    elif _mods & _SHIFT_VK:
        _toggle_mode()
    elif _mods & _ALT_VK:
        _do_export(to_clipboard=False, to_api=True)
    else:
        _do_export(to_clipboard=True, to_api=False)


# --------------------------------------------------------------------------
# Low-level input: a single worker thread runs the key logic so the OS hook
# callback stays fast, and a win32 event filter suppresses our keys.
# --------------------------------------------------------------------------

_event_q = queue.Queue()


def _key_down(name):
    if name in ("f9", "f11"):
        _taphold_down(name)
    elif name == "f8":
        if "f8" in _simple_held:
            return
        _simple_held.add("f8")
        toggle_voice_note()
    elif name == "f10":
        if "f10" in _simple_held:
            return
        _simple_held.add("f10")
        single_audio()
    elif name == "f12":
        if "f12" in _simple_held:
            return
        _simple_held.add("f12")
        _on_f12()


def _key_up(name):
    if name in ("f9", "f11"):
        _taphold_up(name)
    else:
        _simple_held.discard(name)


def _worker():
    """Serializes key handling off the OS hook thread (preserves down/up order)."""
    while True:
        item = _event_q.get()
        if item is None:
            return
        kind, name = item
        try:
            if kind == "down":
                _key_down(name)
            else:
                _key_up(name)
        except Exception as exc:
            status(f"Hotkey handler error: {exc}")


def _win32_filter(msg, data):
    """Runs in the OS keyboard-hook thread for every key event. Tracks modifier
    state, and for our F9-F12 keys enqueues the action then SUPPRESSES the event
    so it never reaches the focused application."""
    vk = data.vkCode
    if vk in _MOD_VK:
        if msg in _WM_DOWN:
            _mods.add(vk)
        elif msg in _WM_UP:
            _mods.discard(vk)
        return  # never suppress modifiers
    if vk in _VK:
        name = _VK[vk]
        if msg in _WM_DOWN:
            if vk not in _phys_down:        # drop auto-repeat
                _phys_down.add(vk)
                _event_q.put(("down", name))
        elif msg in _WM_UP:
            _phys_down.discard(vk)
            _event_q.put(("up", name))
        _listener.suppress_event()          # raises -> blocks propagation to other apps
    # any other key: let it through untouched


def _noop(*_args):
    return None


def _print_banner():
    print("=" * 60)
    print(" Claude Screen + Audio Capture")
    print("=" * 60)
    print(f" Export mode : {export_mode.upper()}")
    print(f" Whisper     : {config.WHISPER_MODEL}")
    print(f" Audio       : {'ready' if audio.is_available() else 'UNAVAILABLE'}")
    print(f" API key     : {'set' if (config.ANTHROPIC_API_KEY) else 'NOT SET'}")
    print("-" * 60)
    print(" F8  tap        voice note: screenshot + record; tap again to stop & attach")
    print(" F9  tap/hold   single / rolling screen")
    print(" F10 tap        audio chunk -> transcribe")
    print(" F11 tap/hold   single / rolling screen + audio")
    print(" F12            export -> COPY TO CLIPBOARD (paste into chat, free)")
    print(" Alt+F12        export -> send to Claude API (costs API credits)")
    print(" Shift+F12      toggle grid <-> pdf")
    print(" Ctrl+F12       clear buffer")
    print(" Ctrl+C (here)  quit")
    print("=" * 60)


def main():
    global _listener
    state.reset_clock()
    audio.start()
    _print_banner()

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()

    _listener = keyboard.Listener(
        on_press=_noop, on_release=_noop, win32_event_filter=_win32_filter
    )
    _listener.start()
    try:
        _listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        capture.stop_rolling()
        audio.stop()
        _event_q.put(None)
        print("\nShutting down. Bye.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        capture.stop_rolling()
        audio.stop()
        print("\nShutting down. Bye.")
