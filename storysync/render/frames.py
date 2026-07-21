"""Frame rendering with highlight styles."""

import math
import random
import re
import threading

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from storysync.render.config import RenderConfig
from storysync.render.fonts import load_fonts
from storysync.render.layout import LayoutCache

# Ruled textures need layout data to align lines; all others are pre-layout.
_RULED_TEXTURES = {'Lines', 'College Ruled', 'Yellow Ruled'}

# ── Logo image cache (avoids reloading from disk on every frame) ──────────────
_logo_cache: dict = {}
_logo_lock = threading.Lock()


def _load_logo_cached(path):
    """Return RGBA PIL Image for logo_path, or None if it can't be opened."""
    with _logo_lock:
        if path not in _logo_cache:
            try:
                _logo_cache[path] = Image.open(path).convert('RGBA')
            except Exception:
                _logo_cache[path] = None
        return _logo_cache[path]


def _draw_watermark(img, draw, cx0, cy0, cx1, cy1,
                    watermark_path, watermark_size=0.5, watermark_opacity=0.3):
    """Render a semi-transparent image watermark centred on the card."""
    if not watermark_path or watermark_opacity <= 0:
        return img, draw
    src = _load_logo_cached(watermark_path)
    if src is None:
        return img, draw
    card_w, card_h = cx1 - cx0, cy1 - cy0
    target_px = max(16, int(min(card_w, card_h) * max(0.03, min(0.75, watermark_size))))
    lw, lh = src.size
    ratio = min(target_px / lw, target_px / lh)
    new_w, new_h = max(1, int(lw * ratio)), max(1, int(lh * ratio))
    wm = src.resize((new_w, new_h), Image.LANCZOS)
    r, g, b, a = wm.split()
    a = a.point(lambda x: int(x * max(0.0, min(1.0, watermark_opacity))))
    wm = Image.merge('RGBA', (r, g, b, a))
    paste_x = (cx0 + cx1) // 2 - new_w // 2
    paste_y = (cy0 + cy1) // 2 - new_h // 2
    base = img.convert('RGBA')
    base.paste(wm, (paste_x, paste_y), wm)
    img = base.convert('RGB')
    return img, ImageDraw.Draw(img)


def _draw_logo(img, cx0, cy0, cx1, cy1, W, H,
               logo_path, logo_position='top-right',
               logo_size=0.1, logo_opacity=1.0, logo_inside=True):
    """Composite a logo image at a card corner.

    logo_inside=True  → logo is placed within the card boundary.
    logo_inside=False → logo is placed in the outer margin (outside the card border).
    """
    if not logo_path:
        return img
    src = _load_logo_cached(logo_path)
    if src is None:
        return img
    card_w, card_h = cx1 - cx0, cy1 - cy0
    logo_px = max(16, int(min(card_w, card_h) * max(0.03, min(0.5, logo_size))))
    lw, lh = src.size
    ratio = min(logo_px / lw, logo_px / lh)
    new_w, new_h = max(1, int(lw * ratio)), max(1, int(lh * ratio))
    logo = src.resize((new_w, new_h), Image.LANCZOS)
    if logo_opacity < 1.0:
        r, g, b, a = logo.split()
        a = a.point(lambda x: int(x * max(0.0, min(1.0, logo_opacity))))
        logo = Image.merge('RGBA', (r, g, b, a))

    bp = (logo_position or 'top-right').lower().replace(' ', '-')
    in_right  = 'right'  in bp
    in_bottom = 'bottom' in bp

    if logo_inside:
        pad = max(8, int(min(card_w, card_h) * 0.015))
        if bp == 'top-left':
            x, y = cx0 + pad, cy0 + pad
        elif bp == 'bottom-right':
            x, y = cx1 - new_w - pad, cy1 - new_h - pad
        elif bp == 'bottom-left':
            x, y = cx0 + pad, cy1 - new_h - pad
        else:  # top-right
            x, y = cx1 - new_w - pad, cy0 + pad
    else:
        # Centre logo inside the margin strip between the card edge and image edge.
        pad = max(4, int(min(W, H) * 0.01))
        # Horizontal: centre in the right or left margin strip
        if in_right:
            x = cx1 + max(pad, (W - cx1 - new_w) // 2)
        else:
            x = max(pad, (cx0 - new_w) // 2)
        x = max(pad, min(W - new_w - pad, x))
        # Vertical: centre in the top or bottom margin strip
        if in_bottom:
            y = cy1 + max(pad, (H - cy1 - new_h) // 2)
        else:
            y = max(pad, (cy0 - new_h) // 2)
        y = max(pad, min(H - new_h - pad, y))

    base = img.convert('RGBA')
    base.paste(logo, (x, y), logo)
    return base.convert('RGB')


def _hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_WORD_STRIP_RE = re.compile(r'^\W+|\W+$', re.UNICODE)


def _keyword_color(word, keyword_colors, default):
    """Return the mapped colour for *word* (whole-word, case-insensitive), or default."""
    if not keyword_colors:
        return default
    key = _WORD_STRIP_RE.sub('', word).lower()
    return keyword_colors.get(key, default)


# ── Non-ruled background textures (drawn before text) ────────────────────────

def _draw_texture(draw, img, cx0, cy0, cx1, cy1, texture, card_color):
    """Apply a non-ruled paper texture over the card area."""
    if not texture or texture in _RULED_TEXTURES or texture == 'Blank':
        return img, draw

    if texture == 'Graph Paper':
        rule = Image.new('RGBA', img.size, (0, 0, 0, 0))
        rdraw = ImageDraw.Draw(rule)
        g_step = 22
        y = cy0
        while y <= cy1:
            rdraw.line([(cx0 + 4, y), (cx1 - 4, y)], fill=(100, 150, 215, 80), width=1)
            y += g_step
        x = cx0
        while x <= cx1:
            rdraw.line([(x, cy0 + 4), (x, cy1 - 4)], fill=(100, 150, 215, 80), width=1)
            x += g_step
        img = Image.alpha_composite(img.convert('RGBA'), rule).convert('RGB')
        draw = ImageDraw.Draw(img)

    elif texture == 'Dot Grid':
        rule = Image.new('RGBA', img.size, (0, 0, 0, 0))
        rdraw = ImageDraw.Draw(rule)
        d_step = 24
        dy = cy0 + d_step
        while dy < cy1:
            dx = cx0 + d_step
            while dx < cx1:
                rdraw.ellipse([dx - 1, dy - 1, dx + 1, dy + 1],
                              fill=(145, 145, 165, 150))
                dx += d_step
            dy += d_step
        img = Image.alpha_composite(img.convert('RGBA'), rule).convert('RGB')
        draw = ImageDraw.Draw(img)

    elif texture == 'Grid':
        r, g, b = _hex_to_rgb(card_color)
        line_color = (max(0, r - 22), max(0, g - 22), max(0, b - 22))
        g_step = 28
        y = cy0 + g_step
        while y < cy1:
            draw.line([(cx0 + 8, y), (cx1 - 8, y)], fill=line_color, width=1)
            y += g_step
        x = cx0 + g_step
        while x < cx1:
            draw.line([(x, cy0 + 8), (x, cy1 - 8)], fill=line_color, width=1)
            x += g_step

    elif texture == 'Sandpaper':
        noise = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ndraw = ImageDraw.Draw(noise)
        rng = random.Random(42)
        for _ in range((cx1 - cx0) * (cy1 - cy0) // 4):
            nx = rng.randint(cx0, cx1 - 1)
            ny = rng.randint(cy0, cy1 - 1)
            v = rng.randint(0, 60)
            a = rng.randint(20, 55)
            ndraw.point((nx, ny), fill=(v, v, v, a))
        img = Image.alpha_composite(img.convert('RGBA'), noise).convert('RGB')
        draw = ImageDraw.Draw(img)

    elif texture == 'Aged Paper':
        noise = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ndraw = ImageDraw.Draw(noise)
        rng = random.Random(7)
        for _ in range((cx1 - cx0) * (cy1 - cy0) // 6):
            nx = rng.randint(cx0, cx1 - 1)
            ny = rng.randint(cy0, cy1 - 1)
            v = rng.randint(100, 160)
            a = rng.randint(8, 28)
            ndraw.point((nx, ny), fill=(v, int(v * 0.85), int(v * 0.6), a))
        for i in range(12):
            alpha = int(18 * (1 - i / 12))
            inset = i * 2
            ndraw.rounded_rectangle(
                [cx0 + inset, cy0 + inset, cx1 - inset, cy1 - inset],
                radius=max(4, 16 - i), outline=(101, 67, 33, alpha), width=2)
        img = Image.alpha_composite(img.convert('RGBA'), noise).convert('RGB')
        draw = ImageDraw.Draw(img)

    elif texture == 'Linen':
        r, g, b = _hex_to_rgb(card_color)
        h_color = (max(0, r - 18), max(0, g - 18), max(0, b - 18))
        v_color = (max(0, r - 12), max(0, g - 12), max(0, b - 12))
        y = cy0
        while y < cy1:
            if y % 4 == 0:
                draw.line([(cx0, y), (cx1, y)], fill=h_color, width=1)
            y += 2
        x = cx0
        while x < cx1:
            if x % 4 == 0:
                draw.line([(x, cy0), (x, cy1)], fill=v_color, width=1)
            x += 2

    elif texture == 'Vellum':
        # Cloudy, mottled parchment: soft blurred blotches + fine grain speckle.
        r, g, b = _hex_to_rgb(card_color)
        blotch = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(blotch)
        rng = random.Random(23)
        n_blotches = max(18, (cx1 - cx0) * (cy1 - cy0) // 9000)
        for _ in range(n_blotches):
            bx = rng.randint(cx0, cx1 - 1)
            by = rng.randint(cy0, cy1 - 1)
            rad = rng.randint(18, 55)
            shade = rng.randint(-30, 20)
            a = rng.randint(10, 26)
            cr = max(0, min(255, r + shade))
            cg = max(0, min(255, g + int(shade * 0.85)))
            cb = max(0, min(255, b + int(shade * 0.6)))
            bdraw.ellipse([bx - rad, by - rad, bx + rad, by + rad],
                          fill=(cr, cg, cb, a))
        blotch = blotch.filter(ImageFilter.GaussianBlur(radius=14))

        grain = Image.new('RGBA', img.size, (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grain)
        for _ in range((cx1 - cx0) * (cy1 - cy0) // 5):
            nx = rng.randint(cx0, cx1 - 1)
            ny = rng.randint(cy0, cy1 - 1)
            v = rng.randint(-40, 30)
            a = rng.randint(6, 20)
            cr = max(0, min(255, r + v))
            cg = max(0, min(255, g + int(v * 0.85)))
            cb = max(0, min(255, b + int(v * 0.6)))
            gdraw.point((nx, ny), fill=(cr, cg, cb, a))

        noise = Image.alpha_composite(blotch, grain)
        img = Image.alpha_composite(img.convert('RGBA'), noise).convert('RGB')
        draw = ImageDraw.Draw(img)

    elif texture == 'Kraft Paper':
        # Fibrous flecked paper: dense short random-angle fiber strokes.
        r, g, b = _hex_to_rgb(card_color)
        noise = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ndraw = ImageDraw.Draw(noise)
        rng = random.Random(91)
        n_fibers = (cx1 - cx0) * (cy1 - cy0) // 45
        for _ in range(n_fibers):
            fx = rng.uniform(cx0, cx1 - 1)
            fy = rng.uniform(cy0, cy1 - 1)
            length = rng.uniform(2, 7)
            angle = rng.uniform(0, math.pi)
            dx = math.cos(angle) * length
            dy = math.sin(angle) * length
            shade = rng.randint(-35, 25)
            a = rng.randint(15, 40)
            cr = max(0, min(255, r + shade))
            cg = max(0, min(255, g + int(shade * 0.8)))
            cb = max(0, min(255, b + int(shade * 0.55)))
            ndraw.line([(fx, fy), (fx + dx, fy + dy)], fill=(cr, cg, cb, a), width=1)
        img = Image.alpha_composite(img.convert('RGBA'), noise).convert('RGB')
        draw = ImageDraw.Draw(img)

    return img, draw


# ── Ruled textures (drawn AFTER layout so lines align with text baselines) ────

def _draw_ruled_lines(draw, img, cx0, cy0, cx1, cy1, texture, blocks,
                      lh_body, line_color=None, line_thickness=1,
                      ft_bottom_offset=None, top_clip=None,
                      extra_rule_ys=None, pad_x=60):
    """Draw horizontal ruled lines aligned to actual rendered text line positions.

    When ft_bottom_offset is provided (= font descender bottom relative to line y0),
    lines are drawn just below the text descenders so text visually sits ON the rule.
    Without it, lines sit at the slot bottom (legacy behaviour).
    """
    # ── Resolve line RGBA colour ───────────────────────────────────────────
    if line_color:
        r, g, b = _hex_to_rgb(line_color)
        lc = (r, g, b, 130)
    elif texture == 'Yellow Ruled':
        lc = (70, 130, 200, 120)
    else:
        lc = (100, 149, 237, 130)          # cornflower blue

    # ── Yellow Ruled: warm background tint ────────────────────────────────
    if texture == 'Yellow Ruled':
        tint = Image.new('RGBA', img.size, (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(tint)
        tdraw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=16,
                                 fill=(255, 235, 110, 55))
        img = Image.alpha_composite(img.convert('RGBA'), tint).convert('RGB')
        draw = ImageDraw.Draw(img)

    rule = Image.new('RGBA', img.size, (0, 0, 0, 0))
    rdraw = ImageDraw.Draw(rule)

    lw = max(1, int(line_thickness))
    _clip_top = top_clip if top_clip is not None else (cy0 + 2)

    def hline(y):
        if _clip_top < y < cy1 - 2:
            rdraw.line([(cx0 + 8, y), (cx1 - 8, y)], fill=lc, width=lw)

    # ── Collect rule-line y positions from layout blocks ──────────────────
    # When ft_bottom_offset is given, rule sits just 2px below the text
    # descenders — text visually rests ON the line (college-ruled look).
    # Otherwise rule goes at the bottom of the lh slot (legacy).
    text_line_rules = []
    for block in blocks:
        y = block['y0']
        for _ in block['lines']:
            if ft_bottom_offset is not None:
                text_line_rules.append(y + ft_bottom_offset + 2)
            else:
                text_line_rules.append(y + block['lh'])
            y += block['lh']

    for ly in text_line_rules:
        hline(ly)

    # ── Header area: extend upward from first content rule at lh intervals ─
    if text_line_rules:
        y = text_line_rules[0] - lh_body
        while y > cy0 + 2:
            hline(y)
            y -= lh_body

    # ── Footer area: extend downward from last content rule at lh intervals ─
    if text_line_rules:
        y = text_line_rules[-1] + lh_body
        while y < cy1 - 2:
            hline(y)
            y += lh_body

    # Fallback: blank page
    if not text_line_rules:
        y = cy0 + lh_body
        while y < cy1 - 2:
            hline(y)
            y += lh_body

    # ── Extra rules for empty paragraph-gap rows ──────────────────────────
    for ey in (extra_rule_ys or []):
        hline(ey)

    # ── Red margin line for College Ruled and Yellow Ruled ────────────────
    # Tracks pad_x so it stays LEFT of text (tx0 = cx0+pad_x) at any resolution.
    # Starts at top_clip so it doesn't draw through the audio player widget.
    if texture in ('College Ruled', 'Yellow Ruled'):
        margin_x   = cx0 + max(4, int(pad_x * 0.7))
        margin_top = _clip_top + 4
        rdraw.line([(margin_x, margin_top), (margin_x, cy1 - 8)],
                   fill=(215, 65, 65, 170), width=2)

    img = Image.alpha_composite(img.convert('RGBA'), rule).convert('RGB')
    draw = ImageDraw.Draw(img)
    return img, draw


# ── Chapter heading helper ────────────────────────────────────────────────────

def _draw_chapter_heading(draw, img, W, H, cx0, cy0, cx1, cy1,
                          ch_lines, ch_y_pos, ch_tw, lh_heading,
                          font_heading, chapter_color, preset,
                          highlight_heading, highlight_color, highlight_style):
    """Render the chapter heading (multi-line safe) on top of texture/ruled lines."""
    ch_color = chapter_color or preset['heading']
    hl = highlight_color or preset['highlight']

    y = ch_y_pos
    for ln in ch_lines:
        lw = draw.textbbox((0, 0), ln, font=font_heading)[2]
        ch_h = draw.textbbox((0, 0), ln, font=font_heading)[3]
        ch_x = cx0 + ((cx1 - cx0) - lw) // 2

        rx0 = ch_x - 8
        ry0 = y - 4
        rx1 = ch_x + lw + 8
        ry1 = y + ch_h + 4

        if highlight_heading:
            if highlight_style == 'Underline':
                draw.text((ch_x, y), ln, font=font_heading, fill=ch_color)
                draw.line([(rx0, ry1 - 2), (rx1, ry1 - 2)], fill=hl, width=4)
            elif highlight_style == 'Soft glow':
                glow  = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                gdraw = ImageDraw.Draw(glow)
                gdraw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=5,
                                         fill=_hex_to_rgb(hl) + (120,))
                glow  = glow.filter(ImageFilter.GaussianBlur(radius=4))
                img   = Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')
                draw  = ImageDraw.Draw(img)
                draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=5, fill=hl)
                draw.text((ch_x, y), ln, font=font_heading, fill=ch_color)
            else:
                draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=5, fill=hl)
                draw.text((ch_x, y), ln, font=font_heading, fill=ch_color)
        else:
            draw.text((ch_x, y), ln, font=font_heading, fill=ch_color)

        y += lh_heading

    return img, draw


# ── Audio progress widget (9:16 portrait only) ───────────────────────────────

def _draw_audio_player(draw, img, cx0, player_top, cx1, H,
                       font_body, current_time, total_time, player_h,
                       player_width=1.0):
    """Draw a pill-shaped audio progress bar at player_top."""
    p_margin = max(16, int((cx1 - cx0) * 0.06))
    # player_width scales the pill width; 1.0 = full card width, 0.5 = half
    base_pill_w = (cx1 - cx0) - 2 * p_margin
    scaled_w    = max(80, int(base_pill_w * max(0.2, min(2.0, player_width))))
    center_x    = (cx0 + cx1) // 2
    px0 = center_x - scaled_w // 2
    px1 = center_x + scaled_w // 2
    py0 = player_top
    py1 = py0 + player_h

    # Pill background
    draw.rounded_rectangle([px0, py0, px1, py1], radius=player_h // 2,
                            fill=(248, 248, 252), outline=(210, 212, 220), width=1)

    bar_cy = (py0 + py1) // 2
    btn_area = player_h

    # ▶ Play triangle
    tr_cx = px0 + int(btn_area * 0.72)
    tr_r  = int(player_h * 0.28)
    draw.polygon([
        (tr_cx - tr_r // 2, bar_cy - tr_r),
        (tr_cx + tr_r,      bar_cy),
        (tr_cx - tr_r // 2, bar_cy + tr_r),
    ], fill=(50, 50, 65))

    # Time labels
    def fmt_t(t):
        m, s = int(t) // 60, int(t) % 60
        return f'{m}:{s:02d}'

    progress  = min(1.0, current_time / max(1.0, total_time))
    time_lbl  = fmt_t(current_time) + ' / ' + fmt_t(total_time)

    try:
        tf_size = max(8, int(player_h * 0.36))
        tfont   = ImageFont.truetype(font_body.path, size=tf_size)
    except Exception:
        tfont = font_body

    tb = draw.textbbox((0, 0), time_lbl, font=tfont)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]

    time_x = px1 - int(btn_area * 0.55) - tw
    time_y = bar_cy - th // 2 - tb[1]
    draw.text((time_x, time_y), time_lbl, font=tfont, fill=(75, 80, 95))

    # Progress bar (between play btn and time label)
    bar_x0 = px0 + int(btn_area * 1.6)
    bar_x1 = time_x - int(btn_area * 0.35)
    bar_h2  = max(3, int(player_h * 0.18))
    bar_y0  = bar_cy - bar_h2 // 2
    bar_y1  = bar_y0 + bar_h2
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1],
                            radius=bar_h2, fill=(210, 212, 220))
    fill_x1 = bar_x0 + max(0, int((bar_x1 - bar_x0) * progress))
    if fill_x1 > bar_x0:
        draw.rounded_rectangle([bar_x0, bar_y0, fill_x1, bar_y1],
                                radius=bar_h2, fill=(75, 100, 210))
    # Knob
    kn_r = max(4, int(player_h * 0.22))
    draw.ellipse([fill_x1 - kn_r, bar_cy - kn_r, fill_x1 + kn_r, bar_cy + kn_r],
                 fill=(75, 100, 210), outline=(255, 255, 255), width=max(1, kn_r // 3))

    return draw


# ── Main frame renderer ───────────────────────────────────────────────────────

def render_frame(W, H, page_items, cfg: RenderConfig,
                 active_text=None,
                 page_chapter=None,
                 highlight_heading=False,
                 active_sentence_id=None,
                 page_num=None,
                 current_time=0.0,
                 layout_cache=None,
                 draw=None):
    """Render one video frame.  All style parameters live in *cfg*;
    only per-frame values (active sentence, page number, playhead position)
    are passed directly."""

    # Unpack cfg into local names so the function body below is unchanged.
    preset            = cfg.preset
    font_body, font_heading = load_fonts(
        cfg.font_family, cfg.body_size, cfg.heading_size, cfg.use_bold)
    line_spacing      = cfg.line_spacing
    chapter_color     = cfg.chapter_color
    highlight_color   = cfg.highlight_color
    highlight_style   = cfg.highlight_style
    text_color        = cfg.text_color
    bg_color          = cfg.bg_color
    card_color        = cfg.card_color
    outline_color     = cfg.outline_color
    texture           = cfg.texture
    para_spacing      = cfg.para_spacing
    line_color        = cfg.line_color
    line_thickness    = cfg.line_thickness
    hl_padding        = cfg.hl_padding
    show_player       = cfg.show_player
    total_time        = cfg.total_time
    text_align        = cfg.text_align
    badge_circle_color = cfg.badge_circle_color
    badge_number_color = cfg.badge_number_color
    badge_position    = cfg.badge_position
    show_badge_circle = cfg.show_badge_circle
    badge_size        = cfg.badge_size
    border_thickness  = cfg.border_thickness
    player_width      = cfg.player_width
    player_height     = cfg.player_height
    para_empty_row    = cfg.para_empty_row
    para_row_line     = cfg.para_row_line
    body_stroke       = cfg.body_stroke
    watermark_path    = cfg.watermark_path
    watermark_opacity = cfg.watermark_opacity
    watermark_size    = cfg.watermark_size
    logo_path         = cfg.logo_path
    logo_position     = cfg.logo_position
    logo_size         = cfg.logo_size
    logo_opacity      = cfg.logo_opacity
    logo_inside       = cfg.logo_inside
    show_card_border  = cfg.show_card_border
    title_body_gap    = cfg.title_body_gap
    card_margin       = cfg.card_margin
    text_padding      = cfg.text_padding
    keyword_colors    = cfg.keyword_colors

    eff_bg      = bg_color      or preset['bg']
    eff_card    = card_color    or preset['card']
    eff_outline = outline_color or '#1a1a1a'
    eff_text    = text_color    or preset['text']

    img  = Image.new('RGB', (W, H), eff_bg)
    draw = draw or ImageDraw.Draw(img)

    mx, my = int(W * card_margin), int(H * card_margin)
    cx0, cy0, cx1, cy1 = mx, my, W - mx, H - my
    pad_x = max(8, int((cx1 - cx0) * text_padding))

    # ── Card shadow ───────────────────────────────────────────────────────
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sdraw  = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [cx0 + 4, cy0 + 6, cx1 + 4, cy1 + 6], radius=18, fill=(0, 0, 0, 40))
    img  = Image.alpha_composite(img.convert('RGBA'), shadow).convert('RGB')
    draw = ImageDraw.Draw(img)

    if show_card_border:
        draw.rounded_rectangle(
            [cx0, cy0, cx1, cy1], radius=16,
            fill=eff_card, outline=eff_outline, width=max(1, border_thickness))
    else:
        draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=16, fill=eff_card)

    # ── Font metrics (used for ruled line alignment + highlight tightness) ──
    from storysync.render.layout import measure_font as _measure_font
    ft_top_m, ft_bottom_m = _measure_font(draw, font_body)
    # ft_bottom_m = position of text descender bottom relative to draw y0.
    # Rule lines for ruled textures are drawn 2px below this value so text
    # visually sits on the rule.

    # ── Measure heading + player, establish body_top ─────────────────────
    # Order on card: [chapter heading] → [audio player] → [body text]
    is_portrait = H > W
    player_h = 0
    if show_player and is_portrait:
        base_ph = max(36, int(H * 0.036))
        player_h = max(24, int(base_ph * max(0.3, min(2.0, player_height))))

    body_top = cy0
    ch_y_pos = ch_tw = ch_h_px = None
    ch_lines = None
    lh_heading = int(font_heading.size * line_spacing)
    if page_chapter:
        from storysync.render.layout import wrap_text as _wrap_heading
        _head_max_w = (cx1 - cx0) - pad_x * 2
        ch_lines    = _wrap_heading(draw, page_chapter, font_heading, _head_max_w)
        ch_y_pos    = body_top + 16
        ch_tw       = max(draw.textbbox((0, 0), ln, font=font_heading)[2] for ln in ch_lines)
        ch_h_px     = draw.textbbox((0, 0), ch_lines[0], font=font_heading)[3]
        _total_ch_h = lh_heading * len(ch_lines)
        _tgap       = int(font_heading.size * title_body_gap)
        body_top    = ch_y_pos + _total_ch_h + _tgap

    # Player sits directly below the chapter heading (or card top if no heading)
    player_draw_top = body_top + int(H * 0.004)
    if show_player and is_portrait and player_h > 0:
        body_top = player_draw_top + player_h + int(H * 0.005)

    lh_body  = int(font_body.size * line_spacing)
    is_ruled = texture in _RULED_TEXTURES

    # One full line-height below body_top → text aligns to the first ruled line
    # after the title/player area; falls back to standard 48px pad on pages without a header
    _top_pad = lh_body if body_top > cy0 else 48

    # ── PHASE 0.5: Audio player widget (portrait 9:16 only) ───────────────
    if show_player and is_portrait and player_h > 0:
        draw = _draw_audio_player(
            draw, img, cx0, player_draw_top, cx1, H,
            font_body, current_time, total_time, player_h,
            player_width=player_width)

    # ── PHASE 1: Non-ruled textures (pre-layout) ──────────────────────────
    if not is_ruled:
        img, draw = _draw_texture(draw, img, cx0, cy0, cx1, cy1, texture, eff_card)

    # ── PHASE 2: Compute layout blocks ───────────────────────────────────
    # hl_padding makes highlights fill the full lh slot (compact ruled look).
    effective_hlpad = hl_padding if is_ruled and hl_padding is not None else None
    if layout_cache:
        blocks, _ = layout_cache.get_blocks(
            draw, page_items, font_body, font_heading, W, H, line_spacing,
            body_top, para_spacing, hl_padding=effective_hlpad,
            top_pad=_top_pad, para_empty_row=para_empty_row,
            pad_x=pad_x, card_margin=card_margin)
    else:
        from storysync.render.layout import layout_page
        blocks = layout_page(
            draw, page_items, font_body, font_heading,
            cx0, body_top, cx1, pad_x, 48, line_spacing, para_spacing,
            hl_padding=effective_hlpad, top_pad=_top_pad,
            para_empty_row=para_empty_row)

    # ── PHASE 3: Ruled textures (post-layout, line positions exact) ───────
    if is_ruled:
        # Clip ruled lines through the heading+player area so those zones stay clean.
        ruled_top_clip = body_top - 4 if body_top > cy0 else None

        # Optional: draw ruled lines in empty paragraph-gap rows too
        extra_ys = []
        if para_empty_row and para_row_line:
            for bi, blk in enumerate(blocks):
                if blk['type'] != 'paragraph':
                    continue
                blk_bottom_y = blk['y0'] + len(blk['lines']) * blk['lh']
                # Rule for the empty gap slot sits one lh below last line of block
                gap_rule_y = blk_bottom_y + ft_bottom_m + 2
                extra_ys.append(gap_rule_y)

        img, draw = _draw_ruled_lines(
            draw, img, cx0, cy0, cx1, cy1,
            texture, blocks, lh_body, line_color, line_thickness,
            ft_bottom_offset=ft_bottom_m, top_clip=ruled_top_clip,
            extra_rule_ys=extra_ys if extra_ys else None,
            pad_x=pad_x)

    # ── PHASE 3.5: Watermark image (behind all text) ─────────────────────
    if watermark_path:
        img, draw = _draw_watermark(img, draw, cx0, cy0, cx1, cy1,
                                    watermark_path, watermark_size,
                                    watermark_opacity)

    # ── PHASE 4: Chapter heading on top of texture/ruled lines ────────────
    if page_chapter and ch_y_pos is not None and ch_lines is not None:
        img, draw = _draw_chapter_heading(
            draw, img, W, H, cx0, cy0, cx1, cy1,
            ch_lines, ch_y_pos, ch_tw, lh_heading,
            font_heading, chapter_color, preset,
            highlight_heading, highlight_color, highlight_style)

    hl = highlight_color or preset['highlight']

    # ── PHASE 5: Highlight rects ──────────────────────────────────────────
    for block in blocks:
        if block['type'] != 'paragraph':
            continue
        for si, sent in enumerate(block['sentences']):
            if active_sentence_id is not None:
                if sent.get('_id') != active_sentence_id:
                    continue
            elif sent['text'] != active_text:
                continue
            rects = block['sent_rects'][si]
            pad_x_val = block['tx0'] - block['cx0']   # = layout pad_x (60)
            right_edge = block['cx1'] - pad_x_val
            lw_list = block.get('line_widths', [])
            tmax_blk = block['cx1'] - block['cx0'] - 2 * pad_x_val
            wrapped_lines = block.get('wrapped')       # [(word, sent_idx)] per line
            n_para_lines  = len(block['lines'])

            def _align_off(li):
                """X offset for text_align on line li of this block."""
                if text_align == 'left' or li >= len(lw_list):
                    return 0
                lw = lw_list[li]
                if text_align == 'center':
                    return (tmax_blk - lw) // 2
                if text_align == 'right':
                    return max(0, tmax_blk - lw)
                return 0

            for ri, rect_data in enumerate(rects):
                rx0, ry0, rx1, ry1, li = rect_data
                x_off = _align_off(li)
                rx0 += x_off
                rx1 += x_off

                # Justify alignment expands inter-word gaps on non-last lines,
                # but sent_rects were computed with natural (non-expanded) widths.
                # Remap rx0/rx1 to the actual justified word positions.
                if (text_align == 'justify'
                        and wrapped_lines is not None
                        and li < n_para_lines - 1):
                    line_tagged = wrapped_lines[li]   # [(word, sent_idx), ...]
                    all_ws = [w for w, _ in line_tagged]
                    if len(all_ws) > 1:
                        wws = [draw.textbbox((0, 0), w, font=block['font'])[2]
                               for w in all_ws]
                        extra = (tmax_blk - sum(wws)) / (len(all_ws) - 1)
                        jx0, jx1 = [], []
                        x = 0.0
                        for ww in wws:
                            jx0.append(x)
                            jx1.append(x + ww)
                            x += ww + extra
                        si_idxs = [i for i, (_, s) in enumerate(line_tagged)
                                   if s == si]
                        if si_idxs:
                            rx0 = int(block['tx0'] + jx0[si_idxs[0]])  - 4
                            rx1 = int(block['tx0'] + jx1[si_idxs[-1]]) + 4
                if highlight_style == 'Underline':
                    draw.line([(rx0, ry1 - 2), (rx1, ry1 - 2)],
                              fill=hl, width=4)
                elif highlight_style == 'Soft glow':
                    glow  = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                    gdraw = ImageDraw.Draw(glow)
                    gdraw.rounded_rectangle(
                        [rx0, ry0, rx1, ry1], radius=5,
                        fill=_hex_to_rgb(hl) + (120,))
                    glow  = glow.filter(ImageFilter.GaussianBlur(radius=4))
                    img   = Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')
                    draw  = ImageDraw.Draw(img)
                    draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=5, fill=hl)
                elif is_ruled:
                    # Full-width row highlight for ruled textures — extend to the
                    # right margin on every line except the last (where the sentence
                    # ends mid-line).  No rounded corners; clean notebook-row look.
                    is_last_line = (ri == len(rects) - 1)
                    eff_x1 = rx1 if is_last_line else right_edge
                    draw.rectangle([rx0, ry0, eff_x1, ry1], fill=hl)
                else:
                    draw.rounded_rectangle(
                        [rx0, ry0, rx1, ry1], radius=5, fill=hl)

    # ── PHASE 5.5: Body stroke layer ─────────────────────────────────────
    # PIL stroke_width is integer-only, so values 0.1-0.4 and 0.6-0.9 are
    # invisible with direct rounding.  Instead, draw text+stroke onto a
    # transparent RGBA layer, scale its alpha by body_stroke, then composite.
    # Phase 6 then draws the text fill at full opacity, leaving only the
    # stroke ring semi-transparent — giving true smooth 0→1 graduation.
    if body_stroke > 0:
        _sa = min(1.0, float(body_stroke))
        _sl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        _sld = ImageDraw.Draw(_sl)
        _sr, _sg, _sb = _hex_to_rgb(eff_text)
        _sf = (_sr, _sg, _sb, 255)
        for _blk in blocks:
            if _blk['type'] != 'paragraph':
                continue
            _y  = _blk['y0']
            _tm = _blk['cx1'] - _blk['cx0'] - 2 * (_blk['tx0'] - _blk['cx0'])
            _nl = len(_blk['lines'])
            _lw = _blk.get('line_widths', [])
            for _li, _ln in enumerate(_blk['lines']):
                _last = (_li == _nl - 1)
                if text_align == 'justify' and not _last:
                    _ws = _ln.split()
                    if len(_ws) > 1:
                        _wws = [_sld.textbbox((0, 0), w, font=_blk['font'])[2] for w in _ws]
                        _ex  = (_tm - sum(_wws)) / (len(_ws) - 1)
                        _x   = float(_blk['tx0'])
                        for _wi, (_w, _ww) in enumerate(zip(_ws, _wws)):
                            _sld.text((int(_x), _y), _w, font=_blk['font'],
                                      fill=_sf, stroke_width=1, stroke_fill=_sf)
                            _x += _ww + (_ex if _wi < len(_ws) - 1 else 0)
                    else:
                        _sld.text((_blk['tx0'], _y), _ln, font=_blk['font'],
                                  fill=_sf, stroke_width=1, stroke_fill=_sf)
                else:
                    _xo = 0
                    if text_align not in ('left', 'justify') and _li < len(_lw):
                        if text_align == 'center':
                            _xo = (_tm - _lw[_li]) // 2
                        elif text_align == 'right':
                            _xo = max(0, _tm - _lw[_li])
                    _sld.text((_blk['tx0'] + _xo, _y), _ln, font=_blk['font'],
                              fill=_sf, stroke_width=1, stroke_fill=_sf)
                _y += _blk['lh']
        _rc, _gc, _bc, _ac = _sl.split()
        _ac = _ac.point(lambda p: int(p * _sa))
        _sl = Image.merge('RGBA', (_rc, _gc, _bc, _ac))
        img  = Image.alpha_composite(img.convert('RGBA'), _sl).convert('RGB')
        draw = ImageDraw.Draw(img)

    # ── PHASE 6: Text ─────────────────────────────────────────────────────
    for block in blocks:
        if block['type'] == 'heading':
            y = block['y0']
            for line in block['lines']:
                tw = draw.textbbox((0, 0), line, font=block['font'])[2]
                x  = block['cx0'] + ((block['cx1'] - block['cx0']) - tw) // 2
                draw.text((x, y), line, font=block['font'], fill=preset['heading'])
                y += block['lh']
        elif block['type'] == 'paragraph':
            y = block['y0']
            lw_list = block.get('line_widths', [])
            n_lines  = len(block['lines'])
            tmax_blk = block['cx1'] - block['cx0'] - 2 * (block['tx0'] - block['cx0'])
            for li, line in enumerate(block['lines']):
                is_last_line = (li == n_lines - 1)
                _sk = {}  # stroke applied via alpha-composite layer in Phase 5.5
                if text_align == 'justify' and not is_last_line:
                    words = line.split()
                    if len(words) > 1:
                        word_widths = [
                            draw.textbbox((0, 0), w, font=block['font'])[2]
                            for w in words]
                        total_word_w = sum(word_widths)
                        n_gaps = len(words) - 1
                        extra = (tmax_blk - total_word_w) / n_gaps
                        x = float(block['tx0'])
                        for wi, (word, ww) in enumerate(zip(words, word_widths)):
                            color = _keyword_color(word, keyword_colors, eff_text)
                            draw.text((int(x), y), word,
                                      font=block['font'], fill=color, **_sk)
                            x += ww + (extra if wi < n_gaps else 0)
                    else:
                        color = _keyword_color(line, keyword_colors, eff_text)
                        draw.text((block['tx0'], y), line,
                                  font=block['font'], fill=color, **_sk)
                else:
                    x_off = 0
                    if text_align not in ('left', 'justify') and li < len(lw_list):
                        lw = lw_list[li]
                        if text_align == 'center':
                            x_off = (tmax_blk - lw) // 2
                        elif text_align == 'right':
                            x_off = max(0, tmax_blk - lw)
                    if keyword_colors:
                        words = line.split()
                        prefix = ''
                        for wi, word in enumerate(words):
                            wx = block['tx0'] + x_off + (
                                draw.textbbox((0, 0), prefix, font=block['font'])[2]
                                if prefix else 0)
                            color = _keyword_color(word, keyword_colors, eff_text)
                            draw.text((wx, y), word,
                                      font=block['font'], fill=color, **_sk)
                            prefix += word + (' ' if wi < len(words) - 1 else '')
                    else:
                        draw.text((block['tx0'] + x_off, y), line,
                                  font=block['font'], fill=eff_text, **_sk)
                y += block['lh']

    # ── PHASE 7: Page number badge ────────────────────────────────────────
    if page_num is not None:
        r_badge = max(10, int(min(W, H) * 0.020 * max(0.5, min(2.5, badge_size))))
        def _bc(v):
            if v and isinstance(v, str) and v.startswith('#'):
                return _hex_to_rgb(v)
            return (0, 0, 0)
        b_circle = _bc(badge_circle_color)
        b_number = _bc(badge_number_color)

        diag = r_badge + max(1, border_thickness) + 6
        bp = badge_position
        if bp == 'top-left':
            pcx = max(cx0 - diag, r_badge + 2)
            pcy = max(cy0 - diag, r_badge + 2)
        elif bp == 'bottom-right':
            pcx = min(cx1 + diag, W - r_badge - 2)
            pcy = min(cy1 + diag, H - r_badge - 2)
        elif bp == 'bottom-left':
            pcx = max(cx0 - diag, r_badge + 2)
            pcy = min(cy1 + diag, H - r_badge - 2)
        elif bp == 'right-edge':
            pcx = min(cx1 + r_badge + 4, W - r_badge - 2)
            pcy = max(cy0 + r_badge * 3, r_badge + 2)
        else:  # top-right (default)
            pcx = min(cx1 + diag, W - r_badge - 2)
            pcy = max(cy0 - diag, r_badge + 2)

        if show_badge_circle:
            draw.ellipse([pcx - r_badge, pcy - r_badge,
                          pcx + r_badge, pcy + r_badge],
                         fill=None, outline=b_circle, width=2)
        num_str = str(page_num)
        try:
            nfont = ImageFont.truetype(font_body.path, size=max(8, int(r_badge * 0.85)))
        except Exception:
            nfont = font_body
        bbox = draw.textbbox((0, 0), num_str, font=nfont)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        draw.text((pcx - tw // 2, pcy - th // 2 - bbox[1]),
                  num_str, font=nfont, fill=b_number)

    # ── PHASE 8: Logo overlay (on top of everything) ──────────────────────
    if logo_path:
        img = _draw_logo(img, cx0, cy0, cx1, cy1, W, H,
                         logo_path, logo_position, logo_size, logo_opacity, logo_inside)

    return img
