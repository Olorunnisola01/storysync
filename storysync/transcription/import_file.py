"""Import word/utterance timestamps from a user-supplied JSON, SRT, or TXT file.

Lets a user skip Whisper/Deepgram API calls entirely by handing StorySync a
transcript they already have. Output shape matches the API providers exactly:

    words:      [{'word': str, 'start': float, 'end': float}, ...]
    utterances: [{'transcript': str, 'start': float, 'end': float}, ...]
"""

import json
import re
from pathlib import Path


def parse_transcript_file(path):
    """Parse *path* into (words, utterances). Format is chosen by extension.

    Supported layouts:
      .json — either the StorySync/Deepgram/Whisper cache shape
              {"words": [...], "utterances": [...]}, or a bare list of word
              dicts [{"word"/"text", "start", "end"}, ...].
      .srt  — standard SubRip subtitles. Word-level timing is synthesised by
              evenly spreading each subtitle line's words across its duration.
      .txt  — either
                "[start --> end] sentence text"  (one utterance per line), or
                "start,end,word" / "start<TAB>end<TAB>word"  (one word per line)
    """
    ext = Path(path).suffix.lower()
    text = Path(path).read_text(encoding='utf-8-sig')

    if ext == '.json':
        return _parse_json(text)
    if ext == '.srt':
        return _parse_srt(text)
    return _parse_txt(text)


def _norm_word(w):
    start = float(w.get('start', 0))
    end = float(w.get('end', start + 0.2))
    return {'word': str(w.get('word', w.get('text', ''))), 'start': start, 'end': end}


def _parse_json(text):
    data = json.loads(text)
    if isinstance(data, list):
        words = [_norm_word(w) for w in data]
        return words, _utterances_from_words(words)

    words = [_norm_word(w) for w in data.get('words', [])]
    utterances = [
        {'transcript': u.get('transcript', u.get('text', '')),
         'start': float(u['start']), 'end': float(u.get('end', u['start'] + 1.0))}
        for u in data.get('utterances', [])
    ]
    if not utterances:
        utterances = _utterances_from_words(words)
    return words, utterances


def _parse_ts(ts):
    """Parse 'HH:MM:SS,mmm' / 'MM:SS.mmm' / 'SS.mmm' into seconds."""
    parts = ts.strip().replace(',', '.').split(':')
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


_SRT_BLOCK_RE = re.compile(
    r'(?:^|\n)\s*\d+\s*\n(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*'
    r'(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)',
    re.DOTALL)

_TAG_RE = re.compile(r'<[^>]+>')


def _parse_srt(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    utterances = []
    for m in _SRT_BLOCK_RE.finditer('\n' + text + '\n\n'):
        start, end = _parse_ts(m.group(1)), _parse_ts(m.group(2))
        raw = m.group(3).strip()
        transcript = ' '.join(ln.strip() for ln in raw.splitlines() if ln.strip())
        transcript = _TAG_RE.sub('', transcript).strip()
        if transcript:
            utterances.append({'transcript': transcript, 'start': start, 'end': end})
    if not utterances:
        raise ValueError('No valid subtitle blocks found in this .srt file.')
    return _words_from_utterances(utterances), utterances


_BRACKET_LINE_RE = re.compile(
    r'^\s*\[?\s*(\d{1,2}(?::\d{2}){0,2}[.,]\d{1,3})\s*-->\s*'
    r'(\d{1,2}(?::\d{2}){0,2}[.,]\d{1,3})\s*\]?\s*(.*)$')

_CSV_ROW_RE = re.compile(r'^\s*([\d.]+)\s*[,\t]\s*([\d.]+)\s*[,\t]\s*(.+?)\s*$')


def _parse_txt(text):
    lines = [ln for ln in text.replace('\r\n', '\n').split('\n') if ln.strip()]
    if not lines:
        raise ValueError('Transcript file is empty.')

    bracket_hits = sum(1 for ln in lines if _BRACKET_LINE_RE.match(ln))
    csv_hits = sum(1 for ln in lines if _CSV_ROW_RE.match(ln))

    if bracket_hits >= max(1, len(lines) // 2):
        utterances = []
        for ln in lines:
            m = _BRACKET_LINE_RE.match(ln)
            if not m:
                continue
            start, end, txt = _parse_ts(m.group(1)), _parse_ts(m.group(2)), m.group(3).strip()
            if txt:
                utterances.append({'transcript': txt, 'start': start, 'end': end})
        return _words_from_utterances(utterances), utterances

    if csv_hits >= max(1, len(lines) // 2):
        words = []
        for ln in lines:
            m = _CSV_ROW_RE.match(ln)
            if not m:
                continue
            start, end, w = float(m.group(1)), float(m.group(2)), m.group(3).strip()
            if w:
                words.append({'word': w, 'start': start, 'end': end})
        return words, _utterances_from_words(words)

    raise ValueError(
        'Could not detect a transcript layout in this .txt file. Supported layouts:\n'
        '  [start --> end] sentence text     (one line per sentence)\n'
        '  start,end,word  or  start<TAB>end<TAB>word     (one line per word)'
    )


def _words_from_utterances(utterances):
    """Evenly distribute each utterance's words across its [start, end] span."""
    words = []
    for u in utterances:
        parts = u['transcript'].split()
        if not parts:
            continue
        span = max(0.05, u['end'] - u['start'])
        dt = span / len(parts)
        for i, w in enumerate(parts):
            words.append({
                'word': w,
                'start': u['start'] + i * dt,
                'end': u['start'] + (i + 1) * dt,
            })
    return words


def _utterances_from_words(words, gap_threshold=1.2):
    """Group consecutive words into utterances, splitting on large time gaps."""
    if not words:
        return []
    utterances = []
    cur = [words[0]]
    for w in words[1:]:
        if w['start'] - cur[-1]['end'] > gap_threshold:
            utterances.append(_make_utt(cur))
            cur = [w]
        else:
            cur.append(w)
    utterances.append(_make_utt(cur))
    return utterances


def _make_utt(word_group):
    return {
        'transcript': ' '.join(w['word'] for w in word_group),
        'start': word_group[0]['start'],
        'end': word_group[-1]['end'],
    }
