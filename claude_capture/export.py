"""Export the capture buffer to either an annotated grid PNG or a multi-page PDF."""

import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

import config

# Grid layout tuning.
_GRID_COLS = 2
_CELL_W = 640                # target cell image width
_LABEL_H = 56                # height of the dark label bar under each frame
_PAD = 12                    # padding around cells
_LABEL_CHARS = 80            # transcript truncation for grid labels


def _load_font(size=16):
    """Try a few common fonts, falling back to PIL's default bitmap font."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _temp_path(suffix):
    fd, path = tempfile.mkstemp(prefix="claude_capture_", suffix=suffix)
    os.close(fd)
    return path


def _label_text(entry):
    ts = entry.get("timestamp", "")
    transcript = entry.get("transcript") or ""
    if transcript:
        snippet = transcript.replace("\n", " ")
        if len(snippet) > _LABEL_CHARS:
            snippet = snippet[: _LABEL_CHARS - 1] + "…"
        return f"[{ts}] {snippet}"
    return f"[{ts}]"


def export_grid(entries):
    """Mode A: arrange frames in a 2-column grid with labelled bars. Returns path."""
    if not entries:
        raise ValueError("Buffer is empty, nothing to export.")

    font = _load_font(16)

    # Resize each frame to a fixed cell width, preserving aspect ratio.
    cells = []
    for entry in entries:
        frame = entry["frame"]
        if frame is None:
            # Audio-only entry: render a placeholder cell.
            frame = Image.new("RGB", (_CELL_W, int(_CELL_W * 0.4)), (40, 40, 40))
        ratio = _CELL_W / frame.width
        cell_img_h = max(1, int(frame.height * ratio))
        img = frame.resize((_CELL_W, cell_img_h), Image.LANCZOS).convert("RGB")
        cells.append((img, _label_text(entry)))

    rows = (len(cells) + _GRID_COLS - 1) // _GRID_COLS

    # Row height is driven by the tallest image in that row + label bar.
    row_heights = []
    for r in range(rows):
        row_cells = cells[r * _GRID_COLS : (r + 1) * _GRID_COLS]
        max_img_h = max(img.height for img, _ in row_cells)
        row_heights.append(max_img_h + _LABEL_H)

    canvas_w = _GRID_COLS * _CELL_W + (_GRID_COLS + 1) * _PAD
    canvas_h = sum(row_heights) + (rows + 1) * _PAD
    canvas = Image.new("RGB", (canvas_w, canvas_h), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)

    y = _PAD
    idx = 0
    for r in range(rows):
        x = _PAD
        for c in range(_GRID_COLS):
            if idx >= len(cells):
                break
            img, label = cells[idx]
            canvas.paste(img, (x, y))
            # Dark label bar below the image.
            bar_top = y + img.height
            draw.rectangle([x, bar_top, x + _CELL_W, bar_top + _LABEL_H], fill=(10, 10, 10))
            draw.text((x + 8, bar_top + 8), label, fill=(235, 235, 235), font=font)
            x += _CELL_W + _PAD
            idx += 1
        y += row_heights[r] + _PAD

    path = _temp_path(".png")
    canvas.save(path, "PNG")
    return path


def export_pdf(entries):
    """Mode B: one page per entry — full frame + timestamp + full transcript. Returns path."""
    if not entries:
        raise ValueError("Buffer is empty, nothing to export.")

    from fpdf import FPDF

    pdf = FPDF(unit="pt", format="A4")
    pdf.set_auto_page_break(auto=True, margin=36)
    page_w = pdf.w - 72  # 36pt margins each side

    tmp_images = []
    try:
        for entry in entries:
            pdf.add_page()
            pdf.set_font("Helvetica", style="B", size=12)
            pdf.cell(0, 18, f"Timestamp: {entry.get('timestamp', '')}", ln=1)

            frame = entry["frame"]
            if frame is not None:
                img_path = _temp_path(".png")
                frame.convert("RGB").save(img_path, "PNG")
                tmp_images.append(img_path)
                disp_w = page_w
                disp_h = frame.height * (disp_w / frame.width)
                # Cap image height so transcript still fits on the page.
                max_h = pdf.h * 0.6
                if disp_h > max_h:
                    disp_h = max_h
                    disp_w = frame.width * (disp_h / frame.height)
                pdf.image(img_path, w=disp_w, h=disp_h)

            pdf.ln(10)
            pdf.set_font("Helvetica", size=11)
            transcript = entry.get("transcript") or "(no transcript)"
            pdf.multi_cell(0, 15, _latin1_safe(transcript))

        path = _temp_path(".pdf")
        pdf.output(path)
        return path
    finally:
        for p in tmp_images:
            try:
                os.remove(p)
            except OSError:
                pass


def _latin1_safe(text):
    """fpdf2 core fonts are latin-1 only; drop characters it can't encode."""
    return text.encode("latin-1", "replace").decode("latin-1")


def export_buffer(entries, mode):
    """Dispatch to the correct exporter. Returns (path, mode)."""
    if mode == "pdf":
        return export_pdf(entries), "pdf"
    return export_grid(entries), "grid"
