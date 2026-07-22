"""StorySync main application."""

import ctypes
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog

import customtkinter as ctk
from PIL import Image

from storysync.config import (load_config, save_config,
                              load_custom_presets, save_custom_presets)
from storysync.constants import (
    DEEPGRAM_MODELS, GROUP_KEYS, GROUP_OPTIONS,
    HIGHLIGHT_STYLES, LANGUAGES, PRESETS, PROVIDERS, RATIOS, TEXTURES,
    TEXT_ALIGNMENTS, BADGE_POSITIONS, PAGE_TRANSITIONS, LOGO_POSITIONS,
)
from storysync.render.layout import reflow_pages
from storysync.matching import assign_timestamps, expand_compounds
from storysync.render import build_video, check_ffmpeg, load_fonts, render_frame
from storysync.render.config import RenderConfig
from storysync.render.layout import LayoutCache
from storysync.text import iter_sentences, paginate, parse_story, prompt_excerpt, story_stats
from storysync.transcription import get_timestamps, test_provider
from storysync.transcription.import_file import parse_transcript_file
from storysync.transcription.chunking import get_audio_duration


def _scrollable_combo(parent, variable, values, **kw):
    def _on_select(choice):
        variable.set(choice)
    cb = ctk.CTkComboBox(parent, values=values, command=_on_select,
                          state='readonly', **kw)
    current = variable.get()
    cb.set(current if current in values else values[0])
    return cb


def _provider_key(display_name):
    return PROVIDERS.get(display_name, 'groq')


_BADGE_POS_MAP = {
    'Top-Right Corner':    'top-right',
    'Top-Left Corner':     'top-left',
    'Bottom-Right Corner': 'bottom-right',
    'Bottom-Left Corner':  'bottom-left',
    'Right Edge':          'right-edge',
}

def _badge_pos_key(display_name):
    return _BADGE_POS_MAP.get(display_name, 'top-right')


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')
        self.title('StorySync — Story Video Maker v5')
        self.geometry('1360x860')
        self.minsize(1100, 700)

        cfg = load_config()
        self._cfg = cfg
        self._cancel_event = threading.Event()
        self._layout_cache = LayoutCache()
        self._preview_layout_cache = LayoutCache()
        self._last_pages = []
        self._preview_sent_idx = 0

        self._audio = ctk.StringVar(value=cfg.get('audio', ''))
        self._output = ctk.StringVar(value=cfg.get('output', ''))
        self._preset = ctk.StringVar(value=cfg.get('preset', 'Brown Paper'))
        self._ratio = ctk.StringVar(value=cfg.get('ratio', '16:9'))
        self._ppage = ctk.StringVar(value=str(cfg.get('per_page', 5)))
        self._lang = ctk.StringVar(value=cfg.get('language', 'de'))
        self._openai_key = ctk.StringVar(value=cfg.get('openai_api_key', ''))
        self._dg_key = ctk.StringVar(value=cfg.get('deepgram_api_key', ''))
        self._provider = ctk.StringVar(value=cfg.get('provider', list(PROVIDERS.keys())[0]))
        self._dg_model = ctk.StringVar(value=cfg.get('deepgram_model', list(DEEPGRAM_MODELS.keys())[0]))
        self._transcript_path = ctk.StringVar(value=cfg.get('transcript_path', ''))
        self._family = ctk.StringVar(value=cfg.get('font_family', 'Georgia'))
        self._bsize = ctk.IntVar(value=cfg.get('body_size', 34))
        self._hsize = ctk.IntVar(value=cfg.get('heading_size', 28))
        self._spacing = ctk.DoubleVar(value=cfg.get('line_spacing', 1.3))
        self._para_spacing = ctk.DoubleVar(value=cfg.get('para_spacing', 0.85))
        self._chapter_color = ctk.StringVar(value=cfg.get('chapter_color', ''))
        self._highlight_color = ctk.StringVar(value=cfg.get('highlight_color', ''))
        self._text_color = ctk.StringVar(value=cfg.get('text_color', ''))
        self._bg_color = ctk.StringVar(value=cfg.get('bg_color', ''))
        self._card_color = ctk.StringVar(value=cfg.get('card_color', ''))
        self._outline_color = ctk.StringVar(value=cfg.get('outline_color', ''))
        self._line_color = ctk.StringVar(value=cfg.get('line_color', ''))
        self._line_thickness = ctk.IntVar(value=cfg.get('line_thickness', 1))
        self._hl_padding = ctk.IntVar(value=cfg.get('hl_padding', 3))
        self._highlight_style = ctk.StringVar(value=cfg.get('highlight_style', HIGHLIGHT_STYLES[0]))
        self._texture = ctk.StringVar(value=cfg.get('texture', TEXTURES[0]))
        self._fast_encode = ctk.BooleanVar(value=cfg.get('fast_encode', False))
        self._show_player = ctk.BooleanVar(value=cfg.get('show_player', False))
        self._text_align = ctk.StringVar(value=cfg.get('text_align', 'Left'))
        self._badge_circle_color = ctk.StringVar(value=cfg.get('badge_circle_color', ''))
        self._badge_number_color = ctk.StringVar(value=cfg.get('badge_number_color', ''))
        self._badge_position = ctk.StringVar(value=cfg.get('badge_position', 'Top-Right Corner'))
        self._border_thickness = ctk.IntVar(value=cfg.get('border_thickness', 3))
        self._player_width  = ctk.DoubleVar(value=cfg.get('player_width', 1.0))
        self._player_height = ctk.DoubleVar(value=cfg.get('player_height', 1.0))
        self._show_badge_circle = ctk.BooleanVar(value=cfg.get('show_badge_circle', True))
        self._badge_size = ctk.DoubleVar(value=cfg.get('badge_size', 1.0))
        self._para_empty_row = ctk.BooleanVar(value=cfg.get('para_empty_row', False))
        self._para_row_line  = ctk.BooleanVar(value=cfg.get('para_row_line', True))
        self._page_transition = ctk.StringVar(value=cfg.get('page_transition', 'None'))
        self._body_bold   = ctk.BooleanVar(value=cfg.get('body_bold', True))
        self._body_stroke = ctk.DoubleVar(value=float(cfg.get('body_stroke', 0.0)))
        self._watermark_path    = ctk.StringVar(value=cfg.get('watermark_path', ''))
        self._watermark_opacity = ctk.DoubleVar(value=cfg.get('watermark_opacity', 0.3))
        self._watermark_size    = ctk.DoubleVar(value=cfg.get('watermark_size', 0.3))
        self._logo_path         = ctk.StringVar(value=cfg.get('logo_path', ''))
        self._logo_position     = ctk.StringVar(value=cfg.get('logo_position', 'Top-Right'))
        self._logo_size         = ctk.DoubleVar(value=cfg.get('logo_size', 0.1))
        self._logo_opacity      = ctk.DoubleVar(value=cfg.get('logo_opacity', 1.0))
        self._logo_inside       = ctk.BooleanVar(value=cfg.get('logo_inside', True))
        self._show_card_border  = ctk.BooleanVar(value=cfg.get('show_card_border', True))
        self._title_body_gap    = ctk.DoubleVar(value=cfg.get('title_body_gap', 0.3))
        self._card_margin       = ctk.DoubleVar(value=cfg.get('card_margin', 0.055))
        self._text_padding      = ctk.DoubleVar(value=cfg.get('text_padding', 0.035))
        self._keyword_colors    = dict(cfg.get('keyword_colors', {}))
        self._custom_presets    = load_custom_presets()
        saved_group = cfg.get('group_mode', GROUP_KEYS[0])
        self._group = ctk.StringVar(value=saved_group if saved_group in GROUP_KEYS else GROUP_KEYS[0])

        self._save_job = None
        self._preview_job = None
        self._preview_page_idx = 0
        self._render_q = queue.Queue()
        self._preview_zoom = 1.0
        self._preview_img_cache = None   # last rendered PIL image for re-zoom

        for var in (self._audio, self._output, self._preset, self._ratio, self._ppage,
                    self._lang, self._openai_key, self._dg_key, self._provider,
                    self._dg_model, self._transcript_path, self._family, self._bsize,
                    self._hsize, self._spacing, self._para_spacing, self._group,
                    self._chapter_color, self._highlight_color, self._highlight_style,
                    self._text_color, self._bg_color, self._card_color,
                    self._outline_color, self._line_color, self._line_thickness,
                    self._hl_padding, self._texture):
            var.trace_add('write', self._on_setting_change)

        for var in (self._preset, self._ratio, self._ppage, self._family, self._bsize,
                    self._hsize, self._spacing, self._para_spacing, self._group,
                    self._chapter_color, self._highlight_color, self._highlight_style,
                    self._text_color, self._bg_color, self._card_color,
                    self._outline_color, self._line_color, self._line_thickness,
                    self._hl_padding, self._texture, self._show_player,
                    self._text_align, self._badge_circle_color, self._badge_number_color,
                    self._badge_position, self._border_thickness,
                    self._player_width, self._player_height, self._show_badge_circle,
                    self._badge_size, self._para_empty_row, self._para_row_line,
                    self._body_bold, self._body_stroke,
                    self._watermark_path, self._watermark_opacity, self._watermark_size,
                    self._logo_path, self._logo_position, self._logo_size, self._logo_opacity,
                    self._logo_inside,
                    self._show_card_border, self._title_body_gap,
                    self._card_margin, self._text_padding):
            var.trace_add('write', self._on_style_change)

        self._preset.trace_add('write', self._on_preset_change)

        self._build()
        self.after(400, self._startup_checks)
        self.after(700, self._on_style_change)

        # Drag and drop
        try:
            self.drop_target_register('DND_Files')
            self.dnd_bind('<<Drop>>', self._on_drop)
        except Exception:
            pass

    def _startup_checks(self):
        if not check_ffmpeg():
            messagebox.showwarning(
                'FFmpeg not found',
                'FFmpeg/ffprobe must be installed and on your PATH.\n'
                'Video rendering will fail without it.')

    def _on_drop(self, event):
        for path in self.tk.splitlist(event.data):
            p = path.strip('{}')
            if p.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.flac')):
                self._audio.set(p)
                if not self._output.get():
                    self._output.set(str(Path(p).with_suffix('.mp4')))
            elif p.lower().endswith('.txt'):
                try:
                    text = Path(p).read_text(encoding='utf-8')
                    self._story.delete('1.0', 'end')
                    self._story.insert('1.0', text)
                    self._on_style_change()
                except Exception as e:
                    messagebox.showerror('Import failed', str(e))

    def _on_setting_change(self, *_):
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(1000, self._do_save)

    def _do_save(self):
        save_config({
            'audio': self._audio.get(),
            'output': self._output.get(),
            'preset': self._preset.get(),
            'ratio': self._ratio.get(),
            'per_page': self._ppage.get(),
            'language': self._lang.get(),
            'openai_api_key': self._openai_key.get(),
            'deepgram_api_key': self._dg_key.get(),
            'provider': self._provider.get(),
            'deepgram_model': self._dg_model.get(),
            'transcript_path': self._transcript_path.get(),
            'font_family': self._family.get(),
            'body_size': self._bsize.get(),
            'heading_size': self._hsize.get(),
            'line_spacing': self._spacing.get(),
            'para_spacing': self._para_spacing.get(),
            'group_mode': self._group.get(),
            'chapter_color': self._chapter_color.get(),
            'highlight_color': self._highlight_color.get(),
            'highlight_style': self._highlight_style.get(),
            'text_color': self._text_color.get(),
            'bg_color': self._bg_color.get(),
            'card_color': self._card_color.get(),
            'outline_color': self._outline_color.get(),
            'line_color': self._line_color.get(),
            'line_thickness': self._line_thickness.get(),
            'hl_padding': self._hl_padding.get(),
            'texture': self._texture.get(),
            'fast_encode': self._fast_encode.get(),
            'show_player': self._show_player.get(),
            'text_align': self._text_align.get(),
            'badge_circle_color': self._badge_circle_color.get(),
            'badge_number_color': self._badge_number_color.get(),
            'badge_position': self._badge_position.get(),
            'border_thickness': self._border_thickness.get(),
            'player_width': self._player_width.get(),
            'player_height': self._player_height.get(),
            'show_badge_circle': self._show_badge_circle.get(),
            'badge_size': self._badge_size.get(),
            'para_empty_row': self._para_empty_row.get(),
            'para_row_line': self._para_row_line.get(),
            'page_transition': self._page_transition.get(),
            'body_bold': self._body_bold.get(),
            'body_stroke': self._body_stroke.get(),
            'watermark_path': self._watermark_path.get(),
            'watermark_opacity': self._watermark_opacity.get(),
            'watermark_size': self._watermark_size.get(),
            'logo_path': self._logo_path.get(),
            'logo_position': self._logo_position.get(),
            'logo_size': self._logo_size.get(),
            'logo_opacity': self._logo_opacity.get(),
            'logo_inside': self._logo_inside.get(),
            'show_card_border': self._show_card_border.get(),
            'title_body_gap': self._title_body_gap.get(),
            'card_margin': self._card_margin.get(),
            'text_padding': self._text_padding.get(),
            'keyword_colors': dict(self._keyword_colors),
        })

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color=('#2b2b2b', '#1a1a1a'))
        hdr.grid(row=0, column=0, sticky='ew')
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text='  StorySync',
                     font=ctk.CTkFont(size=22, weight='bold')).grid(
            row=0, column=0, sticky='w', padx=12, pady=10)
        ctk.CTkLabel(hdr, text='story + audio  →  highlighted MP4  v5',
                     font=ctk.CTkFont(size=12), text_color='gray').grid(
            row=0, column=1, sticky='e', padx=14)

        self._tabs = ctk.CTkTabview(self, corner_radius=10)
        self._tabs.grid(row=1, column=0, padx=14, pady=(6, 0), sticky='nsew')
        self._tabs.add('Content')
        self._tabs.add('Timestamps')
        self._tabs.add('Style & Preview')

        self._build_content_tab(self._tabs.tab('Content'))
        self._build_timestamps_tab(self._tabs.tab('Timestamps'))
        self._build_style_tab(self._tabs.tab('Style & Preview'))
        self._build_bottom()

    def _build_content_tab(self, parent):
        parent.grid_columnconfigure(0, weight=3)
        parent.grid_columnconfigure(1, weight=2)
        parent.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(parent)
        left.grid(row=0, column=0, padx=(0, 8), pady=4, sticky='nsew')
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        hdr_f = ctk.CTkFrame(left, fg_color='transparent')
        hdr_f.grid(row=0, column=0, padx=12, pady=(10, 2), sticky='ew')
        hdr_f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr_f, text='Story Text',
                     font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, sticky='w')
        ctk.CTkButton(hdr_f, text='Import .txt', width=90,
                      command=self._import_story).grid(row=0, column=1, padx=4)
        ctk.CTkButton(hdr_f, text='Save Project', width=100,
                      command=self._save_project).grid(row=0, column=2, padx=4)
        ctk.CTkButton(hdr_f, text='Load Project', width=100,
                      command=self._load_project).grid(row=0, column=3)

        self._stats_lbl = ctk.CTkLabel(
            hdr_f, text='', font=ctk.CTkFont(size=10), text_color='gray')
        self._stats_lbl.grid(row=1, column=0, columnspan=4, sticky='w', pady=(2, 0))

        self._story = ctk.CTkTextbox(left, font=ctk.CTkFont(size=13), wrap='word')
        self._story.grid(row=1, column=0, padx=12, pady=(4, 12), sticky='nsew')
        self._story.bind('<KeyRelease>', lambda e: self._on_story_change())

        right = ctk.CTkScrollableFrame(
            parent, label_text='Files & Transcription',
            label_font=ctk.CTkFont(size=13, weight='bold'))
        right.grid(row=0, column=1, padx=(8, 0), pady=4, sticky='nsew')
        right.grid_columnconfigure(0, weight=1)
        r = 0

        def lbl(t):
            nonlocal r
            ctk.CTkLabel(right, text=t, font=ctk.CTkFont(size=12, weight='bold')).grid(
                row=r, column=0, padx=12, pady=(12, 2), sticky='w')
            r += 1

        def browse_row(var, cmd):
            nonlocal r
            f = ctk.CTkFrame(right, fg_color='transparent')
            f.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
            f.grid_columnconfigure(0, weight=1)
            ctk.CTkEntry(f, textvariable=var).grid(row=0, column=0, sticky='ew')
            ctk.CTkButton(f, text='Browse', width=72, command=cmd).grid(
                row=0, column=1, padx=(6, 0))
            r += 1

        lbl('Transcription Provider')
        _scrollable_combo(right, self._provider, list(PROVIDERS.keys())).grid(
            row=r, column=0, padx=12, pady=(0, 4), sticky='ew')
        r += 1

        lbl('OpenAI API Key  (whisper-1 · word-level timestamps)')
        self._openai_entry = ctk.CTkEntry(right, textvariable=self._openai_key, show='*',
                                          placeholder_text='sk-…')
        self._openai_entry.grid(row=r, column=0, padx=12, pady=(0, 4), sticky='ew')
        r += 1

        lbl('Deepgram API Key  (alternative)')
        self._dg_entry = ctk.CTkEntry(right, textvariable=self._dg_key, show='*',
                                       placeholder_text='Deepgram token')
        self._dg_entry.grid(row=r, column=0, padx=12, pady=(0, 4), sticky='ew')
        r += 1

        lbl('Deepgram Model')
        _scrollable_combo(right, self._dg_model, list(DEEPGRAM_MODELS.keys())).grid(
            row=r, column=0, padx=12, pady=(0, 4), sticky='ew')
        r += 1

        ctk.CTkLabel(right, text='── OR: Import Transcript (skips API) ──',
                     font=ctk.CTkFont(size=12, weight='bold'),
                     text_color='gray').grid(
            row=r, column=0, padx=12, pady=(10, 2), sticky='w')
        r += 1

        lbl('Transcript File  (.json / .srt / .txt — with timestamps)')
        tr_row = ctk.CTkFrame(right, fg_color='transparent')
        tr_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        tr_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(tr_row, textvariable=self._transcript_path,
                     placeholder_text='No file selected').grid(
            row=0, column=0, sticky='ew')
        ctk.CTkButton(tr_row, text='Browse', width=70,
                      command=self._browse_transcript).grid(row=0, column=1, padx=(6, 0))
        ctk.CTkButton(tr_row, text='Clear', width=56,
                      command=lambda: self._transcript_path.set('')).grid(
            row=0, column=2, padx=(6, 0))
        r += 1

        test_f = ctk.CTkFrame(right, fg_color='transparent')
        test_f.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        test_f.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(test_f, text='Test API Connection',
                      command=self._test_api).grid(row=0, column=0, sticky='ew')
        r += 1

        lbl('Audio File  (drag & drop supported)')
        browse_row(self._audio, self._browse_audio)
        ctk.CTkButton(
            right, text='Re-transcribe Audio  (clear cache)',
            fg_color='#8b4513', hover_color='#6b2f0e',
            command=self._clear_cache).grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        lbl('Output File (MP4)')
        browse_row(self._output, self._browse_output)

        lbl('Audio Language')
        _scrollable_combo(right, self._lang, LANGUAGES).grid(
            row=r, column=0, padx=12, pady=(0, 12), sticky='ew')
        r += 1

    def _build_timestamps_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(parent, fg_color='transparent')
        top.grid(row=0, column=0, padx=12, pady=8, sticky='ew')
        ctk.CTkLabel(top, text='Timestamp Review',
                     font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, sticky='w')
        ctk.CTkButton(top, text='Analyze Timestamps', width=160,
                      command=self._analyze_timestamps).grid(row=0, column=1, padx=8)
        self._ts_summary = ctk.CTkLabel(
            top, text='Run analysis after selecting audio + story.',
            font=ctk.CTkFont(size=11), text_color='gray')
        self._ts_summary.grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 0))

        self._ts_list = ctk.CTkTextbox(parent, font=ctk.CTkFont(family='Consolas', size=11))
        self._ts_list.grid(row=1, column=0, padx=12, pady=(0, 12), sticky='nsew')

    def _build_style_tab(self, parent):
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        ctrl = ctk.CTkScrollableFrame(
            parent, width=330, label_text='Typography & Style',
            label_font=ctk.CTkFont(size=13, weight='bold'))
        ctrl.grid(row=0, column=0, padx=(0, 8), pady=4, sticky='nsew')
        ctrl.grid_columnconfigure(0, weight=1)
        r = 0

        def lbl(t):
            nonlocal r
            ctk.CTkLabel(ctrl, text=t, font=ctk.CTkFont(size=12, weight='bold')).grid(
                row=r, column=0, padx=12, pady=(12, 2), sticky='w')
            r += 1

        def slider_row(var, from_, to, steps, fmt='{:.0f}'):
            nonlocal r
            frm = ctk.CTkFrame(ctrl, fg_color='transparent')
            frm.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
            frm.grid_columnconfigure(0, weight=1)
            val_lbl = ctk.CTkLabel(frm, text=fmt.format(var.get()), width=44)
            val_lbl.grid(row=0, column=1, padx=(8, 0))

            def on_slide(v):
                val_lbl.configure(text=fmt.format(float(v)))
                var.set(round(float(v), 2) if '.' in fmt else int(float(v)))

            sl = ctk.CTkSlider(frm, from_=from_, to=to, number_of_steps=steps,
                               command=on_slide)
            sl.set(var.get())
            sl.grid(row=0, column=0, sticky='ew')
            r += 1

        from storysync.constants import FONT_FILES
        lbl('Font Family')
        _scrollable_combo(ctrl, self._family, list(FONT_FILES.keys())).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        ctk.CTkCheckBox(ctrl, text='Bold body text',
                        variable=self._body_bold).grid(
            row=r, column=0, padx=14, pady=(0, 4), sticky='w')
        r += 1

        lbl('Stroke Thickness  (0.0 = off, 0.5 → 1 px)')
        slider_row(self._body_stroke, 0.0, 1.0, 10, fmt='{:.1f}')

        lbl('Body Font Size (px)')
        slider_row(self._bsize, 18, 100, 82)
        lbl('Heading Font Size (px)')
        slider_row(self._hsize, 14, 100, 86)
        lbl('Body Line Spacing')
        slider_row(self._spacing, 1.0, 2.5, 30, fmt='{:.2f}')
        lbl('Title → Body Gap  (-2.0 = overlap, 0 = tight, 2.0 = large gap)')
        slider_row(self._title_body_gap, -2.0, 2.0, 40, fmt='{:.2f}')
        lbl('Paragraph Spacing')
        slider_row(self._para_spacing, 0.2, 3.0, 56, fmt='{:.2f}')

        ctk.CTkCheckBox(ctrl,
                        text='Use empty row between paragraphs\n(overrides slider above)',
                        variable=self._para_empty_row).grid(
            row=r, column=0, padx=14, pady=(0, 4), sticky='w')
        r += 1

        ctk.CTkCheckBox(ctrl,
                        text='Show ruled line in paragraph gap\n(only when empty row is on)',
                        variable=self._para_row_line).grid(
            row=r, column=0, padx=14, pady=(0, 10), sticky='w')
        r += 1

        lbl('Paragraph Grouping')
        _scrollable_combo(ctrl, self._group, GROUP_KEYS).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        lbl('Max Sentences per Page')
        ctk.CTkEntry(ctrl, textvariable=self._ppage, width=60).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='w')
        r += 1

        lbl('Background Preset')
        all_preset_names = list(PRESETS.keys()) + list(self._custom_presets.keys())
        self._preset_combo = _scrollable_combo(ctrl, self._preset, all_preset_names)
        self._preset_combo.grid(row=r, column=0, padx=12, pady=(0, 4), sticky='ew')
        r += 1

        preset_btns = ctk.CTkFrame(ctrl, fg_color='transparent')
        preset_btns.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        preset_btns.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(preset_btns, text='Save as Preset…', height=28,
                      command=self._save_as_preset).grid(row=0, column=0, sticky='ew')
        self._delete_preset_btn = ctk.CTkButton(
            preset_btns, text='Delete Preset', width=110, height=28,
            fg_color='#8b1a1a', hover_color='#6b0e0e',
            state='disabled', command=self._delete_preset)
        self._delete_preset_btn.grid(row=0, column=1, padx=(6, 0))
        r += 1

        lbl('Card Texture')
        _scrollable_combo(ctrl, self._texture, TEXTURES).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        lbl('Highlight Style')
        _scrollable_combo(ctrl, self._highlight_style, HIGHLIGHT_STYLES).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        def _color_row(label_text, var, preset_key, btn_attr, pick_method):
            nonlocal r
            lbl(label_text)
            row_f = ctk.CTkFrame(ctrl, fg_color='transparent')
            row_f.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
            row_f.grid_columnconfigure(0, weight=1)

            def _cur():
                c = var.get()
                return c if c else PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])[preset_key]

            btn = ctk.CTkButton(row_f, text='● Change colour', fg_color=_cur(),
                                hover_color=_cur(), command=pick_method)
            btn.grid(row=0, column=0, sticky='ew')
            setattr(self, btn_attr, btn)

            def _reset():
                var.set('')
                getattr(self, btn_attr).configure(fg_color=_cur(), hover_color=_cur())

            ctk.CTkButton(row_f, text='Reset', width=62, command=_reset).grid(
                row=0, column=1, padx=(6, 0))
            r += 1

        _color_row('Highlight Colour', self._highlight_color,
                   'highlight', '_hl_btn', self._pick_highlight_color)
        _color_row('Chapter Header Colour', self._chapter_color,
                   'heading', '_ch_color_btn', self._pick_chapter_color)
        _color_row('Body Text Colour', self._text_color,
                   'text', '_text_color_btn', self._pick_text_color)
        _color_row('Outer Background Colour', self._bg_color,
                   'bg', '_bg_color_btn', self._pick_bg_color)
        _color_row('Card (Inner) Colour', self._card_color,
                   'card', '_card_color_btn', self._pick_card_color)

        lbl('Card Outline Colour')
        oc_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        oc_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        oc_row.grid_columnconfigure(0, weight=1)

        def _oc_cur():
            c = self._outline_color.get()
            return c if c else '#1a1a1a'

        self._outline_color_btn = ctk.CTkButton(
            oc_row, text='● Change colour', fg_color=_oc_cur(),
            hover_color=_oc_cur(), command=self._pick_outline_color)
        self._outline_color_btn.grid(row=0, column=0, sticky='ew')

        def _oc_reset():
            self._outline_color.set('')
            self._outline_color_btn.configure(fg_color=_oc_cur(), hover_color=_oc_cur())

        ctk.CTkButton(oc_row, text='Reset', width=62, command=_oc_reset).grid(
            row=0, column=1, padx=(6, 0))
        r += 1

        lbl('Ruled Line Colour')
        lc_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        lc_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        lc_row.grid_columnconfigure(0, weight=1)

        def _lc_cur():
            c = self._line_color.get()
            return c if c else '#6495ed'

        self._line_color_btn = ctk.CTkButton(
            lc_row, text='● Change colour', fg_color=_lc_cur(),
            hover_color=_lc_cur(), command=self._pick_line_color)
        self._line_color_btn.grid(row=0, column=0, sticky='ew')

        def _lc_reset():
            self._line_color.set('')
            self._line_color_btn.configure(fg_color=_lc_cur(), hover_color=_lc_cur())

        ctk.CTkButton(lc_row, text='Reset', width=62, command=_lc_reset).grid(
            row=0, column=1, padx=(6, 0))
        r += 1

        lbl('Line Thickness (px)')
        slider_row(self._line_thickness, 1, 6, 5)

        lbl('Highlight Padding (px)  — smaller = tighter to ruled lines')
        slider_row(self._hl_padding, 1, 14, 13)

        lbl('Aspect Ratio')
        _scrollable_combo(ctrl, self._ratio, list(RATIOS.keys())).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        ctk.CTkCheckBox(ctrl, text='Fast encode (draft quality)',
                        variable=self._fast_encode).grid(
            row=r, column=0, padx=14, pady=(4, 4), sticky='w')
        r += 1

        ctk.CTkCheckBox(ctrl, text='Show audio player (9:16 portrait only)',
                        variable=self._show_player).grid(
            row=r, column=0, padx=14, pady=(0, 4), sticky='w')
        r += 1

        lbl('Player Width')
        slider_row(self._player_width, 0.2, 2.0, 36, fmt='{:.2f}')
        lbl('Player Height')
        slider_row(self._player_height, 0.3, 2.0, 34, fmt='{:.2f}')

        lbl('Text Alignment')
        _scrollable_combo(ctrl, self._text_align, TEXT_ALIGNMENTS).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        ctk.CTkCheckBox(ctrl, text='Show card border outline',
                        variable=self._show_card_border,
                        command=self._on_style_change).grid(
            row=r, column=0, padx=12, pady=(4, 6), sticky='w')
        r += 1
        lbl('Card Border Thickness (px)')
        slider_row(self._border_thickness, 1, 12, 11)
        lbl('Card Margin  (outer space from image edge to card)')
        slider_row(self._card_margin, 0.0, 0.12, 24, fmt='{:.1%}')
        lbl('Text Padding  (inner inset from card edge to text)')
        slider_row(self._text_padding, 0.01, 0.15, 28, fmt='{:.1%}')

        lbl('Page Number Position')
        _scrollable_combo(ctrl, self._badge_position, BADGE_POSITIONS).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        ctk.CTkCheckBox(ctrl, text='Show circle around page number',
                        variable=self._show_badge_circle).grid(
            row=r, column=0, padx=14, pady=(0, 4), sticky='w')
        r += 1

        lbl('Page Number Size')
        slider_row(self._badge_size, 0.5, 2.5, 20, fmt='{:.2f}')

        # Badge circle color
        lbl('Badge Circle Colour')
        bc_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        bc_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        bc_row.grid_columnconfigure(0, weight=1)

        def _bcc_cur():
            c = self._badge_circle_color.get()
            return c if c else '#000000'

        self._badge_circle_btn = ctk.CTkButton(
            bc_row, text='● Change colour', fg_color=_bcc_cur(),
            hover_color=_bcc_cur(), command=self._pick_badge_circle_color)
        self._badge_circle_btn.grid(row=0, column=0, sticky='ew')

        def _bcc_reset():
            self._badge_circle_color.set('')
            self._badge_circle_btn.configure(fg_color=_bcc_cur(), hover_color=_bcc_cur())

        ctk.CTkButton(bc_row, text='Reset', width=62, command=_bcc_reset).grid(
            row=0, column=1, padx=(6, 0))
        r += 1

        # Badge number color
        lbl('Badge Number Colour')
        bn_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        bn_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        bn_row.grid_columnconfigure(0, weight=1)

        def _bnc_cur():
            c = self._badge_number_color.get()
            return c if c else '#000000'

        self._badge_number_btn = ctk.CTkButton(
            bn_row, text='● Change colour', fg_color=_bnc_cur(),
            hover_color=_bnc_cur(), command=self._pick_badge_number_color)
        self._badge_number_btn.grid(row=0, column=0, sticky='ew')

        def _bnc_reset():
            self._badge_number_color.set('')
            self._badge_number_btn.configure(fg_color=_bnc_cur(), hover_color=_bnc_cur())

        ctk.CTkButton(bn_row, text='Reset', width=62, command=_bnc_reset).grid(
            row=0, column=1, padx=(6, 0))
        r += 1

        lbl('Page Transition')
        _scrollable_combo(ctrl, self._page_transition, PAGE_TRANSITIONS).grid(
            row=r, column=0, padx=12, pady=(0, 12), sticky='ew')
        r += 1

        # ── Watermark ──────────────────────────────────────────────────────
        ctk.CTkLabel(ctrl, text='── Watermark ──',
                     font=ctk.CTkFont(size=12, weight='bold'),
                     text_color='gray').grid(
            row=r, column=0, padx=12, pady=(8, 4), sticky='w')
        r += 1

        lbl('Watermark Image  (PNG/JPG, leave blank = none)')
        wm_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        wm_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        wm_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(wm_row, textvariable=self._watermark_path,
                     placeholder_text='No file selected').grid(
            row=0, column=0, sticky='ew')
        ctk.CTkButton(wm_row, text='Browse', width=70,
                      command=self._browse_watermark).grid(
            row=0, column=1, padx=(6, 0))
        r += 1

        lbl('Watermark Opacity  (0 = invisible, 1 = solid)')
        slider_row(self._watermark_opacity, 0.0, 1.0, 20, fmt='{:.2f}')
        lbl('Watermark Size  (fraction of card)')
        slider_row(self._watermark_size, 0.03, 0.75, 36, fmt='{:.2f}')

        # ── Logo ───────────────────────────────────────────────────────────
        ctk.CTkLabel(ctrl, text='── Logo Overlay ──',
                     font=ctk.CTkFont(size=12, weight='bold'),
                     text_color='gray').grid(
            row=r, column=0, padx=12, pady=(8, 4), sticky='w')
        r += 1

        lbl('Logo Image File  (PNG/JPG with transparency)')
        logo_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        logo_row.grid(row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        logo_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(logo_row, textvariable=self._logo_path,
                     placeholder_text='No file selected').grid(
            row=0, column=0, sticky='ew')
        ctk.CTkButton(logo_row, text='Browse', width=70,
                      command=self._browse_logo).grid(
            row=0, column=1, padx=(6, 0))
        r += 1

        lbl('Logo Position')
        _scrollable_combo(ctrl, self._logo_position, LOGO_POSITIONS).grid(
            row=r, column=0, padx=12, pady=(0, 8), sticky='ew')
        r += 1

        ctk.CTkCheckBox(ctrl, text='Place logo inside card border\n(uncheck = in outer margin)',
                        variable=self._logo_inside).grid(
            row=r, column=0, padx=14, pady=(0, 8), sticky='w')
        r += 1

        lbl('Logo Size  (fraction of card)')
        slider_row(self._logo_size, 0.03, 0.5, 47, fmt='{:.2f}')
        lbl('Logo Opacity  (0 = invisible, 1 = solid)')
        slider_row(self._logo_opacity, 0.0, 1.0, 20, fmt='{:.2f}')

        # ── Keyword Word Colours ────────────────────────────────────────────
        ctk.CTkLabel(ctrl, text='── Keyword Word Colours ──',
                     font=ctk.CTkFont(size=12, weight='bold'),
                     text_color='gray').grid(
            row=r, column=0, padx=12, pady=(8, 4), sticky='w')
        r += 1

        lbl('Colour every occurrence of a word in the body text\n'
            '(whole word, case-insensitive — heading text is unaffected)')

        kw_add_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        kw_add_row.grid(row=r, column=0, padx=12, pady=(0, 6), sticky='ew')
        kw_add_row.grid_columnconfigure(0, weight=1)
        self._kw_entry = ctk.CTkEntry(kw_add_row, placeholder_text='word, e.g. endlich')
        self._kw_entry.grid(row=0, column=0, sticky='ew')
        self._kw_entry.bind('<Return>', lambda e: self._add_keyword_color())
        self._kw_new_color = '#e02020'
        self._kw_color_btn = ctk.CTkButton(
            kw_add_row, text='●', width=32, fg_color=self._kw_new_color,
            hover_color=self._kw_new_color, command=self._pick_keyword_new_color)
        self._kw_color_btn.grid(row=0, column=1, padx=(6, 0))
        ctk.CTkButton(kw_add_row, text='Add', width=52,
                      command=self._add_keyword_color).grid(row=0, column=2, padx=(6, 0))
        r += 1

        self._kw_list_frame = ctk.CTkFrame(ctrl, fg_color='transparent')
        self._kw_list_frame.grid(row=r, column=0, padx=12, pady=(0, 10), sticky='ew')
        self._kw_list_frame.grid_columnconfigure(0, weight=1)
        r += 1

        self._refresh_keyword_list()

        prev_frm = ctk.CTkFrame(parent)
        prev_frm.grid(row=0, column=1, padx=(8, 0), pady=4, sticky='nsew')
        prev_frm.grid_rowconfigure(1, weight=1)
        prev_frm.grid_columnconfigure(0, weight=1)

        nav = ctk.CTkFrame(prev_frm, fg_color='transparent')
        nav.grid(row=0, column=0, sticky='ew', padx=10, pady=(8, 4))
        nav.grid_columnconfigure(2, weight=1)
        self._prev_btn = ctk.CTkButton(nav, text='◀ Page', width=80, command=self._prev_page)
        self._prev_btn.grid(row=0, column=0)
        self._page_lbl = ctk.CTkLabel(nav, text='Page — / —', font=ctk.CTkFont(size=13))
        self._page_lbl.grid(row=0, column=1, padx=8)
        self._next_btn = ctk.CTkButton(nav, text='Page ▶', width=80, command=self._next_page)
        self._next_btn.grid(row=0, column=2, sticky='e')

        # Zoom controls
        zoom_f = ctk.CTkFrame(nav, fg_color='transparent')
        zoom_f.grid(row=0, column=3, padx=(12, 0))
        ctk.CTkButton(zoom_f, text='−', width=28, height=28,
                      command=self._zoom_out).grid(row=0, column=0)
        self._zoom_lbl = ctk.CTkLabel(zoom_f, text='100%',
                                       font=ctk.CTkFont(size=11), width=42)
        self._zoom_lbl.grid(row=0, column=1, padx=2)
        ctk.CTkButton(zoom_f, text='+', width=28, height=28,
                      command=self._zoom_in).grid(row=0, column=2)

        sent_nav = ctk.CTkFrame(prev_frm, fg_color='transparent')
        sent_nav.grid(row=0, column=0, sticky='ew', padx=10, pady=(44, 0))
        sent_nav.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(sent_nav, text='◀ Sent', width=70,
                      command=self._prev_sentence).grid(row=0, column=0)
        self._sent_lbl = ctk.CTkLabel(sent_nav, text='Highlight: sentence 1',
                                       font=ctk.CTkFont(size=11), text_color='gray')
        self._sent_lbl.grid(row=0, column=1)
        ctk.CTkButton(sent_nav, text='Sent ▶', width=70,
                      command=self._next_sentence).grid(row=0, column=2)

        self._preview_lbl = ctk.CTkLabel(
            prev_frm, text='← Paste story text to see preview',
            font=ctk.CTkFont(size=14), text_color='gray')
        self._preview_lbl.grid(row=1, column=0, sticky='nsew', padx=10, pady=(0, 10))

        # Mouse-wheel zoom on the preview
        def _on_wheel(event):
            delta = getattr(event, 'delta', 0)
            if delta > 0 or getattr(event, 'num', 0) == 4:
                self._zoom_in()
            elif delta < 0 or getattr(event, 'num', 0) == 5:
                self._zoom_out()

        self._preview_lbl.bind('<MouseWheel>', _on_wheel)
        self._preview_lbl.bind('<Button-4>', _on_wheel)
        self._preview_lbl.bind('<Button-5>', _on_wheel)

    def _build_bottom(self):
        bot = ctk.CTkFrame(self, height=82)
        bot.grid(row=2, column=0, padx=14, pady=(4, 12), sticky='ew')
        bot.grid_columnconfigure(0, weight=1)

        self._bar = ctk.CTkProgressBar(bot)
        self._bar.grid(row=0, column=0, padx=14, pady=(10, 4), sticky='ew')
        self._bar.set(0)

        self._status_lbl = ctk.CTkLabel(
            bot, text='Ready — paste story, choose audio, click Render.',
            font=ctk.CTkFont(size=12), text_color='gray')
        self._status_lbl.grid(row=1, column=0, padx=14, pady=(0, 8), sticky='w')

        btn_f = ctk.CTkFrame(bot, fg_color='transparent')
        btn_f.grid(row=0, column=1, rowspan=2, padx=14, pady=8)
        self._cancel_btn = ctk.CTkButton(
            btn_f, text='Cancel', width=90, height=38,
            fg_color='#666', hover_color='#444',
            state='disabled', command=self._cancel_render)
        self._cancel_btn.grid(row=0, column=0, padx=(0, 8))
        self._btn = ctk.CTkButton(
            btn_f, text='  Render Video  ', height=42, width=150,
            font=ctk.CTkFont(size=14, weight='bold'),
            command=self._start_render)
        self._btn.grid(row=0, column=1)

    # ── Custom preset management ──────────────────────────────────────────────

    # Keys saved into / loaded from a custom preset (everything visual/style).
    _PRESET_KEYS = [
        'font_family', 'body_size', 'heading_size', 'body_bold', 'body_stroke',
        'highlight_style', 'texture', 'text_align', 'page_transition',
        'chapter_color', 'highlight_color', 'text_color', 'bg_color',
        'card_color', 'outline_color', 'line_color',
        'line_spacing', 'para_spacing', 'border_thickness',
        'line_thickness', 'hl_padding',
        'show_player', 'player_width', 'player_height',
        'badge_circle_color', 'badge_number_color', 'badge_position',
        'show_badge_circle', 'badge_size',
        'para_empty_row', 'para_row_line',
        'watermark_path', 'watermark_opacity', 'watermark_size',
        'logo_path', 'logo_position', 'logo_size', 'logo_opacity', 'logo_inside',
        'show_card_border', 'title_body_gap',
        'card_margin', 'text_padding',
    ]

    def _on_preset_change(self, *_):
        name = self._preset.get()
        if name in self._custom_presets:
            self._apply_preset_settings(self._custom_presets[name])
        # Enable/disable Delete button
        is_custom = name in self._custom_presets
        if hasattr(self, '_delete_preset_btn'):
            self._delete_preset_btn.configure(
                state='normal' if is_custom else 'disabled')

    def _save_as_preset(self):
        name = simpledialog.askstring(
            'Save Preset', 'Enter a name for this preset:',
            parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in PRESETS:
            messagebox.showwarning(
                'Name taken',
                f'"{name}" is a built-in preset name. Choose a different name.')
            return
        if name in self._custom_presets:
            if not messagebox.askyesno(
                    'Overwrite?', f'Preset "{name}" already exists. Overwrite?'):
                return
        settings = self._collect_preset_settings()
        self._custom_presets[name] = settings
        save_custom_presets(self._custom_presets)
        # Update dropdown to include new preset
        all_names = list(PRESETS.keys()) + list(self._custom_presets.keys())
        self._preset_combo.configure(values=all_names)
        self._preset.set(name)
        self._status(f'Preset "{name}" saved.')

    def _delete_preset(self):
        name = self._preset.get()
        if name not in self._custom_presets:
            return
        if not messagebox.askyesno('Delete?', f'Delete preset "{name}"?'):
            return
        del self._custom_presets[name]
        save_custom_presets(self._custom_presets)
        all_names = list(PRESETS.keys()) + list(self._custom_presets.keys())
        self._preset_combo.configure(values=all_names)
        self._preset.set(list(PRESETS.keys())[0])
        self._delete_preset_btn.configure(state='disabled')
        self._status(f'Preset "{name}" deleted.')

    def _collect_preset_settings(self) -> dict:
        """Snapshot the current UI state as a preset dict."""
        var_map = self._preset_var_map()
        return {k: v.get() for k, v in var_map.items()}

    def _apply_preset_settings(self, settings: dict):
        """Set all UI vars from a saved preset dict, then refresh buttons."""
        var_map = self._preset_var_map()
        for key, var in var_map.items():
            if key in settings:
                var.set(settings[key])
        self.after(0, self._refresh_color_buttons)

    def _preset_var_map(self) -> dict:
        """Return {key: tkVar} for all style settings included in presets."""
        return {
            'font_family':        self._family,
            'body_size':          self._bsize,
            'heading_size':       self._hsize,
            'body_bold':          self._body_bold,
            'body_stroke':        self._body_stroke,
            'highlight_style':    self._highlight_style,
            'texture':            self._texture,
            'text_align':         self._text_align,
            'page_transition':    self._page_transition,
            'chapter_color':      self._chapter_color,
            'highlight_color':    self._highlight_color,
            'text_color':         self._text_color,
            'bg_color':           self._bg_color,
            'card_color':         self._card_color,
            'outline_color':      self._outline_color,
            'line_color':         self._line_color,
            'line_spacing':       self._spacing,
            'para_spacing':       self._para_spacing,
            'border_thickness':   self._border_thickness,
            'line_thickness':     self._line_thickness,
            'hl_padding':         self._hl_padding,
            'show_player':        self._show_player,
            'player_width':       self._player_width,
            'player_height':      self._player_height,
            'badge_circle_color': self._badge_circle_color,
            'badge_number_color': self._badge_number_color,
            'badge_position':     self._badge_position,
            'show_badge_circle':  self._show_badge_circle,
            'badge_size':         self._badge_size,
            'para_empty_row':     self._para_empty_row,
            'para_row_line':      self._para_row_line,
            'watermark_path':     self._watermark_path,
            'watermark_opacity':  self._watermark_opacity,
            'watermark_size':     self._watermark_size,
            'logo_path':          self._logo_path,
            'logo_position':      self._logo_position,
            'logo_size':          self._logo_size,
            'logo_opacity':       self._logo_opacity,
            'logo_inside':        self._logo_inside,
            'show_card_border':   self._show_card_border,
            'title_body_gap':     self._title_body_gap,
            'card_margin':        self._card_margin,
            'text_padding':       self._text_padding,
        }

    def _refresh_color_buttons(self):
        """Sync all colour picker button faces with the current var values."""
        p = PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])

        def _c(var, fallback):
            v = var.get()
            return v if v else fallback

        pairs = [
            ('_hl_btn',           self._highlight_color,   p['highlight']),
            ('_ch_color_btn',     self._chapter_color,     p['heading']),
            ('_text_color_btn',   self._text_color,        p['text']),
            ('_bg_color_btn',     self._bg_color,          p['bg']),
            ('_card_color_btn',   self._card_color,        p['card']),
            ('_outline_color_btn', self._outline_color,    '#1a1a1a'),
            ('_line_color_btn',   self._line_color,        '#6495ed'),
            ('_badge_circle_btn', self._badge_circle_color, '#000000'),
            ('_badge_number_btn', self._badge_number_color, '#000000'),
        ]
        for attr, var, fallback in pairs:
            if hasattr(self, attr):
                col = _c(var, fallback)
                getattr(self, attr).configure(fg_color=col, hover_color=col)

    def _build_render_cfg(self, total_time: float = 0.0) -> RenderConfig:
        """Build a RenderConfig from the current UI state.

        Call on the main thread so all StringVar / IntVar reads are safe.
        Pass total_time=0 for previews; the video worker sets it to the real
        audio duration before calling build_video().
        """
        return RenderConfig(
            font_family=self._family.get(),
            body_size=self._bsize.get(),
            heading_size=self._hsize.get(),
            use_bold=self._body_bold.get(),
            body_stroke=self._body_stroke.get(),
            preset=PRESETS.get(self._preset.get(), PRESETS['Brown Paper']),
            chapter_color=self._chapter_color.get() or None,
            highlight_color=self._highlight_color.get() or None,
            highlight_style=self._highlight_style.get(),
            text_color=self._text_color.get() or None,
            bg_color=self._bg_color.get() or None,
            card_color=self._card_color.get() or None,
            outline_color=self._outline_color.get() or None,
            line_color=self._line_color.get() or None,
            line_spacing=self._spacing.get(),
            para_spacing=self._para_spacing.get(),
            text_align=self._text_align.get().lower(),
            para_empty_row=self._para_empty_row.get(),
            para_row_line=self._para_row_line.get(),
            border_thickness=self._border_thickness.get(),
            texture=self._texture.get() or None,
            line_thickness=self._line_thickness.get(),
            hl_padding=self._hl_padding.get(),
            show_player=self._show_player.get(),
            player_width=self._player_width.get(),
            player_height=self._player_height.get(),
            total_time=total_time,
            badge_circle_color=self._badge_circle_color.get() or None,
            badge_number_color=self._badge_number_color.get() or None,
            badge_position=_badge_pos_key(self._badge_position.get()),
            show_badge_circle=self._show_badge_circle.get(),
            badge_size=self._badge_size.get(),
            watermark_path=self._watermark_path.get() or None,
            watermark_opacity=self._watermark_opacity.get(),
            watermark_size=self._watermark_size.get(),
            logo_path=self._logo_path.get() or None,
            logo_position=self._logo_position.get().lower(),
            logo_size=self._logo_size.get(),
            logo_opacity=self._logo_opacity.get(),
            logo_inside=self._logo_inside.get(),
            show_card_border=self._show_card_border.get(),
            title_body_gap=self._title_body_gap.get(),
            card_margin=self._card_margin.get(),
            text_padding=self._text_padding.get(),
            keyword_colors=dict(self._keyword_colors),
        )

    def _on_story_change(self):
        text = self._story.get('1.0', 'end').strip()
        if text:
            ns, nw, np = story_stats(text)
            self._stats_lbl.configure(text=f'{nw} words · {ns} sentences · ~{np} pages')
        else:
            self._stats_lbl.configure(text='')
        self._on_style_change()

    def _on_style_change(self, *_):
        self._preview_layout_cache.clear()
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(650, self._refresh_preview_async)

    def _get_preview_pages(self):
        story_text = self._story.get('1.0', 'end').strip()
        if not story_text:
            return [], story_text
        group_size = GROUP_OPTIONS.get(self._group.get(), 0)
        try:
            per_page = max(1, min(20, int(self._ppage.get() or 5)))
        except ValueError:
            per_page = 5
        items = parse_story(story_text, group_size)
        return paginate(items, per_page), story_text

    def _page_sentences(self, page):
        sents = []
        for item in page['items']:
            if item['type'] == 'paragraph':
                sents.extend(item['sentences'])
        return sents

    def _refresh_preview_async(self):
        pages, _ = self._get_preview_pages()
        self._last_pages = pages
        if not pages:
            self._preview_lbl.configure(
                text='← Paste story text to see preview', image=None)
            self._page_lbl.configure(text='Page — / —')
            return

        W, H = RATIOS.get(self._ratio.get(), (1920, 1080))
        # Render the preview at the exact same resolution as the final
        # export. A downscaled preview canvas needs its font sizes scaled
        # down too, and int()-truncating those sizes shifts word-wrap
        # points just enough that a different number of sentences fit per
        # page than at full resolution — the preview would then paginate
        # differently from the real render (e.g. showing 6 sentences fit
        # on a page when only 5 actually do). Rendering at full size makes
        # layout/wrapping/pagination pixel-identical to the export; the
        # display-side zoom/resize in _apply_preview_zoom handles shrinking
        # it to fit the on-screen preview pane.
        pW, pH = W, H

        # Build config on the main thread (StringVar/IntVar reads must be here).
        cfg = self._build_render_cfg()

        # Use safe_idx for read-only access; _show_preview clamps it later.
        safe_idx = min(self._preview_page_idx, len(pages) - 1)
        page_data = pages[safe_idx]
        sents = self._page_sentences(page_data)
        safe_sent_idx = min(self._preview_sent_idx, max(0, len(sents) - 1))

        self._page_lbl.configure(text=f'Page {self._preview_page_idx + 1} / {len(pages)}')
        self._sent_lbl.configure(
            text=f'Highlight: sentence {safe_sent_idx + 1} / {max(1, len(sents))}')

        prev_page_idx = self._preview_page_idx
        prev_sent_idx = self._preview_sent_idx

        def do_render():
            fb, fh = load_fonts(cfg.font_family, cfg.body_size,
                                 cfg.heading_size, cfg.use_bold)
            reflowed = reflow_pages(pages, fb, fh, pW, pH, cfg.line_spacing,
                                    para_spacing=cfg.para_spacing,
                                    para_empty_row=cfg.para_empty_row,
                                    show_player=cfg.show_player,
                                    player_height=cfg.player_height,
                                    title_body_gap=cfg.title_body_gap,
                                    card_margin=cfg.card_margin,
                                    text_padding=cfg.text_padding)
            p_idx  = min(prev_page_idx, max(0, len(reflowed) - 1))
            p_data = reflowed[p_idx] if reflowed else None
            if p_data is None:
                return
            sents  = self._page_sentences(p_data)
            s_idx  = min(prev_sent_idx, max(0, len(sents) - 1))
            act    = sents[s_idx]['text'] if sents else None
            act_id = sents[s_idx].get('_id') if sents else None
            n_sents = max(1, len(sents))
            img = render_frame(
                pW, pH, p_data['items'], cfg,
                active_text=act,
                active_sentence_id=act_id,
                page_chapter=p_data.get('chapter'),
                page_num=p_idx + 1,
                current_time=0.0,
                layout_cache=self._preview_layout_cache)
            self.after(0, lambda i=img, r=reflowed, ns=n_sents, si=s_idx:
                       self._show_preview(i, r, ns, si + 1))

        threading.Thread(target=do_render, daemon=True).start()

    def _show_preview(self, img, reflowed_pages, n_sents=1, sent_num=1):
        self._last_pages = reflowed_pages
        total_pages = len(reflowed_pages)
        if self._preview_page_idx >= total_pages:
            self._preview_page_idx = max(0, total_pages - 1)
        self._preview_img_cache = img
        self._preview_n_sents = n_sents
        self._preview_sent_num = sent_num
        self._apply_preview_zoom()
        self._page_lbl.configure(text=f'Page {self._preview_page_idx + 1} / {total_pages}')
        self._sent_lbl.configure(text=f'Highlight: sentence {sent_num} / {n_sents}')

    def _apply_preview_zoom(self):
        img = self._preview_img_cache
        if img is None:
            return
        lbl = self._preview_lbl
        lbl.update_idletasks()
        avail_w = max(100, lbl.winfo_width() - 20)
        avail_h = max(100, lbl.winfo_height() - 20)
        # Base scale to fit label area
        base_scale = min(avail_w / img.width, avail_h / img.height)
        # Apply user zoom on top
        zoomed_scale = base_scale * self._preview_zoom
        disp_w = max(1, int(img.width * zoomed_scale))
        disp_h = max(1, int(img.height * zoomed_scale))
        if self._preview_zoom > 1.0:
            # When zoomed in, crop from centre before resizing
            crop_w = int(img.width / self._preview_zoom)
            crop_h = int(img.height / self._preview_zoom)
            cx = img.width // 2
            cy = img.height // 2
            box = (cx - crop_w // 2, cy - crop_h // 2,
                   cx + crop_w // 2, cy + crop_h // 2)
            cropped = img.crop(box)
            display = cropped.resize(
                (max(1, int(avail_w)), max(1, int(avail_h))), Image.LANCZOS)
            disp_w, disp_h = display.width, display.height
        else:
            display = img.resize((disp_w, disp_h), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=display, dark_image=display,
                               size=(disp_w, disp_h))
        lbl.configure(image=ctk_img, text='')
        lbl._image_ref = ctk_img

    def _zoom_in(self):
        self._preview_zoom = min(4.0, round(self._preview_zoom * 1.3, 2))
        self._zoom_lbl.configure(text=f'{int(self._preview_zoom * 100)}%')
        self._apply_preview_zoom()

    def _zoom_out(self):
        self._preview_zoom = max(0.4, round(self._preview_zoom / 1.3, 2))
        self._zoom_lbl.configure(text=f'{int(self._preview_zoom * 100)}%')
        self._apply_preview_zoom()

    def _prev_page(self):
        if self._preview_page_idx > 0:
            self._preview_page_idx -= 1
            self._preview_sent_idx = 0
            self._refresh_preview_async()

    def _next_page(self):
        if self._preview_page_idx < len(self._last_pages) - 1:
            self._preview_page_idx += 1
            self._preview_sent_idx = 0
            self._refresh_preview_async()

    def _prev_sentence(self):
        if self._preview_sent_idx > 0:
            self._preview_sent_idx -= 1
            self._refresh_preview_async()

    def _next_sentence(self):
        if not self._last_pages:
            return
        safe_idx = min(self._preview_page_idx, len(self._last_pages) - 1)
        sents = self._page_sentences(self._last_pages[safe_idx])
        if self._preview_sent_idx < len(sents) - 1:
            self._preview_sent_idx += 1
            self._refresh_preview_async()

    def _active_api_key(self):
        prov = _provider_key(self._provider.get())
        if prov == 'openai':
            return self._openai_key.get().strip()
        return self._dg_key.get().strip()

    def _test_api(self):
        key = self._active_api_key()
        if not key:
            messagebox.showwarning('No key', 'Enter an API key first.')
            return
        prov = _provider_key(self._provider.get())

        def work():
            ok, msg = test_provider(prov, key)
            self.after(0, lambda: messagebox.showinfo(
                'API Test', f'{"✓" if ok else "✗"} {msg}'))

        threading.Thread(target=work, daemon=True).start()

    def _analyze_timestamps(self):
        story = self._story.get('1.0', 'end').strip()
        audio = self._audio.get().strip()
        transcript_path = self._transcript_path.get().strip()
        key = self._active_api_key()
        if not story or not audio:
            messagebox.showwarning('Missing', 'Need story and audio.')
            return
        if not transcript_path and not key:
            messagebox.showwarning(
                'Missing', 'Need an API key, or an imported transcript file (JSON/SRT/TXT).')
            return
        if transcript_path and not Path(transcript_path).exists():
            messagebox.showwarning('Missing', 'Transcript file not found.')
            return

        self._ts_summary.configure(text='Analyzing…')
        self._ts_list.delete('1.0', 'end')

        def work():
            try:
                prov = _provider_key(self._provider.get())
                if transcript_path:
                    words, utts = parse_transcript_file(transcript_path)
                else:
                    cache = str(Path(audio).with_suffix('.timestamps.json'))
                    words, utts = get_timestamps(
                        audio, cache, prov, key, self._lang.get(),
                        deepgram_model=DEEPGRAM_MODELS.get(self._dg_model.get(), 'nova-3'),
                        story_prompt=prompt_excerpt(story))
                words = expand_compounds(words, story)
                group_size = GROUP_OPTIONS.get(self._group.get(), 0)
                per_page = max(1, min(20, int(self._ppage.get() or 5)))
                pages = paginate(parse_story(story, group_size), per_page)
                total_dur = get_audio_duration(audio)
                assign_timestamps(pages, words, utts, total_dur)

                lines = []
                low = 0
                for i, sent in enumerate(iter_sentences(pages), 1):
                    conf = sent.get('confidence', 0)
                    flag = ' ⚠' if conf < 0.4 else ''
                    if conf < 0.4:
                        low += 1
                    t = sent.get('startTime', 0)
                    snippet = sent['text'][:60] + ('…' if len(sent['text']) > 60 else '')
                    lines.append(f'{i:4d}  {t:7.2f}s  {conf*100:4.0f}%  {snippet}{flag}')

                source = 'imported transcript' if transcript_path else f'provider: {prov}'
                summary = f'{len(lines)} sentences · {low} low-confidence · {source}'
                self.after(0, lambda: self._show_ts_results(summary, '\n'.join(lines)))
            except Exception as e:
                self.after(0, lambda: self._ts_summary.configure(text=f'Error: {e}'))

        threading.Thread(target=work, daemon=True).start()

    def _show_ts_results(self, summary, text):
        self._ts_summary.configure(text=summary)
        self._ts_list.delete('1.0', 'end')
        self._ts_list.insert('1.0', text)

    def _import_story(self):
        p = filedialog.askopenfilename(filetypes=[('Text', '*.txt'), ('All', '*.*')])
        if p:
            try:
                self._story.delete('1.0', 'end')
                self._story.insert('1.0', Path(p).read_text(encoding='utf-8'))
                self._on_story_change()
            except Exception as e:
                messagebox.showerror('Import failed', str(e))

    def _save_project(self):
        p = filedialog.asksaveasfilename(
            defaultextension='.storysync', filetypes=[('StorySync Project', '*.storysync')])
        if not p:
            return
        data = {
            'story': self._story.get('1.0', 'end').strip(),
            'settings': {
                'audio': self._audio.get(),
                'output': self._output.get(),
                'preset': self._preset.get(),
                'ratio': self._ratio.get(),
                'per_page': self._ppage.get(),
                'language': self._lang.get(),
                'provider': self._provider.get(),
                'group_mode': self._group.get(),
            },
        }
        Path(p).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        self._status(f'Project saved: {p}')

    def _load_project(self):
        p = filedialog.askopenfilename(filetypes=[('StorySync Project', '*.storysync')])
        if not p:
            return
        try:
            data = json.loads(Path(p).read_text(encoding='utf-8'))
            self._story.delete('1.0', 'end')
            self._story.insert('1.0', data.get('story', ''))
            s = data.get('settings', {})
            for k, var in [('audio', self._audio), ('output', self._output),
                           ('preset', self._preset), ('ratio', self._ratio),
                           ('per_page', self._ppage), ('language', self._lang),
                           ('provider', self._provider), ('group_mode', self._group)]:
                if k in s:
                    var.set(str(s[k]))
            self._on_story_change()
            self._status(f'Project loaded: {p}')
        except Exception as e:
            messagebox.showerror('Load failed', str(e))

    def _clear_cache(self):
        audio = self._audio.get().strip()
        if not audio:
            messagebox.showwarning('No audio', 'Select an audio file first.')
            return
        cache = Path(audio).with_suffix('.timestamps.json')
        if cache.exists():
            if messagebox.askyesno('Re-transcribe?',
                                   f'Delete cached timestamps for {cache.name}?'):
                cache.unlink()
                self._status('Cache cleared — will re-transcribe on next render.')
        else:
            messagebox.showinfo('No cache', 'No timestamp cache found.')

    def _pick_color(self, var, btn_attr, title, default='#000000'):
        """Generic colour-picker: open dialog, write to var, update button."""
        current = var.get() or default
        result = colorchooser.askcolor(color=current, title=title)
        if result and result[1]:
            var.set(result[1])
            getattr(self, btn_attr).configure(fg_color=result[1], hover_color=result[1])

    def _pick_highlight_color(self):
        p = PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])
        self._pick_color(self._highlight_color, '_hl_btn', 'Highlight Colour', p['highlight'])

    def _pick_chapter_color(self):
        p = PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])
        self._pick_color(self._chapter_color, '_ch_color_btn', 'Chapter Header Colour', p['heading'])

    def _pick_text_color(self):
        p = PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])
        self._pick_color(self._text_color, '_text_color_btn', 'Body Text Colour', p['text'])

    def _pick_bg_color(self):
        p = PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])
        self._pick_color(self._bg_color, '_bg_color_btn', 'Outer Background Colour', p['bg'])

    def _pick_card_color(self):
        p = PRESETS.get(self._preset.get(), PRESETS['Brown Paper'])
        self._pick_color(self._card_color, '_card_color_btn', 'Card (Inner) Colour', p['card'])

    def _pick_outline_color(self):
        self._pick_color(self._outline_color, '_outline_color_btn', 'Card Outline Colour', '#1a1a1a')

    def _pick_line_color(self):
        self._pick_color(self._line_color, '_line_color_btn', 'Ruled Line Colour', '#6495ed')

    def _pick_badge_circle_color(self):
        self._pick_color(self._badge_circle_color, '_badge_circle_btn', 'Badge Circle Colour')

    def _pick_badge_number_color(self):
        self._pick_color(self._badge_number_color, '_badge_number_btn', 'Badge Number Colour')

    # ── Keyword word colour management ────────────────────────────────────────

    def _pick_keyword_new_color(self):
        result = colorchooser.askcolor(color=self._kw_new_color, title='Word Colour')
        if result and result[1]:
            self._kw_new_color = result[1]
            self._kw_color_btn.configure(fg_color=result[1], hover_color=result[1])

    def _add_keyword_color(self):
        word = self._kw_entry.get().strip()
        if not word:
            return
        self._keyword_colors[word.lower()] = self._kw_new_color
        self._kw_entry.delete(0, 'end')
        self._refresh_keyword_list()
        self._on_style_change()
        self._on_setting_change()

    def _remove_keyword_color(self, key):
        self._keyword_colors.pop(key, None)
        self._refresh_keyword_list()
        self._on_style_change()
        self._on_setting_change()

    def _refresh_keyword_list(self):
        for child in self._kw_list_frame.winfo_children():
            child.destroy()
        if not self._keyword_colors:
            ctk.CTkLabel(self._kw_list_frame, text='No coloured words yet.',
                         font=ctk.CTkFont(size=11), text_color='gray').grid(
                row=0, column=0, sticky='w')
            return
        for i, (word, color) in enumerate(sorted(self._keyword_colors.items())):
            row_f = ctk.CTkFrame(self._kw_list_frame, fg_color='transparent')
            row_f.grid(row=i, column=0, sticky='ew', pady=2)
            row_f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row_f, text='●', text_color=color,
                         font=ctk.CTkFont(size=16), width=16).grid(row=0, column=0, padx=(0, 6))
            ctk.CTkLabel(row_f, text=word, anchor='w').grid(row=0, column=1, sticky='w')
            ctk.CTkButton(row_f, text='×', width=24, height=24,
                          fg_color='#8b1a1a', hover_color='#6b0e0e',
                          command=lambda k=word: self._remove_keyword_color(k)).grid(
                row=0, column=2)

    def _browse_audio(self):
        p = filedialog.askopenfilename(
            filetypes=[('Audio', '*.mp3 *.wav *.m4a *.aac *.flac'), ('All', '*.*')])
        if p:
            self._audio.set(p)
            if not self._output.get():
                self._output.set(str(Path(p).with_suffix('.mp4')))

    def _browse_output(self):
        p = filedialog.asksaveasfilename(
            defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4')])
        if p:
            self._output.set(p)

    def _browse_transcript(self):
        p = filedialog.askopenfilename(
            title='Select transcript file',
            filetypes=[('Transcript', '*.json *.srt *.txt'),
                       ('JSON', '*.json'), ('SRT', '*.srt'), ('Text', '*.txt'),
                       ('All', '*.*')])
        if p:
            self._transcript_path.set(p)

    def _browse_watermark(self):
        p = filedialog.askopenfilename(
            title='Select watermark image',
            filetypes=[('Image files', '*.png *.jpg *.jpeg *.webp *.bmp'),
                       ('All files', '*.*')])
        if p:
            self._watermark_path.set(p)

    def _browse_logo(self):
        p = filedialog.askopenfilename(
            title='Select logo image',
            filetypes=[('Image files', '*.png *.jpg *.jpeg *.webp *.bmp'),
                       ('All files', '*.*')])
        if p:
            self._logo_path.set(p)

    def _cancel_render(self):
        self._cancel_event.set()
        self._status('Cancelling…')

    def _start_render(self):
        story = self._story.get('1.0', 'end').strip()
        audio = self._audio.get().strip()
        output = self._output.get().strip()
        transcript_path = self._transcript_path.get().strip()
        key = self._active_api_key()

        if not story:
            messagebox.showerror('Missing', 'Please paste your story text.')
            return
        if not audio or not Path(audio).exists():
            messagebox.showerror('Missing', 'Please select a valid audio file.')
            return
        if not output:
            messagebox.showerror('Missing', 'Please set an output file path.')
            return
        if not transcript_path and not key:
            messagebox.showerror(
                'Missing',
                'Please enter your API key for the selected provider, '
                'or import a transcript file (JSON/SRT/TXT) instead.')
            return
        if transcript_path and not Path(transcript_path).exists():
            messagebox.showerror('Missing', 'Transcript file not found.')
            return
        if not check_ffmpeg():
            messagebox.showerror('FFmpeg', 'FFmpeg is not installed or not on PATH.')
            return

        self._do_save()
        self._cancel_event.clear()
        self._btn.configure(state='disabled')
        self._cancel_btn.configure(state='normal')
        self._bar.set(0)
        self._status('Starting…')
        self._render_start = time.time()

        W, H = RATIOS.get(self._ratio.get(), (1920, 1080))
        prov = _provider_key(self._provider.get())
        dg_m = DEEPGRAM_MODELS.get(self._dg_model.get(), 'nova-3')
        group_size = GROUP_OPTIONS.get(self._group.get(), 0)
        try:
            per_page = max(1, min(20, int(self._ppage.get() or 5)))
        except ValueError:
            per_page = 5

        # Build config on the main thread; total_time is set inside the worker
        # after audio duration is known.
        cfg = self._build_render_cfg()
        fast_encode = self._fast_encode.get()
        page_transition = self._page_transition.get().lower()

        q = self._render_q

        def worker():
            try:
                ctypes.windll.kernel32.SetThreadPriority(
                    ctypes.windll.kernel32.GetCurrentThread(), 1)
            except Exception:
                pass

            try:
                q.put(('p', 0.02, 'Parsing story…'))
                items = parse_story(story, group_size)
                pages = paginate(items, per_page)

                if transcript_path:
                    q.put(('p', 0.06, 'Loading imported transcript…'))
                    words, utterances = parse_transcript_file(transcript_path)
                else:
                    q.put(('p', 0.06, f'Transcribing via {prov}…'))
                    cache = str(Path(audio).with_suffix('.timestamps.json'))
                    words, utterances = get_timestamps(
                        audio, cache, prov, key, self._lang.get(),
                        deepgram_model=dg_m, story_prompt=prompt_excerpt(story))
                words = expand_compounds(words, story)
                total_dur = get_audio_duration(audio)

                q.put(('p', 0.16, 'Matching sentences to audio…'))
                assign_timestamps(pages, words, utterances, total_dur)

                cfg.total_time = total_dur  # now we know the real duration
                build_video(
                    pages, audio, output, W, H, cfg, total_dur,
                    fast_encode=fast_encode,
                    progress_cb=lambda f, m: q.put(('p', 0.20 + f * 0.80, m)),
                    cancel_event=self._cancel_event,
                    page_transition=page_transition)

                q.put(('done', output))
            except InterruptedError:
                q.put(('cancel',))
            except Exception as exc:
                q.put(('error', str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.after(120, self._poll)

    def _poll(self):
        try:
            while True:
                msg = self._render_q.get_nowait()
                if msg[0] == 'p':
                    self._bar.set(msg[1])
                    elapsed = time.time() - getattr(self, '_render_start', time.time())
                    eta = ''
                    if msg[1] > 0.05:
                        total_est = elapsed / msg[1]
                        remaining = max(0, total_est - elapsed)
                        eta = f'  (~{int(remaining)}s left)'
                    self._status(msg[2] + eta)
                elif msg[0] == 'done':
                    self._bar.set(1.0)
                    self._status(f'Done!  Saved: {msg[1]}')
                    self._btn.configure(state='normal')
                    self._cancel_btn.configure(state='disabled')
                    if messagebox.askyesno('Complete',
                                         f'Video saved to:\n{msg[1]}\n\nOpen output folder?'):
                        os.startfile(str(Path(msg[1]).parent))
                    return
                elif msg[0] == 'cancel':
                    self._bar.set(0)
                    self._status('Render cancelled.')
                    self._btn.configure(state='normal')
                    self._cancel_btn.configure(state='disabled')
                    return
                elif msg[0] == 'error':
                    self._bar.set(0)
                    self._status(f'Error: {msg[1][:120]}')
                    self._btn.configure(state='normal')
                    self._cancel_btn.configure(state='disabled')
                    messagebox.showerror('Render failed', msg[1])
                    return
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _status(self, text):
        self._status_lbl.configure(text=text)
