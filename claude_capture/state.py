"""Shared capture buffer and helpers.

Kept in its own module so both `capture.py` (background threads appending
frames) and `main.py` (hotkey orchestration) can touch the same buffer
without a circular import. All buffer mutation goes through the lock.
"""

import threading
import time

from PIL import Image

import config

# The buffer: list of dicts {"timestamp": str, "frame": PIL.Image, "transcript": str|None}
buffer = []
_lock = threading.RLock()
_start_time = time.monotonic()
_last_hash = None  # perceptual hash of the most recently *stored* frame


def reset_clock():
    """Reset the elapsed-time origin (called once at startup)."""
    global _start_time
    _start_time = time.monotonic()


def elapsed_str():
    """Return elapsed time since startup as HH:MM:SS."""
    secs = int(time.monotonic() - _start_time)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _average_hash(image, size=8):
    """Compute a 64-bit average hash (perceptual hash) of an image."""
    small = image.convert("L").resize((size, size), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= avg:
            bits |= (1 << i)
    return bits


def _hamming(a, b):
    return bin(a ^ b).count("1")


def add_entry(frame, transcript=None, dedup=True):
    """Add a frame (+optional transcript) to the buffer.

    Returns (added: bool, count: int, entry: dict|None). `added` is False when
    the frame was skipped as a near-duplicate of the previous one, in which case
    `entry` is None.
    """
    global _last_hash
    with _lock:
        if dedup and frame is not None:
            h = _average_hash(frame)
            if _last_hash is not None and _hamming(h, _last_hash) <= config.DEDUP_THRESHOLD:
                return (False, len(buffer), None)
            _last_hash = h

        entry = {
            "timestamp": elapsed_str(),
            "frame": frame,
            "transcript": transcript,
        }
        buffer.append(entry)

        # Drop oldest beyond the cap.
        while len(buffer) > config.MAX_BUFFER_SIZE:
            buffer.pop(0)

        return (True, len(buffer), entry)


def set_transcript(entry, text):
    """Set the transcript on a specific entry reference (thread-safe)."""
    with _lock:
        if entry is not None:
            entry["transcript"] = text


def attach_transcript(text):
    """Attach a transcript to the most recent entry (used when audio finishes
    transcribing after its frame was already buffered)."""
    with _lock:
        if buffer:
            buffer[-1]["transcript"] = text


def snapshot():
    """Return a shallow copy of the buffer for export (so it can't mutate mid-export)."""
    with _lock:
        return list(buffer)


def clear():
    global _last_hash
    with _lock:
        buffer.clear()
        _last_hash = None


def count():
    with _lock:
        return len(buffer)
