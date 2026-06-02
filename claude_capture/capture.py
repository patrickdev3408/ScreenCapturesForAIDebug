"""Screen capture via mss, plus a background rolling-capture thread.

`mss` is not thread-safe across instances shared between threads, so each
capture path creates its own short-lived `mss.mss()` context.
"""

import threading
import time

import mss
from PIL import Image

import config
import state

_rolling_thread = None
_rolling_stop = None


def capture_screen():
    """Grab the primary monitor and return a PIL.Image (RGB)."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # monitors[0] is the virtual "all monitors" box
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _rolling_loop(interval, stop_event, on_capture):
    """Capture a frame every `interval` seconds until stop_event is set."""
    while not stop_event.is_set():
        start = time.monotonic()
        try:
            frame = capture_screen()
            if on_capture is not None:
                on_capture(frame)
            else:
                state.add_entry(frame)
        except Exception as exc:  # keep the thread alive on transient grab errors
            print(f"[rolling capture error] {exc}")
        # Sleep the remainder of the interval, accounting for capture time.
        elapsed = time.monotonic() - start
        stop_event.wait(max(0.0, interval - elapsed))


def start_rolling_screen(interval=None, on_capture=None):
    """Start a background thread capturing frames at `interval` seconds.

    `on_capture(frame)` is called per frame if provided; otherwise frames are
    added straight to the shared buffer. Returns False if already running.
    """
    global _rolling_thread, _rolling_stop
    if _rolling_thread is not None and _rolling_thread.is_alive():
        return False
    interval = interval if interval is not None else config.ROLLING_SCREEN_INTERVAL
    _rolling_stop = threading.Event()
    _rolling_thread = threading.Thread(
        target=_rolling_loop,
        args=(interval, _rolling_stop, on_capture),
        daemon=True,
    )
    _rolling_thread.start()
    return True


def stop_rolling():
    """Signal the rolling thread to stop and wait briefly for it to exit."""
    global _rolling_thread, _rolling_stop
    if _rolling_stop is not None:
        _rolling_stop.set()
    if _rolling_thread is not None:
        _rolling_thread.join(timeout=2.0)
    _rolling_thread = None
    _rolling_stop = None


def is_rolling():
    return _rolling_thread is not None and _rolling_thread.is_alive()
