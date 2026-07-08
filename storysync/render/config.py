"""All visual/style parameters for a single rendered frame.

Fields are plain Python scalars so the instance is picklable across
process boundaries (required for ProcessPoolExecutor-based rendering).
Font objects are NOT stored here — render_frame() calls load_fonts()
with the spec fields and relies on the per-process cache for speed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RenderConfig:
    # ── Font specs ─────────────────────────────────────────────────────────
    font_family:  str  = 'Georgia'
    body_size:    int  = 34
    heading_size: int  = 28
    use_bold:     bool = True
    body_stroke:  float = 0.0

    # ── Preset & colours ───────────────────────────────────────────────────
    preset:          dict          = field(default_factory=dict)
    chapter_color:   Optional[str] = None
    highlight_color: Optional[str] = None
    highlight_style: str           = 'Background bar'
    text_color:      Optional[str] = None
    bg_color:        Optional[str] = None
    card_color:      Optional[str] = None
    outline_color:   Optional[str] = None
    line_color:      Optional[str] = None

    # ── Typography ─────────────────────────────────────────────────────────
    line_spacing:   float = 1.3
    para_spacing:   float = 0.85
    text_align:     str   = 'left'
    para_empty_row: bool  = False
    para_row_line:  bool  = True

    # ── Card geometry ──────────────────────────────────────────────────────
    border_thickness: int          = 3
    texture:          Optional[str] = None
    line_thickness:   int           = 1
    hl_padding:       Optional[int] = None

    # ── Audio player ───────────────────────────────────────────────────────
    show_player:   bool  = False
    player_width:  float = 1.0
    player_height: float = 1.0
    total_time:    float = 0.0

    # ── Page number badge ──────────────────────────────────────────────────
    badge_circle_color: Optional[str] = None
    badge_number_color: Optional[str] = None
    badge_position:     str           = 'top-right'
    show_badge_circle:  bool          = True
    badge_size:         float         = 1.0

    # ── Watermark ──────────────────────────────────────────────────────────
    watermark_path:    Optional[str] = None
    watermark_opacity: float         = 0.3
    watermark_size:    float         = 0.5

    # ── Logo overlay ───────────────────────────────────────────────────────
    logo_path:     Optional[str] = None
    logo_position: str           = 'top-right'
    logo_size:     float         = 0.1
    logo_opacity:  float         = 1.0
    logo_inside:   bool          = True   # True = within card, False = in outer margin

    # ── Card border & spacing ──────────────────────────────────────────────
    show_card_border: bool  = True   # False = draw card fill only, no outline stroke
    title_body_gap:   float = 0.3    # gap below chapter heading = max(4, heading_size * this)
    card_margin:      float = 0.055  # card inset from image edges (fraction of image size)
    text_padding:     float = 0.035  # text inset from card edges (fraction of card width)
