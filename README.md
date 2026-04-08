<div align="center">

```
██╗   ██╗ ██████╗ ██╗  ██╗
██║   ██║██╔═══██╗╚██╗██╔╝
██║   ██║██║   ██║ ╚███╔╝
╚██╗ ██╔╝██║   ██║ ██╔██╗
 ╚████╔╝ ╚██████╔╝██╔╝ ██╗
  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝
```

*Local speech-to-text that types for you.*

![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows&logoColor=white)
![Tauri](https://img.shields.io/badge/Tauri_2-FFC131?style=flat-square&logo=tauri&logoColor=black)
![Whisper](https://img.shields.io/badge/Whisper-74aa9c?style=flat-square&logo=openai&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=flat-square&logo=ollama&logoColor=white)
![Version](https://img.shields.io/badge/v0.1.0-6366f1?style=flat-square)
![License](https://img.shields.io/badge/MIT-22c55e?style=flat-square)

</div>

---

## What is Vox?

Hold a hotkey, speak, release — your words appear at the cursor. Vox is a lightweight desktop app that transcribes your voice and types the result directly into any application. Everything runs locally. No cloud, no API keys, no latency.

## Features

- **Hold-to-talk** — configurable global hotkey, hold to record, release to transcribe
- **Hands-free mode** — double-tap the hotkey to start continuous recording, tap again to stop
- **Local Whisper** — transcription via faster-whisper (tiny / base / small / medium / large-v3-turbo)
- **Model management** — download, switch, and delete Whisper models from the Settings UI
- **Custom vocabulary** — teach Whisper domain-specific words (course codes, project names, technical terms)
- **Smart formatting** — optional Ollama-powered punctuation and capitalization
- **98 languages** — auto-detection or manual selection
- **Floating overlay** — draggable recording pill with real-time audio visualizer and timer
- **Live partial transcription** — see words appear as you speak
- **Text injection** — transcribed text pastes directly into the active app
- **System tray** — close-to-tray, tray icon toggle, run on startup
- **ASCII art brand identity** — monospace typography, block-character V icon

## Quick Start

### Prerequisites

- **Python 3.10+** with [uv](https://docs.astral.sh/uv/)
- **Node.js 18+**
- **Rust** toolchain (via [rustup](https://rustup.rs/))
- **Ollama** (optional, for smart formatting)

### Install & Run

```bash
# Enter the project
cd vox

# Set up the Python STT server
cd stt-server
uv venv && uv pip install -e .
cd ..

# Install frontend dependencies
npm install

# Run in development mode
npm run tauri dev
```

### Build for Production

```bash
npm run tauri build
```

The installer will be in `src-tauri/target/release/bundle/`.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Shell | Tauri 2 (Rust) |
| Frontend | React 19, TypeScript |
| Styling | Tailwind CSS 4 |
| STT | faster-whisper (Python) |
| LLM | Ollama (optional) |
| Audio | sounddevice |
| Injection | enigo + arboard (Rust) |

## Architecture

```
vox/
├── src/                  # React frontend (TypeScript)
│   ├── App.tsx           # Main UI — idle, recording, hands-free, processing, result
│   ├── constants.ts      # Shared constants (server URL, fonts)
│   ├── components/
│   │   └── Settings.tsx  # Settings — language, model, vocabulary, hotkey, overlay
│   └── styles/
│       └── globals.css   # Theme variables, animations
│
├── src-tauri/            # Tauri backend (Rust)
│   ├── src/
│   │   ├── lib.rs        # App setup, tray, recording state machine, window management
│   │   ├── keyboard_hook.rs  # Low-level Windows keyboard hook for global hotkeys
│   │   ├── injector.rs   # Clipboard-based text injection
│   │   └── stt_bridge.rs # HTTP bridge to Python server (per-request timeouts)
│   └── icons/            # App icons (ASCII V rendered at 4096px, downscaled)
│
├── stt-server/           # Python STT server (FastAPI)
│   ├── server.py         # REST API endpoints + audio backup on failure
│   ├── transcriber.py    # Whisper model loading, transcription, download with progress
│   ├── audio.py          # Audio recording via sounddevice
│   ├── formatter.py      # Ollama text formatting (persistent client, fast fallback)
│   └── config.py         # Persistent config with in-memory cache
│
├── public/
│   └── overlay.html      # Floating recording pill (280x48px, draggable, timer)
│
└── scripts/
    └── gen_icon.py       # Icon generator (ASCII V at 4096px → downscale)
```

**Data flow:** Hotkey press → Audio recording → Whisper transcription → Ollama formatting (optional) → Clipboard injection → Text appears at cursor.

## Recording Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| Hold-to-talk | Hold hotkey | Records while held, transcribes on release |
| Hands-free | Double-tap hotkey | Continuous recording until next tap |

The state machine detects quick taps (<300ms) and waits 400ms for a second tap before committing to hold-to-talk mode.

## Configuration

Settings are stored at `%APPDATA%/vox/config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `whisper_model` | `large-v3-turbo` | Whisper model size |
| `ollama_enabled` | `false` | Smart text formatting via Ollama |
| `language_mode` | `auto` | Auto-detect or manual language selection |
| `hotkey` | `Ctrl+Shift+Space` | Global shortcut (configurable) |
| `hotwords` | `""` | Custom vocabulary (comma-separated) |
| `pill_position` | `bottom-center` | Default overlay position |
| `close_to_tray` | `true` | Minimize to tray on close |

## License

MIT