"""Story parsing and text normalization."""

import re

from storysync.constants import GROUP_OPTIONS


def normalize(text):
    t = text.lower()
    t = re.sub(r'\bhannah\b', 'hanna', t)
    for a, b in [('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 'ss'),
                 ('é', 'e'), ('è', 'e')]:
        t = t.replace(a, b)
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    return [w for w in t.split() if w]


def _split_sentences(block_text):
    parts = re.split(r'(?<=[.!?])\s+', block_text.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_story(text, group_size=0):
    text = re.sub(r'\r\n|\r', '\n', text)
    raw_blocks = re.split(r'\n[ \t]*\n', text.strip())

    tagged = []
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
        # Treat as a chapter heading if it matches known keywords, or if the
        # entire block is a single line written in ALL-CAPS (book title style).
        _is_keyword_heading = re.match(
            r'^(Kapitel\s+\w+|Epilog|Prolog|Titel)\b', block, re.IGNORECASE)
        _single_line = '\n' not in block.strip()
        _all_caps = (block == block.upper() and any(c.isalpha() for c in block)
                     and _single_line and len(block.strip()) <= 120)
        if _is_keyword_heading or _all_caps:
            tagged.append(('heading', block))
            continue
        for s in _split_sentences(block):
            tagged.append(('sentence', s))
        tagged.append(('break',))

    if tagged and tagged[-1] == ('break',):
        tagged.pop()

    items = []
    next_sent_id = 0

    def make_sentences(sentences):
        nonlocal next_sent_id
        result = []
        for sentence in sentences:
            result.append({'text': sentence, '_id': next_sent_id})
            next_sent_id += 1
        return result

    if group_size == 0:
        current_sents = []
        for tag in tagged:
            if tag[0] == 'heading':
                if current_sents:
                    items.append({'type': 'paragraph',
                                  'sentences': make_sentences(current_sents)})
                    current_sents = []
                items.append({'type': 'heading', 'text': tag[1]})
            elif tag[0] == 'sentence':
                current_sents.append(tag[1])
            elif tag[0] == 'break':
                if current_sents:
                    items.append({'type': 'paragraph',
                                  'sentences': make_sentences(current_sents)})
                    current_sents = []
        if current_sents:
            items.append({'type': 'paragraph',
                          'sentences': make_sentences(current_sents)})

    elif group_size == 1:
        for tag in tagged:
            if tag[0] == 'heading':
                items.append({'type': 'heading', 'text': tag[1]})
            elif tag[0] == 'sentence':
                items.append({'type': 'paragraph',
                              'sentences': make_sentences([tag[1]])})

    else:
        current_sents = []
        for tag in tagged:
            if tag[0] == 'heading':
                if current_sents:
                    items.append({'type': 'paragraph',
                                  'sentences': make_sentences(current_sents)})
                    current_sents = []
                items.append({'type': 'heading', 'text': tag[1]})
            elif tag[0] == 'sentence':
                current_sents.append(tag[1])
                if len(current_sents) >= group_size:
                    items.append({'type': 'paragraph',
                                  'sentences': make_sentences(current_sents)})
                    current_sents = []
        if current_sents:
            items.append({'type': 'paragraph',
                          'sentences': make_sentences(current_sents)})

    return items


def paginate(items, per_page=5):
    pages = []
    current = []
    sent_count = 0
    current_chapter = None

    def flush():
        nonlocal current, sent_count
        if current:
            pages.append({'chapter': current_chapter, 'items': current})
        current = []
        sent_count = 0

    for item in items:
        if item['type'] == 'heading':
            flush()
            current_chapter = item['text']
        else:
            sents = item['sentences']
            i = 0
            while i < len(sents):
                remaining = per_page - sent_count
                if remaining <= 0:
                    flush()
                    remaining = per_page
                chunk = sents[i:i + remaining]
                current.append({'type': 'paragraph', 'sentences': chunk})
                sent_count += len(chunk)
                i += len(chunk)

    flush()
    return pages


def iter_sentences(pages):
    for page in pages:
        for item in page['items']:
            if item['type'] == 'paragraph':
                for sent in item['sentences']:
                    yield sent


def story_stats(text):
    items = parse_story(text, 0)
    pages = paginate(items, 5)
    n_sents = sum(1 for _ in iter_sentences(pages))
    n_words = len(normalize(text))
    return n_sents, n_words, len(pages)


def prompt_excerpt(text, max_tokens=200):
    """First ~200 words of story for Whisper prompt."""
    words = text.split()
    return ' '.join(words[:max_tokens])
