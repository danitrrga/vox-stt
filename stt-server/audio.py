"""Audio capture for Vox using sounddevice."""
import logging
import threading
import numpy as np
import sounddevice as sd

logger = logging.getLogger("vox.audio")


class AudioRecorder:
    """Records audio from the default microphone."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.channels = 1
        self._buffer: list[np.ndarray] = []
        self._recording = False
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._rms: float = 0.0

    def start(self):
        """Start recording from the default mic."""
        with self._lock:
            if self._recording:
                logger.warning("Already recording.")
                return
            self._buffer = []
            self._recording = True
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
                blocksize=1024,
            )
            self._stream.start()
            logger.info("Recording started.")

    def stop(self) -> np.ndarray:
        """Stop recording and return audio as float32 numpy array."""
        with self._lock:
            if not self._recording:
                logger.warning("Not recording.")
                return np.array([], dtype=np.float32)
            self._recording = False
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            audio = np.concatenate(self._buffer) if self._buffer else np.array([], dtype=np.float32)
            self._buffer = []
            logger.info(f"Recording stopped. {len(audio)} samples ({len(audio)/self.sample_rate:.1f}s)")
            return audio.flatten()

    def is_recording(self) -> bool:
        return self._recording

    def get_level(self) -> float:
        """Return current audio RMS level (0.0 to 1.0)."""
        return min(self._rms * 5.0, 1.0)  # amplify for visibility

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            logger.warning(f"Audio callback status: {status}")
        if self._recording:
            self._buffer.append(indata.copy())
            self._rms = float(np.sqrt(np.mean(indata ** 2)))

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
