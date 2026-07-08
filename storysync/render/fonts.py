"""Font loading helpers with in-process cache (avoids re-reading TTF on every preview refresh)."""

import sys
import threading
from pathlib import Path

from PIL import ImageFont

from storysync.constants import FONT_FILES

_font_cache: dict = {}
_font_lock = threading.Lock()


def font_path(filename):
    if getattr(sys, 'frozen', False):
        p = Path(sys._MEIPASS) / 'fonts' / filename
        if p.exists():
            return str(p)
    win = Path(r'C:\Windows\Fonts') / filename
    if win.exists():
        return str(win)
    return None


def load_fonts(family='Georgia', size_body=34, size_heading=28, use_bold=True):
    """Return (font_body, font_heading).  Results are cached so repeated calls
    with the same params skip disk I/O entirely."""
    key = (family, size_body, size_heading, use_bold)
    with _font_lock:
        if key in _font_cache:
            return _font_cache[key]

    files = FONT_FILES.get(family, FONT_FILES['Georgia'])
    body_key = 'bold' if use_bold else 'regular'
    body_file = (font_path(files[body_key])
                 or font_path(files['bold'])
                 or font_path(files['regular']))
    head_file = font_path(files['bold']) or font_path(files['regular'])
    try:
        fb = ImageFont.truetype(body_file, size_body) if body_file else ImageFont.load_default()
        fh = ImageFont.truetype(head_file, size_heading) if head_file else ImageFont.load_default()
    except Exception:
        fb = fh = ImageFont.load_default()

    result = (fb, fh)
    with _font_lock:
        _font_cache[key] = result
    return result