"""OpenAI Whisper API transcription provider (whisper-1, word-level timestamps)."""

import json
import time
from pathlib import Path

import requests

from storysync.transcription.chunking import chunk_audio, merge_word_lists, needs_chunking

OPENAI_URL = 'https://api.openai.com/v1/audio/transcriptions'

_CACHE_VERSION = 2

_AUDIO_MIME = {
    '.mp3':  'audio/mpeg',
    '.mp4':  'audio/mp4',
    '.m4a':  'audio/mp4',
    '.wav':  'audio/wav',
    '.flac': 'audio/flac',
    '.webm': 'audio/webm',
    '.ogg':  'audio/ogg',
    '.mpeg': 'audio/mpeg',
    '.mpga': 'audio/mpeg',
}


def transcribe(audio_path, api_key, language='de', model='whisper-1',
               prompt=None, cache_path=None, force_refresh=False):
    if cache_path and Path(cache_path).exists() and not force_refresh:
        cached = json.loads(Path(cache_path).read_text(encoding='utf-8'))
        cache_ok = (
            cached.get('cache_version', 0) == _CACHE_VERSION
            and cached.get('provider') == 'openai'
            and cached.get('model') == model
        )
        if cache_ok:
            return cached.get('words', []), cached.get('utterances', [])

    if needs_chunking(audio_path, 24):
        chunks_data = []
        tmp_dir = None
        for chunk_path, offset in chunk_audio(audio_path, chunk_seconds=480):
            tmp_dir = Path(chunk_path).parent
            words, utts = _call_openai(chunk_path, api_key, language, model, prompt)
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
        words, utterances = _call_openai(audio_path, api_key, language, model, prompt)

    if not words:
        raise RuntimeError(
            'OpenAI Whisper returned no word-level timestamps. '
            'Check your API key is valid and the audio file is supported.'
        )

    if cache_path:
        Path(cache_path).write_text(json.dumps({
            'provider': 'openai', 'model': model, 'language': language,
            'cache_version': _CACHE_VERSION,
            'words': words, 'utterances': utterances,
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    return words, utterances


def _call_openai(audio_path, api_key, language, model, prompt):
    """POST to OpenAI transcription endpoint.

    timestamp_granularities is sent as repeated keys WITHOUT square brackets —
    identical wire format to what OpenAI's own Python SDK produces internally.
    Using [] bracket notation in the key name causes the API to silently ignore
    the parameter and return no word timestamps.
    """
    headers = {'Authorization': f'Bearer {api_key}'}

    data = [
        ('model',                    model),
        ('language',                 language),
        ('response_format',          'verbose_json'),
        ('timestamp_granularities',  'word'),
        ('timestamp_granularities',  'segment'),
    ]
    if prompt:
        # OpenAI prompt hint: keep short, used as context only
        data.append(('prompt', prompt[:500]))

    ext  = Path(audio_path).suffix.lower()
    mime = _AUDIO_MIME.get(ext, 'audio/mpeg')

    last_exc = None
    for attempt in range(3):
        try:
            with open(audio_path, 'rb') as f:
                files = {'file': (Path(audio_path).name, f, mime)}
                r = requests.post(
                    OPENAI_URL, headers=headers, data=data, files=files,
                    timeout=300)   # 5-min hard limit per chunk

            if r.status_code == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue

            if r.status_code >= 400:
                try:
                    msg = r.json().get('error', {}).get('message', r.text[:400])
                except Exception:
                    msg = r.text[:400]
                # 4xx = client error, retrying won't help
                if r.status_code < 500:
                    raise RuntimeError(f'OpenAI {r.status_code}: {msg}')
                last_exc = RuntimeError(f'OpenAI {r.status_code}: {msg}')
                time.sleep(2 ** attempt)
                continue

            body = r.json()
            words, utterances = _parse_response(body)

            # Sanity-check: warn if API returned no words despite requesting them
            if not words and body.get('text'):
                raise RuntimeError(
                    'OpenAI returned a transcript but no word timestamps. '
                    'This usually means the model or language does not support '
                    'word-level granularity. Try a different audio format or language.'
                )

            return words, utterances

        except RuntimeError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 2:
                raise RuntimeError(f'OpenAI request failed: {exc}') from exc
            time.sleep(2 ** attempt)

    if last_exc:
        raise last_exc
    return [], []


def _parse_response(data):
    words = []
    for w in data.get('words', []):
        start = float(w.get('start', 0))
        end   = float(w.get('end', start + 0.2))
        words.append({
            'word':       w.get('word', ''),
            'start':      start,
            'end':        end,
            'confidence': float(w.get('probability', w.get('confidence', 0.9))),
        })

    utterances = []
    for seg in data.get('segments', []):
        utterances.append({
            'transcript': seg.get('text', ''),
            'start':      float(seg.get('start', 0)),
            'end':        float(seg.get('end', seg.get('start', 0) + 1)),
        })

    if not utterances and words:
        utterances = [{
            'transcript': data.get('text', ''),
            'start':      words[0]['start'],
            'end':        words[-1]['end'],
        }]

    return words, utterances


def test_connection(api_key):
    try:
        r = requests.get(
            'https://api.openai.com/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=15)
        if r.status_code == 200:
            return True, 'Connected to OpenAI API'
        try:
            msg = r.json().get('error', {}).get('message', r.text[:120])
        except Exception:
            msg = r.text[:120]
        return False, msg
    except Exception as e:
        return False, str(e)[:120]
