"""Quick tests for timestamp matching."""

from storysync.matching import (
    assign_timestamps, build_timeline, find_timestamp,
)
from storysync.text import paginate, parse_story


def _fake_words(text):
    words = []
    t = 0.0
    for w in text.split():
        words.append({'word': w, 'start': t, 'end': t + 0.4})
        t += 0.5
    return words


def test_monotonic_timestamps():
    story = 'Er ging nach Hause. Er aß sein Brot. Er schlief gut.'
    items = parse_story(story, 1)
    pages = paginate(items, 5)
    words = _fake_words('Er ging nach Hause Er aß sein Brot Er schlief gut')
    assign_timestamps(pages, words, [], total_duration=10.0)
    times = [s['startTime'] for s in pages[0]['items'][0]['sentences']]
    assert times == sorted(times), f'Not monotonic: {times}'
    assert all(times[i + 1] - times[i] >= 0.08 for i in range(len(times) - 1))


def test_no_stuck_timeline():
    story = 'Eins. Zwei. Drei. Vier. Fünf.'
    items = parse_story(story, 1)
    pages = paginate(items, 5)
    words = _fake_words('Eins Zwei Drei Vier Fünf')
    assign_timestamps(pages, words, [], total_duration=5.0)
    states = build_timeline(pages, 5.0)
    assert len(states) >= 5
    for st in states:
        assert 0.1 <= st['duration'] <= 45.0


def test_find_timestamp_fuzzy():
    words = [
        {'word': 'Hanna', 'start': 1.0, 'end': 1.3},
        {'word': 'ging', 'start': 1.4, 'end': 1.6},
        {'word': 'los', 'start': 1.7, 'end': 2.0},
    ]
    t, conf, pos, end = find_timestamp(words, 'Hannah ging los', min_idx=0)
    assert conf > 0.5
    assert abs(t - 1.0) < 0.01


def test_find_timestamp_tolerates_extra_word():
    words = [
        {'word': 'Hanna', 'start': 1.0, 'end': 1.2},
        {'word': 'wirklich', 'start': 1.25, 'end': 1.45},
        {'word': 'ging', 'start': 1.5, 'end': 1.7},
        {'word': 'los', 'start': 1.8, 'end': 2.0},
    ]
    t, conf, pos, end = find_timestamp(words, 'Hanna ging los', min_idx=0)
    assert conf > 0.7
    assert abs(t - 1.0) < 0.01
    assert end == 3


def test_repeated_sentences_keep_distinct_active_ids():
    story = 'Ja. Ja. Nein.'
    pages = paginate(parse_story(story, 1), 5)
    words = _fake_words('Ja Ja Nein')
    assign_timestamps(pages, words, [], total_duration=4.0)
    states = [s for s in build_timeline(pages, 4.0) if s['active']]
    assert states[0]['active'] == states[1]['active']
    assert states[0]['active_id'] != states[1]['active_id']


def test_long_pause_turns_highlight_off_without_shortening_video():
    story = 'Er wartete. Dann ging er.'
    pages = paginate(parse_story(story, 1), 5)
    words = [
        {'word': 'Er', 'start': 0.0, 'end': 0.2},
        {'word': 'wartete', 'start': 0.3, 'end': 0.7},
        {'word': 'Dann', 'start': 80.0, 'end': 80.2},
        {'word': 'ging', 'start': 80.3, 'end': 80.5},
        {'word': 'er', 'start': 80.6, 'end': 80.8},
    ]
    assign_timestamps(pages, words, [], total_duration=90.0)
    states = build_timeline(pages, 90.0)
    assert any(st['active'] is None and st['duration'] > 30 for st in states)
    assert abs(sum(st['duration'] for st in states) - 90.0) < 0.5


if __name__ == '__main__':
    test_monotonic_timestamps()
    test_no_stuck_timeline()
    test_find_timestamp_fuzzy()
    test_find_timestamp_tolerates_extra_word()
    test_repeated_sentences_keep_distinct_active_ids()
    test_long_pause_turns_highlight_off_without_shortening_video()
    print('All tests passed.')
