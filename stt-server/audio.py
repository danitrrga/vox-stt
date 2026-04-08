"""Audio capture for Vox using sounddevice."""
import logging
import threading
import numpy as np
import sounddevice as sd

logger = logging.getLogger("vox.audio")


class AudioRecorder:
    """Records audio from the default microphone.

    The audio stream is kept always-running for instant recording start.
    start()/stop() just toggle a flag — no driver init on each press.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._buffer: list[np.ndarray] = []
        self._recording = False
        self._lock = threading.Lock()
        self._rms: float = 0.0
        self._peak_rms: float = 0.0
        # Pre-initialize stream — always running, near-zero idle CPU
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=512,
        )
        self._stream.start()
        logger.info("Audio stream initialized (persistent).")

    def start(self):
        """Enable recording — instant, no driver init."""
        with self._lock:
            if self._recording:
                return
            self._buffer = []
            self._peak_rms = 0.0
            self._recording = True

    def stop(self) -> np.ndarray:
        """Disable recording and return captured audio."""
        with self._lock:
            if not self._recording:
                return np.array([], dtype=np.float32)
            self._recording = False
            if self._buffer:
                audio = np.concatenate(self._buffer)
            else:
                audio = np.array([], dtype=np.float32)
            self._buffer = []
            logger.info(f"Recording: {len(audio)} samples ({len(audio)/self.sample_rate:.1f}s)")
            return audio.flatten()

    def is_recording(self) -> bool:
        return self._recording

    def get_level(self) -> float:
        """Return peak RMS level since last read (0.0 to 1.0)."""
        level = self._peak_rms
        self._peak_rms = 0.0
        return min(level * 15.0, 1.0)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            logger.warning(f"Audio callback: {status}")
        # Always compute RMS — level meter works even before recording starts
        self._rms = float(np.sqrt(np.mean(indata ** 2)))
        self._peak_rms = max(self._peak_rms, self._rms)
        if self._recording:
            self._buffer.append(indata.copy())

    @staticmethod
    def list_devices() -> list[dict]:
        """List available audio input devices."""
        devices = sd.query_devices()
        inputs = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                inputs.append({
                    "id": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "sample_rate": d["default_samplerate"],
                    "is_default": i == sd.default.device[0],
                })
        return inputs
