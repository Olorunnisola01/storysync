"""Audio chunking for APIs with file-size limits."""

import subprocess
import tempfile
from pathlib import Path

from storysync.ffmpeg_paths import ffmpeg_path, ffprobe_path, no_window_kwargs


def get_audio_duration(audio_path):
    r = subprocess.run(
        [ffprobe_path(), '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
        capture_output=True, text=True, **no_window_kwargs())
    try:
        return float(r.stdout.strip())
    except Exception:
        return 600.0


def get_file_size_mb(path):
    return Path(path).stat().st_size / (1024 * 1024)


def needs_chunking(audio_path, max_mb=24):
    return get_file_size_mb(audio_path) > max_mb


def chunk_audio(audio_path, chunk_seconds=600, overlap=2.0):
    """
    Split audio into FLAC chunks via ffmpeg.
    Yields (chunk_path, time_offset_seconds).
    """
    duration = get_audio_duration(audio_path)
    tmp_dir = Path(tempfile.mkdtemp(prefix='storysync_chunk_'))
    offset = 0.0
    idx = 0

    while offset < duration - 0.1:
        out = tmp_dir / f'chunk_{idx:03d}.flac'
        cmd = [
            ffmpeg_path(), '-y', '-ss', str(max(0, offset - (overlap if idx else 0))),
            '-i', str(audio_path),
            '-t', str(chunk_seconds + overlap),
            '-ar', '16000', '-ac', '1', '-c:a', 'flac',
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, **no_window_kwargs())
        if result.returncode != 0 or not out.exists():
            break
        yield str(out), max(0, offset - (overlap if idx else 0))
        offset += chunk_seconds
        idx += 1

    return tmp_dir


def merge_word_lists(chunks, overlap=2.0):
    """Merge chunked word lists, deduplicating overlap region."""
    if not chunks:
        return [], []
    all_words, all_utts = [], []
    last_end = -1.0

    for words, utts, offset in chunks:
        for w in words:
            t = w['start'] + offset
            if t < last_end - 0.05:
                continue
            merged = dict(w)
            merged['start'] = t
            merged['end'] = w.get('end', w['start'] + 0.3) + offset
            all_words.append(merged)
            last_end = merged['end']

        for u in utts:
            merged = dict(u)
            merged['start'] = u['start'] + offset
            merged['end'] = u.get('end', u['start'] + 1) + offset
            if merged['start'] >= last_end - overlap:
                all_utts.append(merged)

    return all_words, all_utts