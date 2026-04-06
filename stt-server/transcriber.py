"""Whisper transcription wrapper for Vox."""
import logging
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger("vox.transcriber")

_model: WhisperModel | None = None
_model_name: str = ""


def load_model(model_size: str = "small", compute_type: str = "int8"):
    """Load the faster-whisper model. Call once on startup."""
    global _model, _model_name
    if _model and _model_name == model_size:
        return
    logger.info(f"Loading whisper model: {model_size} ({compute_type})...")
    _model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    _model_name = model_size
    logger.info("Model loaded.")


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> dict:
    """Transcribe audio numpy array to text.

    Returns dict with keys: text, language, segments.
    """
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")

    segments, info = _model.transcribe(
        audio,
        beam_size=5,
        language=None,  # auto-detect
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=200,
        ),
    )

    segment_list = []
    full_text = []
    for seg in segments:
        segment_list.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        full_text.append(seg.text.strip())

    return {
        "text": " ".join(full_text),
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "segments": segment_list,
    }


def is_loaded() -> bool:
    return _model is not None


def model_info() -> dict:
    return {
        "loaded": is_loaded(),
        "model": _model_name if _model else None,
    }
