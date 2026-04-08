"""Ollama-based smart text formatting for Vox."""
import logging
import httpx
from config import load_config

logger = logging.getLogger("vox.formatter")

FORMATTING_PROMPT = """You are a text formatter. Fix punctuation, capitalization, and add paragraph breaks where appropriate. The text may be in English or Spanish — preserve the original language. Do not change the meaning or add words. Return ONLY the formatted text, nothing else.

Raw: {text}"""

MIN_WORDS_FOR_FORMATTING = 30

# Persistent HTTP client — avoids TCP connection overhead per call
_ollama_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _ollama_client
    if _ollama_client is None or _ollama_client.is_closed:
        _ollama_client = httpx.AsyncClient(timeout=5.0)
    return _ollama_client


async def format_text(raw_text: str) -> dict:
    config = load_config()

    if not config.get("ollama_enabled", True):
        return {"formatted": _basic_format(raw_text), "used_ollama": False}

    word_count = len(raw_text.split())
    if word_count < MIN_WORDS_FOR_FORMATTING:
        return {"formatted": _basic_format(raw_text), "used_ollama": False}

    try:
        result = await _call_ollama(raw_text, config)
        return {"formatted": result, "used_ollama": True}
    except Exception as e:
        logger.error(f"Ollama formatting failed: {e}")
        return {"formatted": _basic_format(raw_text), "used_ollama": False}


async def _call_ollama(text: str, config: dict) -> str:
    url = f"{config['ollama_url']}/api/generate"
    payload = {
        "model": config.get("ollama_model", "llama3.2:3b"),
        "prompt": FORMATTING_PROMPT.format(text=text),
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": len(text) * 2,
        },
    }

    client = _get_client()
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", text).strip()


def _basic_format(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


async def warm_up():
    config = load_config()
    if not config.get("ollama_enabled", True):
        return
    try:
        logger.info("Warming up Ollama model...")
        await _call_ollama("hello world this is a test of the formatting system", config)
        logger.info("Ollama warm-up complete.")
    except Exception as e:
        logger.warning(f"Ollama warm-up failed (will retry on first use): {e}")
