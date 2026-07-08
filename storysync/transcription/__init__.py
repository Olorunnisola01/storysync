"""Transcription provider facade."""

from pathlib import Path

from storysync.transcription import deepgram, openai_whisper


def get_timestamps(audio_path, cache_path, provider, api_key, language='de',
                   deepgram_model='nova-3', story_prompt=None,
                   force_refresh=False):
    if provider == 'openai':
        return openai_whisper.transcribe(
            audio_path, api_key, language, 'whisper-1',
            prompt=story_prompt, cache_path=cache_path,
            force_refresh=force_refresh)
    # Deepgram (default fallback)
    return deepgram.transcribe(
        audio_path, api_key, language, deepgram_model,
        cache_path=cache_path, force_refresh=force_refresh)


def cache_is_stale(cache_path, provider, deepgram_model, language):
    if not cache_path or not Path(cache_path).exists():
        return True
    try:
        import json
        cached = json.loads(Path(cache_path).read_text(encoding='utf-8'))
        if cached.get('provider') != provider:
            return True
        if cached.get('language') != language:
            return True
        if provider == 'deepgram' and cached.get('model') != deepgram_model:
            return True
        return False
    except Exception:
        return True


def test_provider(provider, api_key):
    if provider == 'openai':
        return openai_whisper.test_connection(api_key)
    return deepgram.test_connection(api_key)
