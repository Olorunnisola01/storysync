"""Video building with parallel frame rendering."""

import multiprocessing
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from storysync.ffmpeg_paths import ffmpeg_path, no_window_kwargs
from storysync.matching import build_timeline
from storysync.render.config import RenderConfig
from storysync.render.fonts import load_fonts
from storysync.render.frames import render_frame
from storysync.render.layout import LayoutCache, reflow_pages


def check_ffmpeg():
    try:
        r = subprocess.run([ffmpeg_path(), '-version'], capture_output=True,
                           timeout=10, **no_window_kwargs())
        return r.returncode == 0
    except Exception:
        return False


# ── Page-transition frame generator ──────────────────────────────────────────

_TRANS_N = 15          # frames per transition  (0.5 s at 30 fps)
_TRANS_DUR = 1.0 / 30  # seconds per transition frame


def _make_transition_frames(img_a, img_b, transition, W, H):
    """Return a list of _TRANS_N PIL images blending img_a → img_b."""
    frames = []
    for i in range(_TRANS_N):
        t = i / (_TRANS_N - 1)
        if transition == 'fade':
            f = Image.blend(img_a.convert('RGBA'), img_b.convert('RGBA'), t).convert('RGB')
        elif transition == 'sweep':
            f = img_a.copy()
            sw = int(W * t)
            if sw > 0:
                f.paste(img_b.crop((0, 0, sw, H)), (0, 0))
        elif transition == 'flip':
            if t < 0.5:
                scale = max(0.001, 1.0 - t * 2.0)
                w = max(1, int(W * scale))
                half = img_a.resize((w, H), Image.LANCZOS)
                f = Image.new('RGB', (W, H), '#111111')
                f.paste(half, ((W - w) // 2, 0))
            else:
                scale = (t - 0.5) * 2.0
                w = max(1, int(W * scale))
                half = img_b.resize((w, H), Image.LANCZOS)
                f = Image.new('RGB', (W, H), '#111111')
                f.paste(half, ((W - w) // 2, 0))
        else:
            f = img_b.copy()
        frames.append(f)
    return frames


# ── Per-process state (initialised once per worker, reused across tasks) ─────

_worker_layout_cache: LayoutCache | None = None


def _init_worker(cfg: RenderConfig):
    """Called once in each worker process before any tasks run."""
    global _worker_layout_cache
    _worker_layout_cache = LayoutCache()
    # Pre-warm the font cache so the first frame in this process is fast.
    load_fonts(cfg.font_family, cfg.body_size, cfg.heading_size, cfg.use_bold)


# ── Per-frame render worker (runs in a worker process) ────────────────────────

def _render_one(args):
    """Render one frame and save it to a PNG file.

    Returns (idx, png_path_str, duration_seconds).  Returning a path string
    instead of a PIL Image avoids pickling megabytes of pixel data across
    the process boundary.
    """
    idx, state, pages, W, H, cfg, total_duration, tmp_dir_str = args
    page_data = pages[state['page_idx']]
    img = render_frame(
        W, H, page_data['items'], cfg,
        active_text=state['active'],
        active_sentence_id=state.get('active_id'),
        page_chapter=state.get('chapter'),
        page_num=state['page_idx'] + 1,
        current_time=state['t_start'],
        highlight_heading=state.get('highlight_heading', False),
        layout_cache=_worker_layout_cache,
    )
    png_path = Path(tmp_dir_str) / f'frame_{idx:05d}.png'
    img.save(str(png_path))
    return idx, str(png_path), state['duration']


# ── Main video builder ────────────────────────────────────────────────────────

def build_video(pages, audio_path, output_path, W, H, cfg: RenderConfig,
                total_duration, fast_encode=False, progress_cb=None,
                cancel_event=None, page_transition='none'):
    """Render all frames in parallel then encode with FFmpeg.

    All visual/style parameters come from *cfg*; only pipeline-level
    settings (encode speed, progress, cancellation, transitions) are
    passed as keyword arguments.
    """

    font_body, font_heading = load_fonts(
        cfg.font_family, cfg.body_size, cfg.heading_size, cfg.use_bold)

    pages = reflow_pages(pages, font_body, font_heading, W, H, cfg.line_spacing,
                         para_spacing=cfg.para_spacing,
                         para_empty_row=cfg.para_empty_row,
                         show_player=cfg.show_player,
                         player_height=cfg.player_height,
                         title_body_gap=cfg.title_body_gap,
                         card_margin=cfg.card_margin,
                         text_padding=cfg.text_padding)

    states = build_timeline(pages, total_duration)

    tmp = Path(tempfile.mkdtemp(prefix='storysync_'))
    png_files = [None] * len(states)
    total = len(states)

    import os as _os
    workers = min(max(_os.cpu_count() or 4, 4), max(2, (total // 4) + 1))

    tasks = [
        (idx, state, pages, W, H, cfg, total_duration, str(tmp))
        for idx, state in enumerate(states)
    ]

    ctx = multiprocessing.get_context('spawn')
    done_count = 0
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                             initializer=_init_worker, initargs=(cfg,)) as pool:
        futures = {pool.submit(_render_one, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                pool.shutdown(wait=False, cancel_futures=True)
                break
            idx, png_path_str, duration = fut.result()
            png_files[idx] = (Path(png_path_str), duration)
            done_count += 1
            if progress_cb:
                progress_cb(done_count / total * 0.65,
                            f'Rendering frame {done_count} / {total}…')

    if cancel_event and cancel_event.is_set():
        _cleanup(tmp, png_files)
        raise InterruptedError('Render cancelled')

    _FPS = 30.0
    _total_frames = max(1, round(total_duration * _FPS))

    valid_pairs = [(i, states[i]) for i, p in enumerate(png_files) if p is not None]

    # ── Build concat list, optionally inserting transition frames ─────────
    norm_trans = (page_transition or 'none').lower().strip()
    use_trans  = norm_trans not in ('none', '')

    concat_lines = []
    trans_png_paths = []  # track for cleanup

    for k, (idx, state) in enumerate(valid_pairs):
        png_path = png_files[idx][0]
        t_start  = state['t_start']

        if use_trans and k > 0:
            prev_idx, prev_state = valid_pairs[k - 1]
            if prev_state['page_idx'] != state['page_idx']:
                # Re-read PNGs for transition (workers already saved them)
                try:
                    img_a = Image.open(str(png_files[prev_idx][0]))
                    img_b = Image.open(str(png_files[idx][0]))
                    if progress_cb:
                        progress_cb(0.65 + 0.05 * k / len(valid_pairs),
                                    f'Generating transition {prev_state["page_idx"]+1}→{state["page_idx"]+1}…')
                    t_frames = _make_transition_frames(img_a, img_b, norm_trans, W, H)
                    for ti, tf in enumerate(t_frames):
                        tp = tmp / f'trans_{idx:05d}_{ti:03d}.png'
                        tf.save(str(tp))
                        trans_png_paths.append(tp)
                        concat_lines.append(f"file '{tp.as_posix()}'")
                        concat_lines.append(f'duration {_TRANS_DUR:.10f}')
                except Exception:
                    pass

        if k < len(valid_pairs) - 1:
            t_next = valid_pairs[k + 1][1]['t_start']
            frames = max(1, round(t_next * _FPS) - round(t_start * _FPS))
        else:
            frames = max(1, _total_frames - round(t_start * _FPS))
        concat_lines.append(f"file '{png_path.as_posix()}'")
        concat_lines.append(f'duration {frames / _FPS:.10f}')

    if valid_pairs:
        concat_lines.append(f"file '{png_files[valid_pairs[-1][0]][0].as_posix()}'")

    concat_file = tmp / 'concat.txt'
    concat_file.write_text('\n'.join(concat_lines), encoding='utf-8')

    if progress_cb:
        progress_cb(0.78, 'Encoding with FFmpeg…')

    preset_name = 'ultrafast' if fast_encode else 'fast'
    cmd = [
        ffmpeg_path(), '-y',
        '-f', 'concat', '-safe', '0', '-i', str(concat_file),
        '-i', str(audio_path),
        '-vf', f'fps=30,scale={W}:{H}:flags=lanczos',
        '-c:v', 'libx264', '-preset', preset_name, '-crf', '18',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-map', '0:v:0', '-map', '1:a:0', '-shortest',
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, **no_window_kwargs())
    _cleanup(tmp, png_files, extra_paths=trans_png_paths)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
    if progress_cb:
        progress_cb(1.0, 'Done!')


def _cleanup(tmp, png_files, extra_paths=None):
    for entry in (png_files or []):
        if not entry:
            continue
        try:
            entry[0].unlink()
        except Exception:
            pass
    for p in (extra_paths or []):
        try:
            p.unlink()
        except Exception:
            pass
    try:
        (tmp / 'concat.txt').unlink()
    except Exception:
        pass
    try:
        tmp.rmdir()
    except Exception:
        pass
