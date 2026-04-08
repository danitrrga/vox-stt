"""Whisper transcription wrapper for Vox."""
import logging
import os
import threading
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger("vox.transcriber")

_model: WhisperModel | None = None
_model_name: str = ""
_model_lock = threading.RLock()


def is_model_cached(model_size: str) -> bool:
    """Check if a model is already downloaded."""
    return get_cached_models_batch().get(model_size, False)


def get_cached_models_batch(models: list[str] | None = None) -> dict[str, bool]:
    """Check which models are cached with a single directory listing."""
    if models is None:
        models = ["tiny", "base", "small", "medium", "large-v3-turbo"]
    cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    if not os.path.isdir(cache):
        return {m: False for m in models}
    dirs = os.listdir(cache)
    result = {}
    for m in models:
        result[m] = any(
            d.startswith("models--") and m in d and "whisper" in d.lower()
            for d in dirs
        )
    return result


def load_model(model_size: str = "small", compute_type: str = "int8"):
    """Load the faster-whisper model. Only loads cached models (won't download)."""
    global _model, _model_name
    with _model_lock:
        if _model and _model_name == model_size:
            return
        if not is_model_cached(model_size):
            raise RuntimeError(f"Model {model_size} not cached. Download it first.")
        logger.info(f"Loading whisper model: {model_size} ({compute_type})...")
        _model = WhisperModel(model_size, device="cpu", compute_type=compute_type, cpu_threads=os.cpu_count() or 8)
        _model_name = model_size
        logger.info("Model loaded.")


def transcribe(audio: np.ndarray, language: str | None = None, hotwords: str | None = None) -> dict:
    """Transcribe audio numpy array to text.

    Args:
        language: ISO-639-1 code to force (e.g. "en", "es"), or None for auto-detect.

    Returns dict with keys: text, language, segments.
    """
    with _model_lock:
        if _model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        model = _model

    use_vad = len(audio) > 80000  # skip VAD for <5s audio (saves 50-200ms)
    segments, info = model.transcribe(
        audio,
        beam_size=1,
        language=language,
        vad_filter=use_vad,
        hotwords=hotwords,
        condition_on_previous_text=False,
    )

    full_text = [seg.text.strip() for seg in segments]

    return {
        "text": " ".join(full_text),
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
    }


def is_loaded() -> bool:
    return _model is not None


def model_info() -> dict:
    return {
        "loaded": is_loaded(),
        "model": _model_name if _model else None,
    }


# ── Model download with progress ──

_download_state = {
    "downloading": False, "progress": 0.0, "model": "",
    "error": None, "done": False,
    "downloaded_bytes": 0, "total_bytes": 0,
}
_download_lock = threading.Lock()


def get_download_state() -> dict:
    with _download_lock:
        return dict(_download_state)


def download_model_async(model_size: str, compute_type: str = "int8"):
    """Download and load a model in a background thread with progress tracking."""

    def _run():
        global _model, _model_name
        with _download_lock:
            _download_state.update(
                downloading=True, progress=0.0, model=model_size,
                error=None, done=False, downloaded_bytes=0, total_bytes=0,
            )
        try:
            import huggingface_hub
            repo_id = f"Systran/faster-whisper-{model_size}"

            # Check if already cached
            try:
                huggingface_hub.snapshot_download(repo_id, local_files_only=True)
                _download_state.update(progress=1.0)
                logger.info(f"Model {model_size} already cached.")
            except Exception:
                # Not cached — download files individually with progress
                logger.info(f"Downloading model {model_size}...")
                api = huggingface_hub.HfApi()
                model_files = api.model_info(repo_id).siblings
                files_with_size = [(f.rfilename, f.size or 0) for f in model_files]
                total_size = sum(s for _, s in files_with_size)
                _download_state["total_bytes"] = total_size
                downloaded = 0

                for filename, file_size in files_with_size:
                    huggingface_hub.hf_hub_download(
                        repo_id, filename=filename,
                    )
                    downloaded += file_size
                    _download_state["downloaded_bytes"] = downloaded
                    _download_state["progress"] = downloaded / total_size if total_size else 1.0

                logger.info(f"Model {model_size} downloaded.")

            # Load the model (thread-safe swap)
            logger.info(f"Loading model {model_size}...")
            new_model = WhisperModel(model_size, device="cpu", compute_type=compute_type, cpu_threads=os.cpu_count() or 8)
            with _model_lock:
                _model = new_model
                _model_name = model_size
            with _download_lock:
                _download_state.update(downloading=False, progress=1.0, done=True)
            logger.info(f"Model {model_size} loaded successfully.")
        except Exception as e:
            logger.error(f"Model download failed: {e}")
            with _download_lock:
                _download_state.update(downloading=False, error=str(e), done=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
