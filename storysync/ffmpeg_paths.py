"""Locating the ffmpeg/ffprobe binaries.

The packaged exe ships its own ffmpeg and ffprobe so it works on a machine with
nothing installed. When frozen, PyInstaller unpacks them into sys._MEIPASS and
we call those directly; running from source, we fall back to whatever is on
PATH.
"""

import os
import subprocess
import sys
from pathlib import Path


def _bundled(name):
    """Path to a binary shipped inside the one-file exe, if it is there."""
    base = getattr(sys, '_MEIPASS', None)
    if not base:
        return None
    candidate = Path(base) / name
    return str(candidate) if candidate.exists() else None


def ffmpeg_path():
    return _bundled('ffmpeg.exe') or 'ffmpeg'


def ffprobe_path():
    return _bundled('ffprobe.exe') or 'ffprobe'


# Keeps the console window from flashing up on every subprocess call in the
# windowed build, where there is no console to reuse.
def no_window_kwargs():
    if os.name != 'nt':
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        'startupinfo': startupinfo,
        'creationflags': subprocess.CREATE_NO_WINDOW,
    }
