"""
Quote graphic generator for the Manuscript agent.
Renders a book quote as a styled PNG for Instagram / TikTok / Pinterest — no
external API or paid image generation needed.
"""

from __future__ import annotations
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

GRAPHICS_DIR = Path(__file__).resolve().parent.parent / "data" / "quote_graphics"
GRAPHICS_DIR.mkdir(parents=True, exist_ok=True)

SIZES = {
    "square": (1080, 1080),      # Instagram feed / Pinterest square
    "vertical": (1080, 1920),    # IG Story / Reel / TikTok / Pinterest standard pin
}

THEMES = {
    "midnight": {"top": (13, 19, 33),  "bottom": (27, 16, 53),  "text": (242, 232, 213), "accent": (201, 162, 91)},
    "blush":    {"top": (247, 230, 224), "bottom": (251, 238, 233), "text": (74, 25, 66),  "accent": (196, 120, 141)},
    "zodiac":   {"top": (26, 11, 46),  "bottom": (5, 3, 10),    "text": (224, 195, 252), "accent": (212, 175, 140)},
}

FONT_PATHS_QUOTE = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]

FONT_PATHS_ATTRIBUTION = [
    "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
]


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _vertical_gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    width, height = size
    img = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=row)
    return img


def render_quote_graphic(
    quote: str,
    output_path: Path,
    theme: str = "midnight",
    size_name: str = "square",
    attribution: str = "",
) -> Path:
    """Render a quote as a styled PNG. Returns output_path."""
    palette = THEMES.get(theme, THEMES["midnight"])
    width, height = SIZES.get(size_name, SIZES["square"])

    img = _vertical_gradient((width, height), palette["top"], palette["bottom"])
    draw = ImageDraw.Draw(img)

    margin = int(width * 0.12)
    max_text_width = width - 2 * margin

    font_size = int(width * 0.075)
    quote_font = _load_font(FONT_PATHS_QUOTE, font_size)
    lines = _wrap_text(f"“{quote.strip()}”", quote_font, max_text_width, draw)

    line_height = int(font_size * 1.35)
    block_height = line_height * len(lines)

    attribution_font = _load_font(FONT_PATHS_ATTRIBUTION, int(font_size * 0.45))
    attribution_height = int(font_size * 0.9) if attribution else 0

    y = (height - block_height - attribution_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=quote_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=quote_font, fill=palette["text"])
        y += line_height

    if attribution:
        y += int(font_size * 0.25)
        attr_text = attribution if attribution.startswith("—") else f"— {attribution}"
        bbox = draw.textbbox((0, 0), attr_text, font=attribution_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), attr_text, font=attribution_font, fill=palette["accent"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return output_path
