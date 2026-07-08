"""Sentence-to-audio timestamp matching — greedy word alignment, utterance fallback."""

import re

from storysync.constants import MIN_SENTENCE_GAP, MIN_STATE_DURATION
from storysync.text import normalize


def _normalize_match(text):
    """Normalize text for word matching, joining hyphenated compounds.

    Unlike the global normalize(), hyphens between letters/digits are removed
    (not turned into spaces) so that hyphenated words like 'E-Mails' and
    'gut-gemeint' become single tokens ('emails', 'gutgemeint') that match
    their transcript equivalents.  All other behaviour is identical.
    """
    t = text.lower()
    for src, dst in [('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 'ss'),
                     ('é', 'e'), ('è', 'e')]:
        t = t.replace(src, dst)
    # Join intra-word hyphens BEFORE stripping punctuation so "E-Mails" → "emails"
    # instead of ["e", "mails"].  A hyphen between two alphanumeric chars is
    # word-internal; all other hyphens (dash at start/end) become spaces below.
    t = re.sub(r'(?<=[a-z0-9])-(?=[a-z0-9])', '', t)
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    return [w for w in t.split() if w]


# ── Levenshtein / word matching ────────────────────────────────────────────

def _levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1,
                            prev[j - 1] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


def _words_match(nw, aw):
    if nw == aw:
        return True
    if len(nw) >= 3 and len(aw) >= 3 and _levenshtein(nw, aw) <= 1:
        return True
    return False


# ── Compound expansion ─────────────────────────────────────────────────────

def expand_compounds(words, story_text):
    """Split compound transcript tokens that appear as two words in the story."""
    story_tokens = normalize(story_text)
    pairs, triples = {}, {}
    for i in range(len(story_tokens) - 1):
        pairs.setdefault(story_tokens[i] + story_tokens[i + 1],
                         story_tokens[i:i + 2])
    for i in range(len(story_tokens) - 2):
        triples.setdefault(
            story_tokens[i] + story_tokens[i + 1] + story_tokens[i + 2],
            story_tokens[i:i + 3])

    expanded = []
    for w in words:
        nw = (normalize(w['word']) or [''])[0]
        t0 = w['start']
        t1 = w.get('end', t0 + 0.3)
        if nw in triples:
            parts = triples[nw]
            dt = (t1 - t0) / 3
            for k, part in enumerate(parts):
                expanded.append({**w, 'word': part,
                                  'start': t0 + k * dt,
                                  'end': t0 + (k + 1) * dt})
        elif nw in pairs:
            parts = pairs[nw]
            tm = (t0 + t1) / 2
            expanded.append({**w, 'word': parts[0], 'start': t0, 'end': tm})
            expanded.append({**w, 'word': parts[1], 'start': tm, 'end': t1})
        else:
            expanded.append(w)
    return expanded


# ── Primary: greedy word-by-word alignment ─────────────────────────────────

def _interpolate_none(times, t_start, t_end):
    """Fill None slots in `times` by linear interpolation between known values."""
    n = len(times)
    known = [(i, t) for i, t in enumerate(times) if t is not None]
    if not known:
        for i in range(n):
            times[i] = t_start + (t_end - t_start) * i / max(n - 1, 1)
        return
    first_i, first_t = known[0]
    for i in range(first_i):
        frac = (i + 1) / (first_i + 1)
        times[i] = t_start + (first_t - t_start) * frac
    for k in range(len(known) - 1):
        ia, ta = known[k]
        ib, tb = known[k + 1]
        for i in range(ia + 1, ib):
            frac = (i - ia) / (ib - ia)
            times[i] = ta + (tb - ta) * frac
    last_i, last_t = known[-1]
    for i in range(last_i + 1, n):
        frac = (i - last_i) / (n - last_i)
        times[i] = last_t + (t_end - last_t) * frac


def _greedy_word_align(sents, words):
    """
    Match each story sentence to the transcript using sentence-start verification.

    For every sentence we search up to ~40 seconds ahead for the first position
    where the first TWO story words appear consecutively in the transcript.
    Requiring two consecutive words eliminates false-positive matches on common
    German single words ('er', 'es', 'sie', 'war', 'ist', etc.).

    When a sentence cannot be verified we advance the transcript pointer by the
    sentence's estimated word count so subsequent sentences stay in sync.

    Returns the fraction of sentences that received a direct match.
    """
    n_trans = len(words)
    if n_trans == 0:
        for s in sents:
            s['startTime'] = 0.0
            s['confidence'] = 0.0
        return 0.0

    # Use _normalize_match (not normalize) so hyphenated words become single tokens:
    # "E-Mails" → "emails" on BOTH sides, preventing a 2-token story word from
    # failing to verify against a 1-token transcript word and then advancing the
    # transcript pointer by 2 (skipping the first word of the NEXT sentence).
    norm_trans = [(_normalize_match(w['word']) or [''])[0] for w in words]
    t_span = (words[-1].get('end', words[-1]['start']) - words[0]['start']
              if n_trans > 1 else 1.0)
    wps = max(n_trans / max(t_span, 1.0), 0.5)

    # Large per-sentence lookahead: ~40 s covers chapter announcements and pauses.
    SENT_SKIP = max(120, int(wps * 40))
    # Require 3 consecutive matching words before committing a sentence timestamp.
    # This prevents false-positive matches on common 2-word pairs ("und dann",
    # "er war", etc.) that appear repeatedly inside long German sentences.
    VERIFY = 3

    sent_first_time = {}
    trans_ptr = 0
    # Minimum audio timestamp for the next sentence's match.
    # Prevents a sentence from matching a position that is chronologically
    # inside the previous sentence's expected span.
    min_next_t = words[0]['start'] if words else 0.0

    for si, sent in enumerate(sents):
        sw = [w for w in _normalize_match(sent['text']) if w]
        if not sw:
            continue

        verify_n = min(VERIFY, len(sw))
        found = False
        for j in range(trans_ptr, min(trans_ptr + SENT_SKIP, n_trans)):
            if words[j]['start'] < min_next_t:
                continue  # skip positions that are too early
            if not _words_match(norm_trans[j], sw[0]):
                continue
            ok = True
            for k in range(1, verify_n):
                if j + k >= n_trans or not _words_match(norm_trans[j + k], sw[k]):
                    ok = False
                    break
            if ok:
                t = words[j]['start']
                sent_first_time[si] = t
                trans_ptr = j + verify_n
                min_next_t = t + MIN_SENTENCE_GAP
                found = True
                break

        if not found:
            # Keep the pointer moving forward by estimated sentence length.
            est_dur = max(len(sw), 1) / wps
            min_next_t += est_dur
            trans_ptr = min(trans_ptr + max(len(sw), 1), n_trans)

    n = len(sents)
    times = [None] * n
    confs  = [0.0] * n
    for si, t in sent_first_time.items():
        times[si] = t
        confs[si]  = 1.0

    t_audio_start = words[0]['start']
    t_audio_end   = words[-1].get('end', words[-1]['start'] + 0.5)
    _interpolate_none(times, t_audio_start, t_audio_end)

    for i, sent in enumerate(sents):
        sent['startTime'] = times[i]
        sent['confidence'] = confs[i]

    return len(sent_first_time) / max(n, 1)


# ── Fallback: utterance-level distribution ─────────────────────────────────

def _match_by_utterances(sents, utterances):
    """
    Fallback when word alignment finds too few matches.
    Assigns each sentence to its best-matching Deepgram utterance,
    distributing multiple sentences evenly across the utterance's time span.
    Low-confidence sentences are linearly interpolated between anchors.
    """
    m = len(utterances)
    n = len(sents)
    sent_sets = [frozenset(normalize(s['text'])) for s in sents]
    utt_sets  = [frozenset(normalize(u['transcript'])) for u in utterances]

    raw_times   = [0.0] * n
    confidences = [0.0] * n
    assignments = [0]   * n
    min_utt = 0

    for i, s_words in enumerate(sent_sets):
        if not s_words:
            assignments[i] = min_utt
            raw_times[i]   = float(utterances[min_utt]['start'])
            continue
        best_score, best_j = -1.0, min_utt
        for j in range(min_utt, min(min_utt + 40, m)):
            score = len(s_words & utt_sets[j]) / len(s_words)
            if score > best_score:
                best_score, best_j = score, j
        assignments[i]  = best_j
        raw_times[i]    = float(utterances[best_j]['start'])
        confidences[i]  = max(0.0, best_score)
        if best_score >= 0.35 and best_j > min_utt:
            min_utt = best_j

    # Distribute within utterance groups
    i = 0
    while i < n:
        uid = assignments[i]
        j = i + 1
        while j < n and assignments[j] == uid:
            j += 1
        utt   = utterances[uid]
        t0_u  = float(utt['start'])
        t1_u  = float(utt.get('end', t0_u + max(j - i, 1) * 2.5))
        count = j - i
        for k in range(count):
            raw_times[i + k] = t0_u + (t1_u - t0_u) * k / count
        i = j

    # Anchor interpolation for low-confidence runs
    ANCHOR_CONF = 0.30
    anchors = [i for i in range(n) if confidences[i] >= ANCHOR_CONF]
    t_audio_start = float(utterances[0]['start'])
    t_audio_end   = float(utterances[-1].get('end', utterances[-1]['start'] + 2.0))

    if not anchors:
        for i in range(n):
            raw_times[i] = t_audio_start + (t_audio_end - t_audio_start) * i / max(n - 1, 1)
    else:
        ia0, ta0 = anchors[0], raw_times[anchors[0]]
        for i in range(ia0):
            frac = (i + 1) / (ia0 + 1)
            raw_times[i] = t_audio_start + (ta0 - t_audio_start) * frac
        for k in range(len(anchors) - 1):
            ia, ib = anchors[k], anchors[k + 1]
            ta, tb = raw_times[ia], raw_times[ib]
            for i in range(ia + 1, ib):
                frac = (i - ia) / (ib - ia)
                raw_times[i] = ta + (tb - ta) * frac
        ia_last, ta_last = anchors[-1], raw_times[anchors[-1]]
        for i in range(ia_last + 1, n):
            frac = (i - ia_last) / (n - ia_last)
            raw_times[i] = ta_last + (t_audio_end - ta_last) * frac

    for i in range(n):
        sents[i]['startTime'] = raw_times[i]
        sents[i]['confidence'] = confidences[i]


# ── Word-level timestamp search (still used for find_timestamp) ────────────

def find_timestamp(words, anchor_text, min_idx=0, window=8, max_lookahead=400):
    anchor_words = normalize(anchor_text)[:window]
    fallback = words[min(min_idx, len(words) - 1)]['start'] if words else 0.0
    if not anchor_words:
        return fallback, 0.0, min_idx, min_idx

    norm_words = [(normalize(w['word']) or [''])[0] for w in words]
    best_score, best_pos, best_time = 0, min_idx, fallback
    best_end_idx = min_idx

    search_end = min(min_idx + max_lookahead,
                     max(min_idx + 1, len(words) - len(anchor_words) + 1))
    for i in range(min_idx, search_end):
        s, ai, wi = 0, 0, i
        while ai < len(anchor_words) and wi < len(norm_words):
            nw, aw = norm_words[wi], anchor_words[ai]
            if _words_match(nw, aw):
                s += 1; ai += 1; wi += 1
            else:
                matched = False
                for n in range(2, min(4, len(anchor_words) - ai + 1)):
                    if nw == ''.join(anchor_words[ai:ai + n]):
                        s += n; ai += n; wi += 1; matched = True; break
                if not matched:
                    break
        if s > best_score:
            best_score = s
            best_pos = i
            best_time = words[i]['start']
            best_end_idx = wi - 1 if wi > i else i

    conf = best_score / len(anchor_words)
    return best_time, conf, best_pos, max(best_pos, best_end_idx)


def _sentence_end_time(words, start_idx, sent_text):
    if not words:
        return 0.0
    start_idx = min(max(start_idx, 0), len(words) - 1)
    sent_len = len(normalize(sent_text))
    end_idx = min(start_idx + max(sent_len, 1) - 1, len(words) - 1)
    w = words[end_idx]
    return w.get('end', w['start'] + 0.5)


# ── Chapter timing ─────────────────────────────────────────────────────────

def _first_sentence_time(page):
    """Return the startTime of the first sentence on `page`, or None."""
    for item in page['items']:
        if item['type'] == 'paragraph':
            for s in item['sentences']:
                t = s.get('startTime')
                if t is not None:
                    return float(t)
    return None


def _fix_chapters_from_utterances(pages, utterances):
    """
    Set chapter_time by finding the utterance that announces each chapter heading.

    We anchor the search window to the chapter's first sentence time so that
    early utterances whose text happens to share common words with a later
    chapter title (e.g. 'die ersten') cannot produce a false early match.
    The utterance must fall within 30 s BEFORE the first sentence and must
    overlap at least 2 words with the normalised chapter heading.
    """
    if not utterances:
        return

    utt_sets = [set(normalize(u['transcript'])) for u in utterances]
    seen = set()

    for page in pages:
        chapter = page.get('chapter')
        if not chapter or chapter in seen or page.get('chapter_time') is not None:
            continue
        seen.add(chapter)
        ch_words = set(normalize(chapter))
        if not ch_words:
            continue

        anchor_t = _first_sentence_time(page)
        if anchor_t is None or anchor_t <= 0:
            continue

        WINDOW = 30.0
        best_sc, best_t = 0, None
        for i, utt in enumerate(utterances):
            t_utt = float(utt['start'])
            if t_utt >= anchor_t:
                break
            if t_utt < anchor_t - WINDOW:
                continue
            sc = len(ch_words & utt_sets[i])
            if sc > best_sc:
                best_sc, best_t = sc, t_utt

        if best_sc >= 2 and best_t is not None:
            page['chapter_time'] = best_t


def _fix_chapters_from_words(pages, words):
    """
    Set chapter_time using word-level search, anchored near the chapter's
    first sentence so that early false matches are avoided.
    """
    if not words:
        return
    seen = set()

    for page in pages:
        ch = page.get('chapter')
        if not ch or ch in seen or page.get('chapter_time') is not None:
            continue
        seen.add(ch)

        anchor_t = _first_sentence_time(page)
        if anchor_t is None or anchor_t <= 0:
            continue

        WINDOW = 30.0
        search_start = max(words[0]['start'], anchor_t - WINDOW)

        # Find the word index range [search_start, anchor_t)
        start_idx, end_idx = 0, len(words)
        for i, w in enumerate(words):
            if w['start'] >= search_start and start_idx == 0:
                start_idx = i
            if w['start'] >= anchor_t:
                end_idx = i
                break

        lookahead = max(1, end_idx - start_idx)
        t, conf, pos, _ = find_timestamp(
            words, ch, min_idx=start_idx, max_lookahead=lookahead)
        if conf >= 0.25 and pos < end_idx:
            page['chapter_time'] = t


# ── Post-processing ────────────────────────────────────────────────────────

def _all_sentences(pages):
    return [s for page in pages
            for item in page['items']
            if item['type'] == 'paragraph'
            for s in item['sentences']]


def _ensure_monotonic(pages, total_duration=None):
    """Guarantee strictly increasing startTimes across all sentences in story order."""
    sents = _all_sentences(pages)
    for i in range(1, len(sents)):
        if sents[i]['startTime'] <= sents[i - 1]['startTime']:
            sents[i]['startTime'] = sents[i - 1]['startTime'] + MIN_SENTENCE_GAP
    if total_duration and sents:
        last = sents[-1]['startTime']
        if last >= total_duration:
            overshoot = last - total_duration
            if overshoot > 10.0:
                # Large overshoot (>10 s) → timestamps are fundamentally wrong, scale all.
                scale = (total_duration - 1.0) / max(last, 0.01)
                for s in sents:
                    s['startTime'] *= scale
            else:
                # Small overshoot: clamp sentences that exceed total_duration.
                # Walk backwards so each clamped sentence is still strictly less
                # than the next, preserving monotonicity.
                # DO NOT scale all timestamps — a ratio <1 multiplied through every
                # sentence causes compounding drift (highlights lag progressively more
                # as the video plays). build_timeline handles the last state's
                # duration via max(MIN_STATE_DURATION, …) already.
                cap = total_duration - 1.0
                for k, s in enumerate(reversed(sents)):
                    limit = cap - k * MIN_SENTENCE_GAP
                    if s['startTime'] > limit:
                        s['startTime'] = limit
                    else:
                        break


def _assign_end_times_from_next(pages, total_duration=None):
    sents = _all_sentences(pages)
    for i, sent in enumerate(sents):
        if i + 1 < len(sents):
            next_start = sents[i + 1]['startTime']
            end = sent.get('endTime', next_start)
            sent['endTime'] = min(max(end, sent['startTime'] + MIN_STATE_DURATION),
                                  next_start)
        elif total_duration:
            sent['endTime'] = min(sent.get('endTime', total_duration), total_duration)
        else:
            sent['endTime'] = max(
                sent.get('endTime', sent['startTime'] + 2.0),
                sent['startTime'] + MIN_STATE_DURATION)


# ── Main entry point ───────────────────────────────────────────────────────

def assign_timestamps(pages, words, utterances=None, total_duration=None):
    """
    Assign startTime / endTime to every story sentence.

    Primary path — greedy word alignment:
      Every story word is matched left-to-right to transcript words.
      A sentence's timestamp = its first matched transcript word's start time.
      Unmatched sentences are interpolated between matched neighbours.
      Works for BOTH Deepgram and Groq when Deepgram is called WITHOUT
      smart_format=true (so spoken numbers match written numbers).

    Fallback — utterance distribution (< 20 % of sentences matched):
      Whole-sentence word-set overlap against Deepgram utterance boundaries,
      with anchor-based linear interpolation for low-confidence sentences.

    Last resort — even spread across audio duration.
    """
    sents = _all_sentences(pages)
    if not sents:
        _fix_chapters_from_utterances(pages, utterances)
        return

    matched_ratio = 0.0
    if words:
        matched_ratio = _greedy_word_align(sents, words)

    if matched_ratio < 0.20:
        if utterances:
            _match_by_utterances(sents, utterances)
        else:
            n = len(sents)
            t_max = total_duration or (n * 3.0)
            for i, s in enumerate(sents):
                s['startTime'] = t_max * i / max(n, 1)
                s['confidence'] = 0.0

    if utterances:
        _fix_chapters_from_utterances(pages, utterances)
    elif words:
        _fix_chapters_from_words(pages, words)

    _ensure_monotonic(pages, total_duration)
    _assign_end_times_from_next(pages, total_duration)


# ── Timeline builder ───────────────────────────────────────────────────────

def build_timeline(pages, total_duration):
    """
    Build the list of video states from page/sentence timestamps.
    Guarantees: strictly increasing t_start, duration >= MIN_STATE_DURATION,
    no chapter-reveal entry appearing after the first sentence on its page.
    """
    entries = []
    for p_idx, page in enumerate(pages):
        ch_time = page.get('chapter_time')
        if ch_time is not None:
            entries.append({
                'time': float(ch_time), 'page_idx': p_idx,
                'active': page.get('chapter'),
                'chapter': page.get('chapter'),
                'kind': 'chapter',
                'highlight_heading': True,
            })
        for item in page['items']:
            if item['type'] != 'paragraph':
                continue
            for sent in item['sentences']:
                entries.append({
                    'time': float(sent['startTime']),
                    'page_idx': p_idx,
                    'active': sent['text'],
                    'chapter': page.get('chapter'),
                    'end_time': sent.get('endTime'),
                    'kind': 'sentence',
                })

    entries.sort(key=lambda e: (e['time'], e['kind'] == 'chapter'))

    last_t = -1.0
    for e in entries:
        if e['time'] <= last_t:
            e['time'] = last_t + MIN_SENTENCE_GAP
        last_t = e['time']

    first_sent_t = {}
    for e in entries:
        if e['kind'] == 'sentence':
            p = e['page_idx']
            if p not in first_sent_t:
                first_sent_t[p] = e['time']
    entries = [e for e in entries
               if not (e['kind'] == 'chapter'
                       and first_sent_t.get(e['page_idx'], float('inf')) <= e['time'])]

    if not entries:
        return []

    total_duration = float(total_duration or 0)
    states = []
    for k, entry in enumerate(entries):
        next_t = entries[k + 1]['time'] if k + 1 < len(entries) else total_duration
        end_cap = entry.get('end_time')
        if end_cap and entry['kind'] == 'sentence':
            next_t = min(next_t, max(float(end_cap), entry['time'] + MIN_STATE_DURATION))
        duration = max(MIN_STATE_DURATION, next_t - entry['time'])
        states.append({
            'page_idx': entry['page_idx'],
            'active': entry['active'],
            'chapter': entry['chapter'],
            'duration': duration,
            't_start': entry['time'],
            'highlight_heading': entry.get('highlight_heading', False),
        })

    if states and states[0]['t_start'] > 0.5:
        states.insert(0, {
            'page_idx': 0,
            'active': None,
            'chapter': entries[0]['chapter'],
            'duration': states[0]['t_start'],
            't_start': 0.0,
        })

    return _dedupe_states(states)


def _dedupe_states(states):
    """Merge consecutive identical visuals — prevents redundant PNG frames."""
    if not states:
        return states
    merged = [dict(states[0])]
    for st in states[1:]:
        prev = merged[-1]
        if (prev['page_idx'] == st['page_idx']
                and prev['active'] == st['active']
                and prev['chapter'] == st['chapter']):
            prev['duration'] += st['duration']
        else:
            merged.append(dict(st))
    return merged
