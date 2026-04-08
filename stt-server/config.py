"""Vox STT Server configuration."""
import os
import json
from pathlib import Path

APP_DATA = Path(os.environ.get("APPDATA", "")) / "vox"
CONFIG_FILE = APP_DATA / "config.json"

DEFAULTS = {
    "whisper_model": "large-v3-turbo",
    "quantization": "int8",
    "ollama_enabled": False,
    "ollama_model": "llama3.2:3b",
    "ollama_url": "http://localhost:11434",
    "language_mode": "auto",
    "selected_languages": ["en", "es"],
    "stt_server_port": 9876,
    "sample_rate": 16000,
    "silence_threshold": 0.01,
    "silence_duration": 3.0,
    "close_to_tray": True,
    "hotkey": "Ctrl+Shift+Space",
    "pill_position": "bottom-center",
    "hotwords": "",
}

_cached_config: dict | None = None


def load_config() -> dict:
    global _cached_config
    if _cached_config is not None:
        return _cached_config.copy()
    config = DEFAULTS.copy()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config.update(json.load(f))
    _cached_config = config
    return config.copy()


def save_config(config: dict):
    global _cached_config
    APP_DATA.mkdir(parents=True, exist_ok=True)
    merged = DEFAULTS.copy()
    merged.update(config)
    with open(CONFIG_FILE, "w") as f:
        json.dump(merged, f, indent=2)
    _cached_config = merged
