"""Configuration persistence."""

import json
from pathlib import Path

CONFIG_PATH        = Path.home() / ".storysync_config.json"
CUSTOM_PRESETS_PATH = Path.home() / ".storysync_presets.json"


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(data):
    try:
        CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_custom_presets() -> dict:
    """Return {name: settings_dict} for all user-saved presets."""
    if CUSTOM_PRESETS_PATH.exists():
        try:
            return json.loads(CUSTOM_PRESETS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_custom_presets(presets: dict):
    """Persist custom presets to disk."""
    try:
        CUSTOM_PRESETS_PATH.write_text(
            json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
