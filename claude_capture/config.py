"""Central configuration for the Claude capture tool.

Edit values here, or override ANTHROPIC_API_KEY via the environment variable
of the same name (the env var takes precedence if set).
"""

import os

# --- Whisper / audio transcription ---
WHISPER_MODEL = "small"           # base | small | medium
AUDIO_CHUNK_SECONDS = 5           # how many seconds of audio to pull per capture
AUDIO_RING_SECONDS = 15           # rolling mic buffer length kept at all times
AUDIO_SAMPLE_RATE = 16000         # 16 kHz mono is what Whisper expects
AUDIO_CHANNELS = 1
AUDIO_FRAMES_PER_BUFFER = 1024
TRANSCRIBE_SILENCE_PAD = 0.5      # seconds of silence appended before transcription
                                  # so Whisper doesn't drop the final word(s)
VOICE_NOTE_STOP_SETTLE = 0.4      # seconds to keep capturing after you tap F8 to
                                  # stop, so the tail of your sentence isn't clipped

# --- Rolling capture intervals ---
ROLLING_SCREEN_INTERVAL = 0.5     # seconds between frames in rolling screen mode
ROLLING_AUDIO_INTERVAL = 3.0      # seconds between captures in rolling audio+screen mode

# --- Buffer behaviour ---
MAX_BUFFER_SIZE = 20              # max frames before oldest is dropped
CLEAR_BUFFER_AFTER_SEND = False   # whether to auto-clear after sending to Claude
DEDUP_THRESHOLD = 4               # max perceptual-hash bit difference to treat frames as identical

# --- Export ---
EXPORT_MODE = "grid"             # default export mode: grid | pdf
# F12 = export to clipboard (free, paste into chat). Alt+F12 = send to Claude API.

# --- Hotkeys ---
HOLD_THRESHOLD_MS = 300           # press held longer than this counts as a hold

# --- Claude API ---
CLAUDE_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
COPY_RESPONSE_TO_CLIPBOARD = True
MAX_API_RETRIES = 2               # extra attempts after the first failure
