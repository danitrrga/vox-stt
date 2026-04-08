"""Vox STT Server — FastAPI backend for speech-to-text."""
import asyncio
import logging
import os
import numpy as np
from contextlib import asynccontextmanager

VOX_BANNER = r"""
██╗   ██╗ ██████╗ ██╗  ██╗
██║   ██║██╔═══██╗╚██╗██╔╝
██║   ██║██║   ██║ ╚███╔╝
╚██╗ ██╔╝██║   ██║ ██╔██╗
 ╚████╔╝ ╚██████╔╝██╔╝ ██╗
  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝
  stt server · v0.1.0 · port 9876
"""

import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from audio import AudioRecorder
from transcriber import load_model, transcribe, model_info, download_model_async, get_download_state, get_cached_models_batch
from formatter import format_text, warm_up
from config import load_config, save_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vox.server")

recorder = AudioRecorder()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, clean up on shutdown."""
    config = load_config()
    try:
        load_model(config["whisper_model"], config["quantization"])
    except Exception as e:
        logger.warning(f"Failed to load {config['whisper_model']}: {e}")
        # Fall back to smallest cached model
        for fallback in ["small", "base", "tiny"]:
            try:
                load_model(fallback, config["quantization"])
                logger.info(f"Loaded fallback model: {fallback}")
                break
            except Exception:
                continue
    asyncio.create_task(warm_up())
    try:
        print(VOX_BANNER)
    except UnicodeEncodeError:
        logger.info("Vox STT server started.")
    yield
    logger.info("Shutting down Vox STT server.")


app = FastAPI(title="Vox STT Server", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


WHISPER_LANGUAGES = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese",
    "az": "Azerbaijani", "ba": "Bashkir", "be": "Belarusian", "bg": "Bulgarian",
    "bn": "Bengali", "bo": "Tibetan", "br": "Breton", "bs": "Bosnian",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "et": "Estonian", "eu": "Basque", "fa": "Persian", "fi": "Finnish",
    "fo": "Faroese", "fr": "French", "gl": "Galician", "gu": "Gujarati",
    "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew", "hi": "Hindi",
    "hr": "Croatian", "ht": "Haitian Creole", "hu": "Hungarian", "hy": "Armenian",
    "id": "Indonesian", "is": "Icelandic", "it": "Italian", "ja": "Japanese",
    "jw": "Javanese", "ka": "Georgian", "kk": "Kazakh", "km": "Khmer",
    "kn": "Kannada", "ko": "Korean", "la": "Latin", "lb": "Luxembourgish",
    "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mg": "Malagasy", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam",
    "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese",
    "my": "Myanmar", "ne": "Nepali", "nl": "Dutch", "nn": "Nynorsk",
    "no": "Norwegian", "oc": "Occitan", "pa": "Punjabi", "pl": "Polish",
    "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "sn": "Shona", "so": "Somali", "sq": "Albanian",
    "sr": "Serbian", "su": "Sundanese", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai",
    "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish", "tt": "Tatar",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese",
}

PINNED_LANGUAGES = ["en", "es", "fr", "de", "pt", "it", "nl", "zh", "ja", "ko", "ru", "ar", "hi"]


def resolve_languages(config: dict) -> list[str] | None:
    """Return selected language list when in specific mode, or None for auto."""
    if config.get("language_mode") == "specific":
        langs = config.get("selected_languages", [])
        if langs:
            return langs
    return None


@app.get("/api/languages")
def get_languages():
    return {
        "languages": WHISPER_LANGUAGES,
        "pinned": PINNED_LANGUAGES,
    }


@app.get("/api/status")
def status():
    return {
        "status": "ok",
        "recording": recorder.is_recording(),
        "model": model_info(),
    }


@app.post("/api/record/start")
def record_start():
    if recorder.is_recording():
        return JSONResponse({"error": "Already recording"}, status_code=409)
    recorder.start()
    return {"status": "recording"}


@app.post("/api/record/stop")
async def record_stop(format: bool = True):
    if not recorder.is_recording():
        return JSONResponse({"error": "Not recording"}, status_code=409)

    audio = recorder.stop()
    if len(audio) == 0:
        return {"text": "", "formatted": "", "language": None}

    if len(audio) / 16000 < 0.5:
        return {"text": "", "formatted": "", "language": None, "too_short": True}

    # Save audio to temp file as backup (recovered on failure)
    import tempfile, wave, struct  # noqa: E401
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="vox_")
        os.close(tmp_fd)
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes((audio * 32767).astype(np.int16).tobytes())
    except Exception:
        tmp_path = None

    try:
        config = load_config()
        langs = resolve_languages(config)
        lang = langs[0] if (langs and len(langs) == 1) else None
        hw = config.get("hotwords", "") or None

        result = await asyncio.wait_for(
            asyncio.to_thread(transcribe, audio, language=lang, hotwords=hw),
            timeout=240.0,
        )
        raw_text = result["text"]

        formatted_result = {"formatted": raw_text, "used_ollama": False}
        if format and raw_text:
            formatted_result = await format_text(raw_text)
    except asyncio.TimeoutError:
        logger.error(f"Transcription timed out for {len(audio)/16000:.1f}s audio")
        if tmp_path:
            logger.error(f"Audio saved to: {tmp_path}")
        return JSONResponse(
            {"error": "Transcription timed out. Try a shorter recording or smaller model."},
            status_code=504,
        )
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        if tmp_path:
            logger.error(f"Audio saved to: {tmp_path}")
        return JSONResponse({"error": str(e)}, status_code=500)

    # Success — clean up temp file
    if tmp_path:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return {
        "raw": raw_text,
        "formatted": formatted_result["formatted"],
        "language": result["language"],
        "language_probability": result["language_probability"],
        "used_ollama": formatted_result["used_ollama"],
        "duration_seconds": len(audio) / 16000,
    }


@app.get("/api/level")
def audio_level():
    return {"level": recorder.get_level(), "recording": recorder.is_recording()}


@app.get("/api/devices")
def list_devices():
    return {"devices": AudioRecorder.list_devices()}


@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/config")
def update_config(updates: dict):
    config = load_config()
    config.update(updates)
    save_config(config)
    return config


@app.get("/api/models/cached")
def get_cached_models():
    return get_cached_models_batch()


@app.post("/api/model/delete")
def delete_model(body: dict):
    """Delete a cached model from disk."""
    model = body.get("model", "")
    if not model:
        return JSONResponse({"error": "No model specified"}, status_code=400)
    info = model_info()
    if info.get("model") == model:
        return JSONResponse({"error": "Cannot delete the active model"}, status_code=400)
    try:
        cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        deleted = False
        for d in os.listdir(cache):
            if d.startswith("models--") and model in d and "whisper" in d.lower():
                path = os.path.join(cache, d)
                shutil.rmtree(path, ignore_errors=True)
                logger.info(f"Deleted model {model} from {path}")
                deleted = True
        if deleted:
            return {"status": "deleted", "model": model}
        return JSONResponse({"error": f"Model {model} not found in cache"}, status_code=404)
    except Exception as e:
        logger.error(f"Failed to delete model {model}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/model/download")
def start_model_download(body: dict):
    model = body.get("model", "small")
    config = load_config()
    quantization = config.get("quantization", "int8")
    download_model_async(model, quantization)
    return {"status": "downloading", "model": model}


@app.get("/api/model/status")
def model_download_status():
    state = get_download_state()
    return state


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=config["stt_server_port"],
        log_level="info",
    )
