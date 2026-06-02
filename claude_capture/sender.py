"""Send an exported capture (PNG or PDF) to Claude and print the feedback."""

import base64
import os
import time

import config

SYSTEM_PROMPT = (
    "You are a development assistant reviewing a sequence of annotated screen "
    "captures from a developer testing their application or game. Each frame "
    "includes a timestamp and optionally a voice transcript of what the developer "
    "was saying or noticing at that moment. Provide specific, actionable feedback "
    "on what you observe - bugs, UI issues, unexpected behavior, or anything worth "
    "flagging. Be concise and direct."
)


def _copy_to_clipboard(text):
    try:
        import subprocess
        # Windows clip.exe; harmless no-op elsewhere if missing.
        subprocess.run("clip", input=text.encode("utf-16-le"), check=True, shell=True)
        return True
    except Exception:
        return False


def _build_content_block(file_path, export_mode, user_context):
    with open(file_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("ascii")

    intro = (
        "Here is a sequence of annotated screen captures from my development session"
        + (f". Context: {user_context}" if user_context else ".")
    )

    if export_mode == "pdf":
        media_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    else:
        media_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": data},
        }

    return [{"type": "text", "text": intro}, media_block]


def send_to_claude(file_path, export_mode, user_context=""):
    """Read the exported file, send to Claude, print + return the response text."""
    api_key = config.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[sender] No ANTHROPIC_API_KEY set. Set it in config.py or the environment.")
        return None

    try:
        from anthropic import Anthropic
    except Exception as exc:
        print(f"[sender] anthropic SDK not installed: {exc}")
        return None

    client = Anthropic(api_key=api_key)
    content = _build_content_block(file_path, export_mode, user_context)

    last_exc = None
    for attempt in range(config.MAX_API_RETRIES + 1):
        try:
            print(f"[sender] Sending to Claude ({config.CLAUDE_MODEL})...")
            resp = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            text = "".join(block.text for block in resp.content if block.type == "text")
            print("\n" + "=" * 60)
            print("CLAUDE FEEDBACK")
            print("=" * 60)
            print(text)
            print("=" * 60 + "\n")

            if config.COPY_RESPONSE_TO_CLIPBOARD and _copy_to_clipboard(text):
                print("[sender] Response copied to clipboard.")
            return text
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            print(f"[sender] API error (attempt {attempt + 1}): {exc}")
            if attempt < config.MAX_API_RETRIES:
                print(f"[sender] Retrying in {wait}s...")
                time.sleep(wait)

    print(f"[sender] Failed after retries: {last_exc}")
    return None
