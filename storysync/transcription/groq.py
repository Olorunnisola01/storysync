"""Groq Whisper transcription provider."""

import json
from pathlib import Path

import requests

from storysync.transcription.chunking import chunk_audio, merge_word_lists, needs_chunking


GROQ_URL = 'https://api.groq.com/openai/v1/audio/transcriptions'

_CACHE_VERSION = 2


def transcribe(audio_path, api_key, language='de', model='whisper-large-v3',
               prompt=None, cache_path=None, force_refresh=False):
    if cache_path and Path(cache_path).exists() and not force_refresh:
        cached = json.loads(Path(cache_path).read_text(encoding='utf-8'))
        cache_ok = (
            cached.get('cache_version', 1) == _CACHE_VERSION
            and cached.get('provider') == 'groq'
            and cached.get('model') == model
        )
        if cache_ok:
            return cached.get('words', []), cached.get('utterances', [])

    if needs_chunking(audio_path, 24):
        chunks_data = []
        tmp_dir = None
        for chunk_path, offset in chunk_audio(audio_path, chunk_seconds=480):
            tmp_dir = Path(chunk_path).parent
            words, utts = _call_groq(
                chunk_path, api_key, language, model, prompt)
            chunks_data.append((words, utts, offset))
        words, utterances = merge_word_lists(chunks_data)
        if tmp_dir:
            for f in tmp_dir.glob('*.flac'):
                try:
                    f.unlink()
                except OSError:
                    pass
            try:
                tmp_dir.rmdir()
            except OSError:
                pass
    else:
        words, utterances = _call_groq(
            audio_path, api_key, language, model, prompt)

    if cache_path:
        Path(cache_path).write_text(json.dumps({
            'provider': 'groq', 'model': model, 'language': language,
            'cache_version': _CACHE_VERSION,
            'words': words, 'utterances': utterances,
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    return words, utterances


_AUDIO_MIME = {
    '.mp3': 'audio/mpeg',
    '.mp4': 'audio/mp4',
    '.m4a': 'audio/mp4',
    '.wav': 'audio/wav',
    '.flac': 'audio/flac',
    '.webm': 'audio/webm',
    '.ogg': 'audio/ogg',
    '.mpeg': 'audio/mpeg',
    '.mpga': 'audio/mpeg',
}


def _call_groq(audio_path, api_key, language, model, prompt):
    import time

    headers = {'Authorization': f'Bearer {api_key}'}
    # Note: no [] suffix — Groq expects OpenAI-style repeated keys without brackets.
    data = [
        ('model', model),
        ('language', language),
        ('response_format', 'verbose_json'),
        ('timestamp_granularities', 'word'),
        ('timestamp_granularities', 'segment'),
    ]
    if prompt:
        data.append(('prompt', prompt[:800]))  # Groq hard limit is 896 chars

    ext  = Path(audio_path).suffix.lower()
    mime = _AUDIO_MIME.get(ext, 'audio/mpeg')

    for attempt in range(3):
        try:
            # Re-open file each attempt so the file pointer is always at the start.
            with open(audio_path, 'rb') as f:
                files = {'file': (Path(audio_path).name, f, mime)}
                r = requests.post(
                    GROQ_URL, headers=headers, data=data, files=files,
                    timeout=600)

            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue

            if r.status_code >= 400:
                # Extract the actual Groq error message from the response body.
                try:
                    body = r.json()
                    msg = body.get('error', {}).get('message', r.text[:400])
                except Exception:
                    msg = r.text[:400]
                if r.status_code < 500:
                    # Client error — retrying will not help.
                    raise RuntimeError(f'Groq {r.status_code}: {msg}')
                if attempt == 2:
                    raise RuntimeError(f'Groq {r.status_code}: {msg}')
                time.sleep(2 ** attempt)
                continue

            return _parse_groq_response(r.json())

        except RuntimeError:
            raise
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    return [], []


def _parse_groq_response(data):
    words = []
    for w in data.get('words', []):
        words.append({
            'word': w.get('word', ''),
            'start': w['start'],
            'end': w.get('end', w['start'] + 0.2),
            'confidence': w.get('confidence', 0.9),
        })

    utterances = []
    for seg in data.get('segments', []):
        utterances.append({
            'transcript': seg.get('text', ''),
            'start': seg['start'],
            'end': seg.get('end', seg['start'] + 1),
        })

    if not utterances and words:
        utterances = [{
            'transcript': data.get('text', ''),
            'start': words[0]['start'],
            'end': words[-1]['end'],
        }]

    return words, utterances


def test_connection(api_key):
    try:
        r = requests.get(
            'https://api.groq.com/openai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=15)
        return r.status_code == 200, 'Connected' if r.status_code == 200 else r.text[:80]
    except Exception as e:
        return False, str(e)[:80]