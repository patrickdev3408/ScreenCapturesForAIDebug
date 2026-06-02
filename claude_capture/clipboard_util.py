"""Windows clipboard helpers.

Uses Windows PowerShell (5.1, which defaults to a single-threaded apartment)
via System.Windows.Forms.Clipboard, so no extra Python dependency is needed.
"""

import subprocess


def _run_ps(script):
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Sta", "-Command", script],
            check=True,
            capture_output=True,
        )
        return True
    except Exception as exc:
        print(f"[clipboard] failed: {exc}")
        return False


def copy_image(path):
    """Put an image file onto the clipboard as a bitmap (pasteable into chats)."""
    p = path.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        f"$img=[System.Drawing.Image]::FromFile('{p}');"
        "[System.Windows.Forms.Clipboard]::SetImage($img);"
        "$img.Dispose()"
    )
    return _run_ps(script)


def copy_file(path):
    """Put a file (e.g. a PDF) onto the clipboard as a file drop, so it can be
    pasted as an attachment in apps that accept files."""
    p = path.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$col=New-Object System.Collections.Specialized.StringCollection;"
        f"$col.Add('{p}');"
        "[System.Windows.Forms.Clipboard]::SetFileDropList($col)"
    )
    return _run_ps(script)


def copy_text(text):
    """Put text onto the clipboard."""
    try:
        subprocess.run("clip", input=text.encode("utf-16-le"), check=True, shell=True)
        return True
    except Exception:
        return False
