"""Microphone ring buffer + Faster-Whisper transcription.

Audio is captured with `sounddevice` (PortAudio): a callback continuously
pushes mic chunks into a fixed-length deque so the last ~15 seconds is always
available. Transcription runs on a thread pool so it never blocks the hotkey
loop.

(The spec named pyaudio, but pyaudio has no prebuilt wheel for current Python
and needs a C++ compiler to build; sounddevice provides the same capability
with a bundled PortAudio binary and no build step.)
"""

import collections
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import config

# Privacy / quiet-down for huggingface_hub (used only to fetch the Whisper model
# the first time). These must be set BEFORE faster_whisper / huggingface_hub are
# imported, so they live at module top and use a pure-filesystem cache check
# (importing huggingface_hub here would lock in its env-derived constants first).
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _hf_hub_cache_dir():
    """Resolve the huggingface hub cache directory the same way the library does,
    honouring HF_HUB_CACHE / HF_HOME overrides, without importing the library."""
    if os.environ.get("HF_HUB_CACHE"):
        return os.environ["HF_HUB_CACHE"]
    if os.environ.get("HF_HOME"):
        return os.path.join(os.environ["HF_HOME"], "hub")
    return os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")


def _model_is_cached():
    """True if the Whisper model weights are already present on disk."""
    repo = f"models--Systran--faster-whisper-{config.WHISPER_MODEL}"
    snapshots = os.path.join(_hf_hub_cache_dir(), repo, "snapshots")
    try:
        return os.path.isdir(snapshots) and any(os.scandir(snapshots))
    except OSError:
        return False


# If the model is already cached, force fully-offline mode: huggingface_hub will
# make NO network requests at all (and the "unauthenticated requests to the HF
# Hub" notice disappears). We only leave it online when the model genuinely needs
# its one-time download.
if _model_is_cached():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_stream = None
_ring = None
_ring_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)

# Arbitrary-length recording (F8 voice note): while active, every mic chunk is
# accumulated here in addition to the ring buffer, so a recording can be any length.
_recording = False
_record_chunks = []
_record_lock = threading.Lock()

# Lazily-loaded Whisper model (loading "base" can take a few seconds).
_model = None
_model_lock = threading.Lock()

_available = False  # set True once the mic stream starts successfully


def start():
    """Open the mic and begin filling the ring buffer. Safe to call once."""
    global _stream, _ring, _available
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"[audio] sounddevice unavailable, audio capture disabled: {exc}")
        return False

    # Number of chunks needed to hold AUDIO_RING_SECONDS of audio.
    max_chunks = math.ceil(
        config.AUDIO_RING_SECONDS * config.AUDIO_SAMPLE_RATE / config.AUDIO_FRAMES_PER_BUFFER
    )
    _ring = collections.deque(maxlen=max_chunks)

    def _callback(indata, frames, time_info, status_):
        if status_:
            # Overflows etc. are non-fatal; just note them.
            pass
        # indata is int16 (channels last); store raw bytes.
        chunk = bytes(indata)
        with _ring_lock:
            _ring.append(chunk)
        if _recording:
            with _record_lock:
                _record_chunks.append(chunk)

    try:
        _stream = sd.RawInputStream(
            samplerate=config.AUDIO_SAMPLE_RATE,
            blocksize=config.AUDIO_FRAMES_PER_BUFFER,
            channels=config.AUDIO_CHANNELS,
            dtype="int16",
            callback=_callback,
        )
        _stream.start()
    except Exception as exc:
        print(f"[audio] could not open microphone, audio capture disabled: {exc}")
        return False

    _available = True
    return True


def is_available():
    return _available


def get_audio_chunk(seconds=None):
    """Return the last `seconds` of raw int16 audio bytes from the ring buffer."""
    if not _available or _ring is None:
        return b""
    seconds = seconds if seconds is not None else config.AUDIO_CHUNK_SECONDS
    chunks_needed = math.ceil(
        seconds * config.AUDIO_SAMPLE_RATE / config.AUDIO_FRAMES_PER_BUFFER
    )
    with _ring_lock:
        recent = list(_ring)[-chunks_needed:]
    return b"".join(recent)


def is_recording():
    return _recording


def start_recording():
    """Begin accumulating mic audio for an arbitrary-length voice note."""
    global _recording
    if not _available:
        return False
    with _record_lock:
        _record_chunks.clear()
        _recording = True
    return True


def stop_recording():
    """Stop accumulating and return the full recording as raw int16 bytes."""
    global _recording
    with _record_lock:
        _recording = False
        data = b"".join(_record_chunks)
        _record_chunks.clear()
    return data


def recording_seconds(data):
    """Helper: duration in seconds of a raw int16 mono byte string."""
    return len(data) / (config.AUDIO_SAMPLE_RATE * 2)


def _get_model():
    global _model
    with _model_lock:
        if _model is not None:
            return _model

        from faster_whisper import WhisperModel

        # 1. Try to load from the local cache with NO network access at all.
        #    GPU first (float16), then CPU (int8). A failure here can mean either
        #    "no GPU" or "not cached" — both just fall through to the next option.
        for device, compute in (("cuda", "float16"), ("cpu", "int8")):
            try:
                _model = WhisperModel(
                    config.WHISPER_MODEL, device=device, compute_type=compute, local_files_only=True
                )
                print(f"[audio] Whisper '{config.WHISPER_MODEL}' loaded from local cache on {device.upper()}.")
                return _model
            except Exception:
                continue

        # 2. Genuine cache miss: download the weights once, then load on CPU.
        print(
            f"[audio] Whisper '{config.WHISPER_MODEL}' not cached — downloading the model "
            "weights from Hugging Face this once. Your audio is NOT uploaded; only the "
            "model files are downloaded. After this it runs fully offline."
        )
        _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        print(f"[audio] Whisper '{config.WHISPER_MODEL}' loaded on CPU.")
        return _model


def transcribe(audio_bytes):
    """Run Faster-Whisper on raw int16 mono bytes. Returns a transcript string."""
    if not audio_bytes:
        return ""
    try:
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        model = _get_model()
        segments, _info = model.transcribe(audio, language=None, beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
    except Exception as exc:
        print(f"[audio] transcription error: {exc}")
        return ""


def transcribe_async(audio_bytes, callback):
    """Transcribe off the main loop; call `callback(text)` when done."""
    def _job():
        callback(transcribe(audio_bytes))

    _executor.submit(_job)


def stop():
    global _stream
    try:
        if _stream is not None:
            _stream.stop()
            _stream.close()
    except Exception:
        pass
    _executor.shutdown(wait=False)
