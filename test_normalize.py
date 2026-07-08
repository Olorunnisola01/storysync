import sys; sys.path.insert(0, '.')
from storysync.matching import _normalize_match, _greedy_word_align
from storysync.text import parse_story, paginate
from storysync.matching import assign_timestamps

tests = [
    ('E-Mails.', ['emails']),
    ('E-Mail', ['email']),
    ('gut-gemeint', ['gutgemeint']),
    ('Arbeit.', ['arbeit']),
    ('Eine Aufgabe, die sie vergessen hatte.', ['eine', 'aufgabe', 'die', 'sie', 'vergessen', 'hatte']),
]
print("=== _normalize_match tests ===")
all_ok = True
for text, expected in tests:
    result = _normalize_match(text)
    ok = result == expected
    if not ok:
        all_ok = False
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {repr(text)} -> {result}")
print("All OK:", all_ok)
print()

# Now simulate the exact story section that was drifting
print("=== Matching simulation for drifting section ===")
# Simulate transcript words for: "...Gedanken kamen. Arbeit. E-Mails. Eine Aufgabe..."
words = [
    {'word': 'Gedanken', 'start': 580.0, 'end': 580.5},
    {'word': 'kamen',    'start': 580.5, 'end': 581.0},
    {'word': 'Arbeit',   'start': 581.2, 'end': 581.8},
    {'word': 'E-Mails',  'start': 582.0, 'end': 582.6},  # 1 word in transcript
    {'word': 'Eine',     'start': 583.0, 'end': 583.3},
    {'word': 'Aufgabe',  'start': 583.3, 'end': 583.8},
    {'word': 'die',      'start': 583.8, 'end': 584.0},
    {'word': 'sie',      'start': 584.0, 'end': 584.2},
    {'word': 'vergessen','start': 584.2, 'end': 584.7},
    {'word': 'hatte',    'start': 584.7, 'end': 585.0},
    {'word': 'Ein',      'start': 585.5, 'end': 585.7},
    {'word': 'Gespräch', 'start': 585.7, 'end': 586.2},
    {'word': 'das',      'start': 586.2, 'end': 586.4},
]

sents = [
    {'text': 'Gedanken kamen.'},
    {'text': 'Arbeit.'},
    {'text': 'E-Mails.'},
    {'text': 'Eine Aufgabe, die sie vergessen hatte.'},
    {'text': 'Ein Gespräch, das sie falsch gemacht hatte.'},
]

_greedy_word_align(sents, words)

print("Sentence timestamps after matching:")
for s in sents:
    t = s.get('startTime', 'None')
    conf = s.get('confidence', 0)
    status = "MATCHED" if conf >= 1.0 else "interpolated"
    print(f"  [{status:12s}] t={t:.2f}s  '{s['text'][:50]}'")

# Key assertions:
t_emails = next(s['startTime'] for s in sents if 'E-Mails' in s['text'])
t_aufgabe = next(s['startTime'] for s in sents if 'Aufgabe' in s['text'])
t_gesprach = next(s['startTime'] for s in sents if 'Gespräch' in s['text'])

print()
print(f"'E-Mails.' matched at: {t_emails:.2f}s (expected ~582.0s)")
print(f"'Eine Aufgabe...' at:  {t_aufgabe:.2f}s (expected ~583.0s)")
print(f"'Ein Gespräch...' at:  {t_gesprach:.2f}s (expected ~585.5s)")

assert abs(t_emails - 582.0) < 0.5, f"E-Mails drift: {t_emails}"
assert abs(t_aufgabe - 583.0) < 0.5, f"Aufgabe drift: {t_aufgabe}"
assert abs(t_gesprach - 585.5) < 0.5, f"Gesprach drift: {t_gesprach}"
print()
print("PASS: No drift - all sentences matched to correct timestamps")
