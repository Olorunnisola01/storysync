"""Deepgram transcription provider."""

import json
from pathlib import Path

import requests

from storysync.transcription.chunking import (
    chunk_audio, get_file_size_mb, merge_word_lists, needs_chunking,
)

# Bump when API parameters change — forces all existing caches to re-transcribe.
_CACHE_VERSION = 2


def transcribe(audio_path, api_key, language='de', model='nova-3',
               cache_path=None, force_refresh=False):
    if cache_path and Path(cache_path).exists() and not force_refresh:
        cached = json.loads(Path(cache_path).read_text(encoding='utf-8'))
        cache_ok = (
            not isinstance(cached, list)
            and cached.get('cache_version', 1) == _CACHE_VERSION
            and cached.get('provider') in ('deepgram', None)
            and (cached.get('provider') is None or cached.get('model', model) == model)
        )
        if cache_ok:
            return cached.get('words', []), cached.get('utterances', [])

    if needs_chunking(audio_path, 100):
        chunks_data = []
        tmp_dir = None
        for chunk_path, offset in chunk_audio(audio_path, chunk_seconds=900):
            tmp_dir = Path(chunk_path).parent
            words, utts = _call_deepgram(chunk_path, api_key, language, model)
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
        words, utterances = _call_deepgram(audio_path, api_key, language, model)

    if cache_path:
        Path(cache_path).write_text(json.dumps({
            'provider': 'deepgram', 'model': model, 'language': language,
            'cache_version': _CACHE_VERSION,
            'words': words, 'utterances': utterances,
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    return words, utterances


def _call_deepgram(audio_path, api_key, language, model):
    with open(audio_path, 'rb') as f:
        audio_data = f.read()

    url = (
        f'https://api.deepgram.com/v1/listen'
        f'?model={model}&language={language}'
        f'&words=true&utterances=true&punctuate=true'
    )
    ext = Path(audio_path).suffix.lower()
    ctype = 'audio/flac' if ext == '.flac' else 'audio/mpeg'
    headers = {'Authorization': f'Token {api_key}', 'Content-Type': ctype}

    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, data=audio_data, timeout=600)
            if r.status_code == 429:
                import time
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()['results']
            words = data['channels'][0]['alternatives'][0]['words']
            utterances = data.get('utterances', [])
            return words, utterances
        except requests.RequestException:
            if attempt == 2:
                raise
            import time
            time.sleep(2 ** attempt)

    return [], []


def test_connection(api_key):
    try:
        r = requests.get(
            'https://api.deepgram.com/v1/projects',
            headers={'Authorization': f'Token {api_key}'},
            timeout=15)
        return r.status_code == 200, 'Connected' if r.status_code == 200 else r.text[:80]
    except Exception as e:
        return False, str(e)[:80]