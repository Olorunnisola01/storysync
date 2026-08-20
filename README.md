# StorySync

A Windows desktop app that turns a story audio file and its text into a
karaoke-style video with the spoken words highlighted in sync — built for
learning German by reading along with audio.

Transcribes the audio, aligns it against your own text, renders highlighted
frames with Pillow, and builds the final video with FFmpeg. Written in Python
with a customtkinter GUI.

## Download

A prebuilt single-file exe is on the [Releases page](../../releases/latest).
Download it, double-click, and it runs — no Python, and no FFmpeg install:
ffmpeg and ffprobe are bundled inside the exe.

## How it works

1. **Transcribe** — send the audio to Deepgram, Groq, or OpenAI Whisper, or
   import an existing transcript instead of transcribing again.
2. **Match** — align the transcript's word timings against your reference text,
   so the on-screen words come from your script rather than from whatever the
   recogniser heard.
3. **Render** — draw each frame with Pillow, highlighting the current word.
4. **Build** — encode the frames and audio into a video with FFmpeg.

## Running from source

```bash
pip install -r requirements.txt
python storysync.py
```

Running from source needs FFmpeg on your `PATH`. The packaged exe does not —
it carries its own copy. `storysync/ffmpeg_paths.py` picks the bundled binary
when frozen and falls back to `PATH` otherwise.

Transcription API keys are entered in the app and stored in
`%USERPROFILE%\.storysync_config.json`, alongside your saved presets in
`.storysync_presets.json`. Neither file is part of this repository.

## Building the exe

```bash
build_storysync.bat
```

Runs PyInstaller against `StorySync.spec` and writes `dist\StorySync.exe`.
`multiprocessing.freeze_support()` in `storysync.py` is what stops the
one-file build's worker processes from re-launching the GUI on spawn — don't
remove it.

## Notes

- Windows only.
- The released exe is unsigned, so SmartScreen warns on first run.
- ffmpeg and ffprobe are redistributed inside the released exe under their own
  licences.
- Transcription requires an internet connection and an API key for whichever
  provider you choose.
