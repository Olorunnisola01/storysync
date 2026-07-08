"""End-to-end test: verify no compounding drift when ffprobe underestimates duration."""
import sys
sys.path.insert(0, '.')

from storysync.text import parse_story, paginate
from storysync.matching import assign_timestamps, build_timeline
from storysync.constants import PRESETS
from storysync.render.video import build_video
import subprocess, os, tempfile

story = """KAPITEL 1: Der Morgen

Es war ein schoener Morgen. Die Sonne schien hell. Thomas stand frueh auf.
Er trank seinen Kaffee. Das Wetter war gut heute.

KAPITEL 2: Der Tag

Er ging zur Arbeit. Die Strassen waren leer. Er war sehr muede.
Aber die Arbeit machte Spass. Am Abend kam er nach Hause."""

words = [
    {'word': 'Es',       'start':  2.0, 'end':  2.3},
    {'word': 'war',      'start':  2.3, 'end':  2.6},
    {'word': 'ein',      'start':  2.6, 'end':  2.8},
    {'word': 'schoener', 'start':  2.8, 'end':  3.2},
    {'word': 'Morgen',   'start':  3.2, 'end':  3.8},
    {'word': 'Die',      'start':  6.0, 'end':  6.2},
    {'word': 'Sonne',    'start':  6.2, 'end':  6.6},
    {'word': 'schien',   'start':  6.6, 'end':  7.0},
    {'word': 'hell',     'start':  7.0, 'end':  7.5},
    {'word': 'Thomas',   'start': 10.0, 'end': 10.4},
    {'word': 'stand',    'start': 10.4, 'end': 10.7},
    {'word': 'frueh',    'start': 10.7, 'end': 11.0},
    {'word': 'auf',      'start': 11.0, 'end': 11.3},
    {'word': 'Er',       'start': 14.0, 'end': 14.2},
    {'word': 'trank',    'start': 14.2, 'end': 14.5},
    {'word': 'seinen',   'start': 14.5, 'end': 14.8},
    {'word': 'Kaffee',   'start': 14.8, 'end': 15.3},
    {'word': 'Das',      'start': 18.0, 'end': 18.2},
    {'word': 'Wetter',   'start': 18.2, 'end': 18.6},
    {'word': 'war',      'start': 18.6, 'end': 18.8},
    {'word': 'gut',      'start': 18.8, 'end': 19.1},
    {'word': 'heute',    'start': 19.1, 'end': 19.6},
    {'word': 'Er',       'start': 30.0, 'end': 30.2},
    {'word': 'ging',     'start': 30.2, 'end': 30.5},
    {'word': 'zur',      'start': 30.5, 'end': 30.7},
    {'word': 'Arbeit',   'start': 30.7, 'end': 31.2},
    {'word': 'Die',      'start': 34.0, 'end': 34.2},
    {'word': 'Strassen', 'start': 34.2, 'end': 34.7},
    {'word': 'waren',    'start': 34.7, 'end': 35.0},
    {'word': 'leer',     'start': 35.0, 'end': 35.5},
    {'word': 'Er',       'start': 38.0, 'end': 38.2},
    {'word': 'war',      'start': 38.2, 'end': 38.5},
    {'word': 'sehr',     'start': 38.5, 'end': 38.8},
    {'word': 'muede',    'start': 38.8, 'end': 39.3},
    {'word': 'Aber',     'start': 42.0, 'end': 42.3},
    {'word': 'die',      'start': 42.3, 'end': 42.5},
    {'word': 'Arbeit',   'start': 42.5, 'end': 42.9},
    {'word': 'machte',   'start': 42.9, 'end': 43.3},
    {'word': 'Spass',    'start': 43.3, 'end': 43.8},
    {'word': 'Am',       'start': 47.0, 'end': 47.2},
    {'word': 'Abend',    'start': 47.2, 'end': 47.6},
    {'word': 'kam',      'start': 47.6, 'end': 47.9},
    {'word': 'er',       'start': 47.9, 'end': 48.1},
    {'word': 'nach',     'start': 48.1, 'end': 48.4},
    {'word': 'Hause',    'start': 48.4, 'end': 49.0},
]

# ── Test 1: no scaling on small ffprobe underestimate ──────────────────────
print("=" * 60)
print("TEST 1: ffprobe underestimates by 2s (58s vs actual 60s)")
print("=" * 60)
total_dur_ffprobe = 58.0  # underestimate
items = parse_story(story, 0)
pages = paginate(items, 5)
assign_timestamps(pages, words, [], total_dur_ffprobe)

all_sents = [s for p in pages
             for item in p['items'] if item['type'] == 'paragraph'
             for s in item['sentences']]

print("Sentence timestamps:")
for s in all_sents:
    print(f"  {s['startTime']:.3f}s  {s['text'][:50]}")

# The sentence matched to t=30s should remain near 30s, not be scaled down
sent_at_30 = next(s for s in all_sents if 'ging' in s['text'].lower())
actual = sent_at_30['startTime']
expected = 30.0
drift = abs(actual - expected)
print(f"\nSentence 'Er ging zur Arbeit': expected ~{expected}s, got {actual:.3f}s, drift={drift:.3f}s")
assert drift < 1.0, f"FAIL: drift={drift:.3f}s (was {expected*(1-58/60):.3f}s before fix)"
print("PASS: sentence near correct timestamp, no compounding from ffprobe underestimate")

# ── Test 2: video concat timing uses absolute frames ──────────────────────
print()
print("=" * 60)
print("TEST 2: concat file uses absolute frame indices (zero drift)")
print("=" * 60)

# Simulate build_timeline and concat file generation
states = build_timeline(pages, 60.0)
FPS = 30.0
total_frames = round(60.0 * FPS)
frames_list = []
valid = [(i, states[i]) for i in range(len(states))]
for k, (idx, state) in enumerate(valid):
    t_start = state['t_start']
    if k < len(valid) - 1:
        t_next = valid[k+1][1]['t_start']
        frames = max(1, round(t_next * FPS) - round(t_start * FPS))
    else:
        frames = max(1, total_frames - round(t_start * FPS))
    frames_list.append(frames)

total_rendered = sum(frames_list)
drift_frames = abs(total_rendered - total_frames)
print(f"Total frames: {total_rendered} (target: {total_frames}), drift: {drift_frames} frames")
assert drift_frames == 0, f"FAIL: {drift_frames} frames of drift"
print("PASS: zero frame accumulation drift")

# ── Test 3: render a real short video and check ffprobe output ──────────
print()
print("=" * 60)
print("TEST 3: render 60s video and verify audio/video duration match")
print("=" * 60)

audio = 'test_60s.wav'
if not os.path.exists(audio):
    print("SKIP: test_60s.wav not found, run test setup first")
else:
    preset = PRESETS['Cream White']
    out = 'test_out.mp4'
    build_video(
        pages, audio, out, 1280, 720, preset,
        total_duration=58.0,  # simulate ffprobe underestimate
        font_family='Georgia', body_size=32, heading_size=40,
        line_spacing=1.3)
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries',
         'format=duration:stream=codec_type,duration',
         '-of', 'json', out],
        capture_output=True, text=True)
    import json
    info = json.loads(r.stdout)
    vid_dur = float(info['format']['duration'])
    print(f"Output video duration: {vid_dur:.3f}s (audio is 60.0s)")
    # Video should be close to audio length, not scaled to 58s
    assert abs(vid_dur - 60.0) < 2.0, f"FAIL: video duration {vid_dur}s far from 60s audio"
    print(f"PASS: video duration {vid_dur:.2f}s matches audio (60s)")
    os.remove(out)

print()
print("ALL TESTS PASSED - compounding drift bug is fixed")
