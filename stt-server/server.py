"""Vox STT Server — FastAPI backend for speech-to-text."""
import asyncio
import logging
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from audio import AudioRecorder
from transcriber import load_model, transcribe, model_info
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
    load_model(config["whisper_model"], config["quantization"])
    asyncio.create_task(warm_up())
    yield
    logger.info("Shutting down Vox STT server.")


app = FastAPI(title="Vox STT Server", version="0.1.0", lifespan=lifespan)


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

    result = transcribe(audio)
    raw_text = result["text"]

    formatted_result = {"formatted": raw_text, "used_ollama": False}
    if format and raw_text:
        formatted_result = await format_text(raw_text)

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


@app.websocket("/ws/stream")
async def stream_transcription(ws: WebSocket):
    """WebSocket endpoint for streaming transcription (toggle mode)."""
    await ws.accept()
    config = load_config()
    sample_rate = config["sample_rate"]
    chunk_duration = 5  # seconds per chunk

    try:
        recorder.start()
        await ws.send_json({"type": "started"})

        while True:
            msg = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
            if msg == "stop":
                break
    except (asyncio.TimeoutError, WebSocketDisconnect):
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if recorder.is_recording():
            audio = recorder.stop()
            if len(audio) > 0:
                result = transcribe(audio)
                formatted = await format_text(result["text"])
                await ws.send_json({
                    "type": "final",
                    "raw": result["text"],
                    "formatted": formatted["formatted"],
                    "language": result["language"],
                })
        await ws.close()


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=config["stt_server_port"],
        log_level="info",
    )
