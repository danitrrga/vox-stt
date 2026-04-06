"""Vox STT Server configuration."""
import os
import json
from pathlib import Path

APP_DATA = Path(os.environ.get("APPDATA", "")) / "vox"
CONFIG_FILE = APP_DATA / "config.json"

DEFAULTS = {
    "whisper_model": "base",
    "quantization": "int8",
    "ollama_enabled": True,
    "ollama_model": "llama3.2:3b",
    "ollama_url": "http://localhost:11434",
    "auto_language": True,
    "stt_server_port": 9876,
    "sample_rate": 16000,
    "silence_threshold": 0.01,
    "silence_duration": 3.0,
}


def load_config() -> dict:
    config = DEFAULTS.copy()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config.update(json.load(f))
    return config


def save_config(config: dict):
    APP_DATA.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
