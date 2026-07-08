"""Page layout computation with caching."""


def measure_font(draw, font):
    _, top, _, bottom = draw.textbbox((0, 0), 'Hgjpqy', font=font)
    return top, bottom


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, curr = [], []
    for w in words:
        test = ' '.join(curr + [w])
        if draw.textbbox((0, 0), test, font=font)[2] > max_width and curr:
            lines.append(' '.join(curr))
            curr = [w]
        else:
            curr.append(w)
    if curr:
        lines.append(' '.join(curr))
    return lines or ['']


def inline_flow(draw, sentences, font, max_width):
    tagged = []
    for si, sent in enumerate(sentences):
        for w in sent['text'].split():
            tagged.append((w, si))

    wrapped, current = [], []
    for word, si in tagged:
        candidate = ' '.join(w for w, _ in current + [(word, si)])
        if draw.textbbox((0, 0), candidate, font=font)[2] > max_width and current:
            wrapped.append(current)
            current = [(word, si)]
        else:
            current.append((word, si))
    if current:
        wrapped.append(current)

    lines = [' '.join(w for w, _ in ln) for ln in wrapped]
    return lines, wrapped


def compute_sent_highlights(draw, wrapped, sentences, font, tx0,
                            para_y, lh, ft_top, glyph_h, hl_above, hl_below,
                            hl_padding=None):
    n = len(sentences)
    rects = [[] for _ in range(n)]

    for li, ln in enumerate(wrapped):
        groups = []
        for w, si in ln:
            if groups and groups[-1][0] == si:
                groups[-1][1].append(w)
            else:
                groups.append((si, [w]))

        if hl_padding is not None:
            # Ruled row mode: highlight fills from 2px below slot-top down to 1px
            # before the rule line.  Combined with full-width drawing in render_frame
            # this gives a clean "highlighted notebook row" look.
            # Rule is at slot_top + (ft_top+glyph_h) + 2; highlight ends 1px before it.
            line_y0 = para_y + li * lh + 2          # 2px below slot top
            line_y1 = para_y + li * lh + ft_top + glyph_h + 1  # 1px before rule
        else:
            line_y0 = para_y + li * lh + ft_top - hl_above
            line_y1 = para_y + li * lh + ft_top + glyph_h + hl_below

        prefix = ''
        for si, words in groups:
            group_str = ' '.join(words)
            full_so_far = (prefix + ' ' if prefix else '') + group_str
            x_start = draw.textbbox((0, 0), prefix + ' ', font=font)[2] if prefix else 0
            x_end = draw.textbbox((0, 0), full_so_far, font=font)[2]
            # rect is a 5-tuple: (x0, y0, x1, y1, line_index)
            rects[si].append((tx0 + x_start - 4, line_y0, tx0 + x_end + 4, line_y1, li))
            prefix = full_so_far

    return rects


def layout_page(draw, page_items, font_body, font_heading,
                cx0, cy0, cx1, pad_x, pad_y, line_spacing, para_spacing=0.85,
                hl_padding=None, top_pad=None, para_empty_row=False):
    lh_body = int(font_body.size * line_spacing)
    lh_heading = int(font_heading.size * line_spacing)
    tmax = (cx1 - cx0) - pad_x * 2
    tx0 = cx0 + pad_x

    gap_after_heading = int(font_body.size * 1.0)
    # para_empty_row: full line-height gap instead of slider value
    gap_after_para = lh_body if para_empty_row else int(font_body.size * para_spacing)

    ft_top, ft_bottom = measure_font(draw, font_body)
    glyph_h = ft_bottom - ft_top
    hl_above, hl_below = 3, 5

    # top_pad overrides the initial y offset; pad_y still governs bottom margin
    _top = top_pad if top_pad is not None else pad_y
    blocks, y = [], cy0 + _top

    for item in page_items:
        if item['type'] == 'heading':
            lines = wrap_text(draw, item['text'], font_heading, tmax)
            lw_h = [draw.textbbox((0, 0), ln, font=font_heading)[2] for ln in lines]
            blocks.append({
                'type': 'heading', 'lines': lines, 'font': font_heading,
                'lh': lh_heading, 'cx0': cx0, 'cx1': cx1, 'tx0': tx0, 'y0': y,
                'line_widths': lw_h,
            })
            y += lh_heading * len(lines) + gap_after_heading

        elif item['type'] == 'paragraph':
            lines, wrapped = inline_flow(draw, item['sentences'], font_body, tmax)
            sent_rects = compute_sent_highlights(
                draw, wrapped, item['sentences'], font_body, tx0,
                y, lh_body, ft_top, glyph_h, hl_above, hl_below,
                hl_padding=hl_padding)
            lw_p = [draw.textbbox((0, 0), ln, font=font_body)[2] for ln in lines]
            blocks.append({
                'type': 'paragraph', 'sentences': item['sentences'],
                'lines': lines, 'sent_rects': sent_rects, 'font': font_body,
                'lh': lh_body, 'tx0': tx0, 'cx0': cx0, 'cx1': cx1, 'y0': y,
                'line_widths': lw_p, 'wrapped': wrapped,
            })
            y += lh_body * len(lines) + gap_after_para

    return blocks


def _item_height(draw, item, font_body, font_heading, tmax,
                 lh_body, lh_heading, gap_after_para, gap_after_heading):
    """Measure vertical space an item will consume."""
    if item['type'] == 'heading':
        lines = wrap_text(draw, item['text'], font_heading, tmax)
        return lh_heading * len(lines) + gap_after_heading
    else:
        lines, _ = inline_flow(draw, item['sentences'], font_body, tmax)
        return lh_body * len(lines) + gap_after_para


def _find_fit(draw, items, font_body, font_heading,
              cx0, cy0, cx1, pad_x, pad_y, line_spacing, para_spacing, max_y,
              top_pad=None, para_empty_row=False):
    """Return how many leading items fit within max_y (returns at least 1)."""
    lh_body = int(font_body.size * line_spacing)
    lh_heading = int(font_heading.size * line_spacing)
    tmax = (cx1 - cx0) - pad_x * 2
    gap_after_heading = int(font_body.size * 1.0)
    gap_after_para = lh_body if para_empty_row else int(font_body.size * para_spacing)
    bottom_pad = max(16, pad_y // 2)

    _top = top_pad if top_pad is not None else pad_y
    y = cy0 + _top
    for i, item in enumerate(items):
        h = _item_height(draw, item, font_body, font_heading, tmax,
                         lh_body, lh_heading, gap_after_para, gap_after_heading)
        if y + h > max_y - bottom_pad:
            return max(1, i)
        y += h
    return len(items)


def reflow_pages(pages, font_body, font_heading, W, H, line_spacing,
                 para_spacing=0.85, para_empty_row=False,
                 show_player=False, player_height=1.0,
                 title_body_gap=0.3, card_margin=0.055, text_padding=0.035):
    """Re-paginate to prevent text overflow beyond the card boundary.

    Sentences keep their _id and order. Only page boundaries shift.
    Chapter headings are always propagated to every page of that chapter
    so they render persistently until the next chapter begins.
    """
    from PIL import Image, ImageDraw as _ImageDraw
    _img = Image.new('RGB', (W, H), '#ffffff')
    _draw = _ImageDraw.Draw(_img)

    mx, my = int(W * card_margin), int(H * card_margin)
    cx0, cy0, cx1, cy1 = mx, my, W - mx, H - my
    _pad_x = max(8, int((cx1 - cx0) * text_padding))
    is_portrait = H > W

    def _heading_h(chapter):
        if not chapter:
            return 0
        _, _, _, ch_h = _draw.textbbox((0, 0), chapter, font=font_heading)
        _gap = int(font_heading.size * title_body_gap)
        return 16 + ch_h + _gap  # top gap + heading + title-body gap

    def _player_h():
        if not (show_player and is_portrait):
            return 0
        base_ph = max(36, int(H * 0.036))
        ph = max(24, int(base_ph * max(0.3, min(2.0, player_height))))
        return ph + int(H * 0.005) * 2

    def _body_top(chapter):
        top = cy0 + _heading_h(chapter) + _player_h()
        return top

    result = []
    for page in pages:
        chapter = page.get('chapter')
        chapter_time = page.get('chapter_time')  # set by _fix_chapters_from_words/utterances
        items = list(page['items'])
        first_split = True

        while items:
            body_top = _body_top(chapter)
            lh_b = int(font_body.size * line_spacing)
            fit = _find_fit(
                _draw, items, font_body, font_heading,
                cx0, body_top, cx1, _pad_x, 48, line_spacing, para_spacing, cy1,
                top_pad=lh_b, para_empty_row=para_empty_row)

            new_page = {'chapter': chapter, 'items': items[:fit]}
            # Carry chapter_time to the first sub-page only so build_timeline
            # can flip to this chapter the moment "Kapitel X" is spoken in the audio
            if first_split and chapter_time is not None:
                new_page['chapter_time'] = chapter_time
            result.append(new_page)
            items = items[fit:]
            first_split = False

    return result


class LayoutCache:
    """Cache page layouts keyed by page content + style."""

    def __init__(self):
        self._cache = {}

    def key(self, page_items, font_body, font_heading, W, H, line_spacing,
            body_top_offset=0, para_spacing=0.85, hl_padding=None,
            top_pad=None, para_empty_row=False, pad_x=60):
        parts = [str(W), str(H), str(line_spacing),
                 str(font_body.size), str(font_heading.size),
                 str(body_top_offset), str(round(para_spacing, 3)),
                 str(hl_padding), str(top_pad), str(para_empty_row), str(pad_x)]
        for item in page_items:
            if item['type'] == 'heading':
                parts.append('H:' + item['text'])
            else:
                for s in item['sentences']:
                    parts.append(f"S:{s.get('_id', '')}:{s['text']}")
        return '|'.join(parts)

    def get_blocks(self, draw, page_items, font_body, font_heading,
                   W, H, line_spacing, body_top, para_spacing=0.85,
                   hl_padding=None, top_pad=None, para_empty_row=False,
                   pad_x=60, card_margin=0.055):
        mx, my = int(W * card_margin), int(H * card_margin)
        cx0, cy0, cx1, cy1 = mx, my, W - mx, H - my
        offset = body_top - cy0
        k = self.key(page_items, font_body, font_heading, W, H, line_spacing,
                     offset, para_spacing, hl_padding, top_pad, para_empty_row,
                     pad_x=pad_x)
        if k not in self._cache:
            self._cache[k] = layout_page(
                draw, page_items, font_body, font_heading,
                cx0, body_top, cx1, pad_x, 48, line_spacing, para_spacing,
                hl_padding=hl_padding, top_pad=top_pad,
                para_empty_row=para_empty_row)
        return self._cache[k], (cx0, cy0, cx1, cy1)

    def clear(self):
        self._cache.clear()
