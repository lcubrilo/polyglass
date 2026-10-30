"""Live captions: record what the PC is playing (WASAPI loopback), transcribe it locally with faster-whisper,
translate it and publish caption lines.

Three threads keep audio flowing: one records and cuts the stream into utterances at pauses, one transcribes
them, and the translator runs on a third, so recording never waits on the model or the network.
"""

import ctypes
import logging
import os
import queue
import site
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .paths import models_dir
from .translate import Translator, iso

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # what Whisper expects
BLOCK = SAMPLE_RATE // 10  # 100 ms per read from the sound card
CONTEXT_CAPTIONS = 8  # earlier captions sent along as translation context
MAX_BACKLOG = 2  # utterances waiting for the model; older ones are dropped to stay live
LOCK_LANGUAGE_AT = 0.5  # detection confidence after which "auto" keeps the detected language
CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")  # what ctranslate2 needs to run Whisper on the GPU

# Model sizes offered in Settings, with their download size
MODEL_SIZES = {
    "tiny": "75 MB, fastest, rough",
    "base": "145 MB",
    "small": "480 MB, good on a CPU",
    "medium": "1.5 GB, better, slow on a CPU",
    "large-v3-turbo": "1.6 GB, best, needs a GPU to keep up",
}


@dataclass
class Caption:
    id: int
    text: str
    language: str
    translation: str | None = None


class SpeechChunker:
    """Cuts a stream of mono samples into utterances: speech followed by a pause, or at most max_seconds.

    Speech is told from silence by loudness, relative to a slowly tracked noise floor, so quiet background
    music between sentences still counts as a pause.
    """

    FRAME = SAMPLE_RATE * 30 // 1000  # 30 ms

    def __init__(self, pause_seconds=0.6, max_seconds=8.0, min_speech_seconds=0.3, min_level=0.004):
        self.pause_frames = round(pause_seconds * SAMPLE_RATE / self.FRAME)
        self.max_samples = round(max_seconds * SAMPLE_RATE)
        self.min_speech_frames = round(min_speech_seconds * SAMPLE_RATE / self.FRAME)
        self.min_level = min_level
        self.noise = min_level
        self._pending = np.zeros(0, dtype=np.float32)
        self._frames: list[np.ndarray] = []
        self._speech_frames = 0
        self._silent_run = 0

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        self._pending = np.concatenate([self._pending, samples.astype(np.float32, copy=False)])
        done = []
        while len(self._pending) >= self.FRAME:
            frame, self._pending = self._pending[: self.FRAME], self._pending[self.FRAME :]
            utterance = self._frame(frame)
            if utterance is not None:
                done.append(utterance)
        return done

    def _frame(self, frame: np.ndarray) -> np.ndarray | None:
        level = float(np.sqrt(np.mean(frame**2)))
        speech = level > max(self.min_level, self.noise * 3)
        if not speech:  # the noise floor follows quiet stretches only
            self.noise = 0.95 * self.noise + 0.05 * max(level, self.min_level / 3)
        if not self._frames and not speech:
            return None
        self._frames.append(frame)
        if speech:
            self._speech_frames += 1
            self._silent_run = 0
        else:
            self._silent_run += 1
        length = len(self._frames) * self.FRAME
        if self._silent_run >= self.pause_frames or length >= self.max_samples:
            return self._cut()
        return None

    def _cut(self) -> np.ndarray | None:
        audio = np.concatenate(self._frames)
        enough = self._speech_frames >= self.min_speech_frames
        self._frames, self._speech_frames, self._silent_run = [], 0, 0
        return audio if enough else None


def _add_cuda_dll_dirs():
    """GPU support comes from the optional nvidia-cublas-cu12 / nvidia-cudnn-cu12 packages; their DLLs live in
    site-packages/nvidia/*/bin, which Windows doesn't search by itself."""
    if getattr(sys, "frozen", False):  # the installed app has no site-packages and doesn't bundle CUDA
        return
    roots = [Path(p) for p in site.getsitepackages() + [site.getusersitepackages()]]
    for root in roots:
        for bin_dir in (root / "nvidia").glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _cuda_libraries_found() -> bool:
    """Checked before choosing the GPU, so a PC with an NVIDIA card but no CUDA libraries doesn't download the
    large GPU model only to fall back to the CPU."""
    _add_cuda_dll_dirs()
    try:
        for dll in CUDA_DLLS:
            ctypes.WinDLL(dll)
    except OSError as exc:
        log.info("No GPU for speech, CUDA libraries missing: %s", exc)
        return False
    return True


def resolve_model(size: str, device: str) -> str:
    if size != "auto":
        return size
    return "large-v3-turbo" if device == "cuda" else "small"


def load_model(size: str, device_choice: str, on_status=lambda message: None):
    """Load a Whisper model on the GPU if possible, else on the CPU. Returns (model, device, size)."""
    import ctranslate2
    from faster_whisper import WhisperModel

    attempts = []
    if device_choice in ("auto", "cuda") and ctranslate2.get_cuda_device_count() > 0 and _cuda_libraries_found():
        attempts.append(("cuda", "float16"))
    if device_choice != "cuda" or not attempts:
        attempts.append(("cpu", "int8"))

    root = models_dir()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # it copies instead; harmless
    last_error = None
    for device, compute_type in attempts:
        name = resolve_model(size, device)
        if not any(root.glob(f"models--*--faster-whisper-{name}")):  # Hugging Face cache layout
            on_status(f"Downloading the {name} speech model ({MODEL_SIZES.get(name, 'once')})…")
        else:
            on_status(f"Loading the {name} speech model…")
        try:
            model = WhisperModel(name, device=device, compute_type=compute_type, download_root=str(root))
            # CUDA libraries load lazily, so only a real run proves the GPU works
            list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="en")[0])
            log.info("Speech model %s on %s (%s)", name, device, compute_type)
            return model, device, name
        except Exception as exc:
            last_error = exc
            log.warning("Speech model %s on %s unavailable: %s", name, device, exc)
    raise RuntimeError(f"Could not load the speech model: {last_error}")


def is_hallucination(segment) -> bool:
    """Whisper invents text on silence and music ("Thanks for watching"); such segments come with a high
    no-speech probability and a low confidence."""
    return segment.no_speech_prob > 0.6 and segment.avg_logprob < -0.7


def loopback_recorder():
    """A recorder for whatever the default speakers are playing."""
    import soundcard

    speaker = soundcard.default_speaker()
    microphone = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
    log.info("Listening to %s", speaker.name)
    return microphone.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK)


class Listener(threading.Thread):
    """Records system audio and publishes Caption objects: first the transcript, then again with its
    translation."""

    def __init__(
        self,
        language: str,
        target: str,
        translator: Translator,
        model_size: str,
        device: str,
        publish,
        report_error,
        report_status,
        report_stopped=lambda listener: None,
        recorder_factory=loopback_recorder,
    ):
        super().__init__(daemon=True, name="polyglass-listener")
        self.language = None if language == "auto" else language
        self.target = target
        self.translator = translator
        self.model_size = model_size
        self.device = device
        self._publish = publish
        self._report_error = report_error
        self._report_status = report_status
        self._report_stopped = report_stopped
        self._recorder_factory = recorder_factory
        self._stopping = threading.Event()
        self._recording_done = threading.Event()
        self._utterances: queue.Queue[np.ndarray] = queue.Queue()
        self._context: deque[str] = deque(maxlen=CONTEXT_CAPTIONS)
        self._translate_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="polyglass-caption-translate")
        self._next_id = 0
        self._detected_language: str | None = None
        self.model = None

    def stop(self):
        self._stopping.set()

    def run(self):
        try:
            self._run()
        finally:
            self._report_stopped(self)

    def _run(self):
        try:
            self.model, device, name = load_model(
                self.model_size, self.device, lambda text: self._report_status(text, False)
            )
        except Exception as exc:
            log.exception("Speech model failed to load")
            self._report_error(str(exc))
            return
        if self._stopping.is_set():  # switched off while the model was loading
            return
        self._report_status(f"Live captions on ({name} on {device.upper()}). Play something with speech.", True)
        transcriber = threading.Thread(target=self._transcribe_loop, daemon=True, name="polyglass-transcribe")
        transcriber.start()
        try:
            self._record_loop()
        except Exception as exc:
            log.exception("Audio capture failed")
            self._report_error(f"Can't record the PC's sound: {exc}")
        finally:
            # Switched off: drop what's pending. Recording ended by itself: finish the last captions first.
            stopped_by_user = self._stopping.is_set()
            self._recording_done.set()
            transcriber.join(5 if stopped_by_user else None)
            self._translate_pool.shutdown(wait=not stopped_by_user, cancel_futures=stopped_by_user)

    def _record_loop(self):
        chunker = SpeechChunker()
        with self._recorder_factory() as recorder:
            while not self._stopping.is_set():
                block = recorder.record(numframes=BLOCK)
                if block is None:  # a finite source (a test, a file) has run dry
                    break
                for utterance in chunker.feed(np.asarray(block, dtype=np.float32).reshape(-1)):
                    while self._utterances.qsize() >= MAX_BACKLOG:  # fell behind: drop the oldest to stay live
                        self._utterances.get_nowait()
                        log.info("Speech model is behind; skipped an utterance")
                    self._utterances.put(utterance)

    def _transcribe_loop(self):
        while not self._stopping.is_set() and not (self._recording_done.is_set() and self._utterances.empty()):
            try:
                audio = self._utterances.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._transcribe(audio)
            except Exception as exc:
                log.exception("Transcription failed")
                self._report_error(f"Transcription failed: {exc}")

    def _transcribe(self, audio: np.ndarray):
        started = time.monotonic()
        segments, info = self.model.transcribe(
            audio,
            language=self.language or self._detected_language,
            beam_size=5 if self.model.model.device == "cuda" else 1,
            condition_on_previous_text=False,
            vad_filter=True,
        )
        text = " ".join(s.text.strip() for s in segments if not is_hallucination(s)).strip()
        # Durations only: transcripts never go to the log (see docs/PRIVACY.md)
        log.info("Transcribed %.1fs of audio in %.1fs", len(audio) / SAMPLE_RATE, time.monotonic() - started)
        if not text:
            return
        if not (self.language or self._detected_language) and info.language_probability >= LOCK_LANGUAGE_AT:
            # Detecting the language costs about as much as transcribing on a CPU; a video rarely switches
            self._detected_language = info.language
            log.info("Speech language detected: %s (%.0f%%)", info.language, 100 * info.language_probability)
        caption = Caption(self._next_id, text, self.language or self._detected_language or info.language)
        self._next_id += 1
        self._publish(caption)
        if iso(caption.language) == iso(self.target):
            return
        self._translate_pool.submit(self._translate, caption)

    def _translate(self, caption: Caption):
        if self._stopping.is_set():
            return
        started = time.monotonic()
        try:
            translation = self.translator.translate([caption.text], caption.language, self.target, list(self._context))
            log.info("Translated a caption via %s in %.1fs", self.translator.name, time.monotonic() - started)
            self._context.append(caption.text)
            if translation[0].strip():
                caption.translation = translation[0]
                self._publish(caption)
        except Exception as exc:
            log.exception("Caption translation failed")
            self._report_error(f"Translation failed ({self.translator.name}): {exc}")
