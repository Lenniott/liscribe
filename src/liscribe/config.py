"""Load, save, and validate the JSON config at ~/.config/liscribe/config.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "liscribe"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, dict[str, Any]] = {
    "save_folder": {
        "value": "~/transcripts",
        "description": "Default folder to save recordings and transcripts. Override with -f flag.",
    },
    "default_mic": {
        "value": None,
        "description": "Default input device name or index. null = system default. Override with --mic flag.",
    },
    "whisper_model": {
        "value": "base",
        "description": "Whisper model size: tiny, base, small, medium, large.",
    },
    "auto_clipboard": {
        "value": True,
        "description": "Automatically copy transcript to clipboard after transcription.",
    },
    "sample_rate": {
        "value": 16000,
        "description": "Audio sample rate in Hz. 16000 is optimal for whisper.",
    },
    "channels": {
        "value": 1,
        "description": "Number of audio channels. 1 = mono (recommended for transcription).",
    },
    "speaker_device": {
        "value": "Multi-Output Device",
        "description": "Name of the multi-output device that includes BlackHole, used when -s flag is set.",
    },
    "blackhole_device": {
        "value": "BlackHole 2ch",
        "description": "Name of the BlackHole virtual audio device for speaker capture.",
    },
}


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Return a flat dict of {key: value} from the config file, merged with defaults."""
    values: dict[str, Any] = {k: v["value"] for k, v in DEFAULTS.items()}

    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key, entry in raw.items():
                if key.startswith("_"):
                    continue
                if isinstance(entry, dict) and "value" in entry:
                    values[key] = entry["value"]
                else:
                    values[key] = entry
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read config at %s: %s", CONFIG_PATH, exc)

    return values


def save_config(values: dict[str, Any]) -> None:
    """Write current values back to the config file, preserving descriptions."""
    _ensure_dir()
    data: dict[str, Any] = {
        "_description": "Liscribe configuration. Edit values below; descriptions are for reference."
    }
    for key, meta in DEFAULTS.items():
        data[key] = {
            "value": values.get(key, meta["value"]),
            "description": meta["description"],
        }
    CONFIG_PATH.write_text(
        json.dumps(data, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Config saved to %s", CONFIG_PATH)


def get(key: str) -> Any:
    """Convenience: load config and return one value."""
    return load_config()[key]


def init_config_if_missing() -> bool:
    """Create default config file if it doesn't exist. Return True if created."""
    if CONFIG_PATH.exists():
        return False
    defaults = {k: v["value"] for k, v in DEFAULTS.items()}
    save_config(defaults)
    return True
