"""Shared constants for StorySync."""

PRESETS = {
    "Brown Paper":    {"bg": "#c8a47a", "card": "#fdf6e3", "highlight": "#fff176",
                       "text": "#1a1a1a", "heading": "#8b4513"},
    "Aged Parchment": {"bg": "#b8975a", "card": "#f5e6c8", "highlight": "#ffe082",
                       "text": "#2a1a0a", "heading": "#6b3410"},
    "Dark Forest":    {"bg": "#2d4a3e", "card": "#f0ede0", "highlight": "#fff176",
                       "text": "#1a1a1a", "heading": "#5a3010"},
    "Midnight Blue":  {"bg": "#1a2744", "card": "#f0ede0", "highlight": "#fff176",
                       "text": "#1a1a1a", "heading": "#5a3010"},
    "Charcoal":       {"bg": "#2a2a2a", "card": "#f5f5f0", "highlight": "#fff176",
                       "text": "#1a1a1a", "heading": "#8b4513"},
    "Cream White":    {"bg": "#f0ece0", "card": "#ffffff", "highlight": "#ffe082",
                       "text": "#1a1a1a", "heading": "#6b3410"},
    "Slate Blue":     {"bg": "#3d5a80", "card": "#f8f4ee", "highlight": "#fff176",
                       "text": "#1a1a1a", "heading": "#5a3010"},
    "Olive Green":    {"bg": "#4a5240", "card": "#f5f0e8", "highlight": "#fff176",
                       "text": "#1a1a1a", "heading": "#5a3010"},
}

RATIOS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}

LANGUAGES = [
    "de", "en", "fr", "es", "it", "pt", "nl", "pl",
    "ru", "tr", "ja", "zh", "ar", "ko", "hi", "uk", "sv", "da", "no", "fi",
]

FONT_FILES = {
    # ── Classic / Serif ───────────────────────────────────────────────────────
    "Georgia":            {"bold": "georgiab.ttf",             "regular": "georgia.ttf"},
    "Times New Roman":    {"bold": "timesbd.ttf",              "regular": "times.ttf"},
    "Cambria":            {"bold": "cambriab.ttf",             "regular": "cambriab.ttf"},
    "Book Antiqua":       {"bold": "BKANT.TTF",                "regular": "BKANT.TTF"},
    "Garamond":           {"bold": "GARABD.TTF",               "regular": "GARA.TTF"},
    "Palatino Linotype":  {"bold": "palab.ttf",                "regular": "pala.ttf"},
    "Constantia":         {"bold": "constanb.ttf",             "regular": "constan.ttf"},
    "Bookman Old Style":  {"bold": "BOOKOSB.TTF",              "regular": "BOOKOS.TTF"},
    "Noto Serif":         {"bold": "NotoSerif-Bold.ttf",       "regular": "NotoSerif-Regular.ttf"},
    "Cormorant Infant":   {"bold": "CormorantInfant-Bold.ttf", "regular": "CormorantInfant-Regular.ttf"},
    # ── Modern Sans-Serif ─────────────────────────────────────────────────────
    "Arial":              {"bold": "arialbd.ttf",              "regular": "arial.ttf"},
    "Calibri":            {"bold": "calibrib.ttf",             "regular": "calibri.ttf"},
    "Verdana":            {"bold": "verdanab.ttf",             "regular": "verdana.ttf"},
    "Trebuchet MS":       {"bold": "trebucbd.ttf",             "regular": "trebuc.ttf"},
    "Tahoma":             {"bold": "tahomabd.ttf",             "regular": "tahoma.ttf"},
    "Segoe UI":           {"bold": "segoeuib.ttf",             "regular": "segoeui.ttf"},
    "Candara":            {"bold": "Candarab.ttf",             "regular": "Candara.ttf"},
    "Corbel":             {"bold": "corbelb.ttf",              "regular": "corbel.ttf"},
    "Noto Sans":          {"bold": "NotoSans-Bold.ttf",        "regular": "NotoSans-Regular.ttf"},
    # ── Web / Google ──────────────────────────────────────────────────────────
    "Roboto":             {"bold": "Roboto-Bold.ttf",          "regular": "Roboto-Regular.ttf"},
    "Lato":               {"bold": "Lato-Bold.ttf",            "regular": "Lato-Regular.ttf"},
    "Montserrat":         {"bold": "Montserrat-Bold.ttf",      "regular": "Montserrat-Regular.ttf"},
    "Open Sans":          {"bold": "OpenSans-Bold.ttf",        "regular": "OpenSans-Regular.ttf"},
    "Raleway":            {"bold": "Raleway-Bold.ttf",         "regular": "Raleway-Regular.ttf"},
    "Source Sans Pro":    {"bold": "SourceSansPro-Bold.ttf",   "regular": "SourceSansPro-Regular.ttf"},
    # ── Mono / Novelty ────────────────────────────────────────────────────────
    "Courier New":        {"bold": "courbd.ttf",               "regular": "cour.ttf"},
    "Comic Sans MS":      {"bold": "comicbd.ttf",              "regular": "comic.ttf"},
}

GROUP_OPTIONS = {
    "Auto  (blank lines in text)": 0,
    "1 sentence per paragraph":    1,
    "2 sentences per paragraph":   2,
    "3 sentences per paragraph":   3,
    "4 sentences per paragraph":   4,
    "5 sentences per paragraph":   5,
}
GROUP_KEYS = list(GROUP_OPTIONS.keys())

PROVIDERS = {
    "OpenAI Whisper (whisper-1)": "openai",
    "Deepgram": "deepgram",
}

DEEPGRAM_MODELS = {
    "nova-3 (recommended)": "nova-3",
    "nova-2": "nova-2",
}

HIGHLIGHT_STYLES = ["Background bar", "Soft glow", "Underline"]

TEXT_ALIGNMENTS = ["Left", "Center", "Right", "Justify"]
BADGE_POSITIONS  = ["Top-Right Corner", "Top-Left Corner",
                    "Bottom-Right Corner", "Bottom-Left Corner", "Right Edge"]
PAGE_TRANSITIONS = ["None", "Fade", "Sweep", "Flip"]
LOGO_POSITIONS   = ["Top-Right", "Top-Left", "Bottom-Right", "Bottom-Left"]

TEXTURES = [
    "Blank", "Lines", "College Ruled", "Graph Paper", "Dot Grid",
    "Yellow Ruled", "Sandpaper", "Aged Paper", "Linen", "Grid",
]

MIN_SENTENCE_GAP = 0.08
MIN_STATE_DURATION = 0.12
MAX_STATE_DURATION = 45.0