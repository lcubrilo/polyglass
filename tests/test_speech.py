import threading
from types import SimpleNamespace

import numpy as np

from polyglass import speech
from polyglass.speech import SAMPLE_RATE, Listener, SpeechChunker, is_hallucination, resolve_model
from polyglass.translate import Translator


def tone(seconds, level=0.1):
    t = np.arange(round(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (level * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds, level=0.0005):
    return np.random.default_rng(1).normal(0, level, round(seconds * SAMPLE_RATE)).astype(np.float32)


def feed_in_blocks(chunker, audio, block=1600):
    out = []
    for start in range(0, len(audio), block):
        out += chunker.feed(audio[start : start + block])
    return out


def test_chunker_cuts_at_pauses():
    audio = np.concatenate([silence(1), tone(1.5), silence(1), tone(2), silence(1)])
    parts = feed_in_blocks(SpeechChunker(), audio)
    assert [round(len(p) / SAMPLE_RATE, 1) for p in parts] == [2.1, 2.6]  # speech plus the pause that ended it


def test_chunker_caps_long_speech_and_drops_clicks():
    chunker = SpeechChunker(max_seconds=4)
    parts = feed_in_blocks(chunker, np.concatenate([tone(0.1), silence(1), tone(9), silence(1)]))
    assert [round(len(p) / SAMPLE_RATE) for p in parts] == [4, 4, 2]  # the 0.1 s click is not an utterance


def test_chunker_treats_steady_background_as_silence():
    music = tone(3, level=0.01)  # quiet and constant: the noise floor rises to meet it
    speech_part = tone(1.5, level=0.2)
    parts = feed_in_blocks(SpeechChunker(), np.concatenate([music, speech_part, music]))
    assert len(parts) >= 1 and all(len(p) < 3 * SAMPLE_RATE for p in parts[1:])


def test_hallucination_filter():
    assert is_hallucination(SimpleNamespace(no_speech_prob=0.9, avg_logprob=-1.2))
    assert not is_hallucination(SimpleNamespace(no_speech_prob=0.9, avg_logprob=-0.2))
    assert not is_hallucination(SimpleNamespace(no_speech_prob=0.1, avg_logprob=-1.2))


def test_automatic_model_depends_on_device():
    assert resolve_model("auto", "cuda") == "large-v3-turbo"
    assert resolve_model("auto", "cpu") == "small"
    assert resolve_model("medium", "cpu") == "medium"


class FakeModel:
    """Stands in for faster_whisper.WhisperModel: one transcript per utterance."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.model = SimpleNamespace(device="cpu")
        self.languages_asked = []

    def transcribe(self, audio, language=None, **kwargs):
        self.languages_asked.append(language)
        segment = SimpleNamespace(text=f" {self.texts.pop(0)} ", no_speech_prob=0.01, avg_logprob=-0.2)
        return iter([segment]), SimpleNamespace(language=language or "sr", language_probability=0.9)


class FakeRecorder:
    def __init__(self, audio):
        self.audio, self.pos = audio, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def record(self, numframes):
        if self.pos >= len(self.audio):
            return None
        block = self.audio[self.pos : self.pos + numframes]
        self.pos += numframes
        return block.reshape(-1, 1)


class Upper(Translator):
    name = "upper"

    def __init__(self):
        self.calls = []

    def translate(self, texts, source, target, context):
        self.calls.append((texts, source, target, list(context)))
        return [t.upper() for t in texts]


def test_listener_publishes_transcript_then_translation(monkeypatch):
    model = FakeModel(["dobar dan", "hvala"])
    monkeypatch.setattr(speech, "load_model", lambda size, device, on_status: (model, "cpu", "small"))
    audio = np.concatenate([silence(0.5), tone(1), silence(1), tone(1), silence(1)])
    published, statuses, stopped = [], [], threading.Event()
    translator = Upper()
    listener = Listener(
        "auto",
        "en",
        translator,
        "auto",
        "auto",
        lambda c: published.append((c.id, c.text, c.translation)),
        lambda e: published.append(("error", e)),
        lambda text, fade: statuses.append(text),
        lambda _listener: stopped.set(),
        recorder_factory=lambda: FakeRecorder(audio),
    )
    listener.start()
    assert stopped.wait(10)
    listener._translate_pool.shutdown(wait=True)

    assert (0, "dobar dan", None) in published and (0, "dobar dan", "DOBAR DAN") in published
    assert (1, "hvala", "HVALA") in published
    assert translator.calls[0][1:3] == ("sr", "en")  # detected language is the translation source
    assert translator.calls[1][3] == ["dobar dan"]  # earlier captions go along as context
    assert model.languages_asked == [None, "sr"]  # detected once, then reused
    assert statuses and statuses[-1].startswith("Live captions on")


def test_listener_skips_translation_when_already_in_target_language(monkeypatch):
    monkeypatch.setattr(speech, "load_model", lambda size, device, on_status: (FakeModel(["hello"]), "cpu", "small"))
    translator, done = Upper(), threading.Event()
    listener = Listener(
        "sr",
        "sr",
        translator,
        "auto",
        "auto",
        lambda c: None,
        lambda e: None,
        lambda text, fade: None,
        lambda _listener: done.set(),
        recorder_factory=lambda: FakeRecorder(np.concatenate([tone(1), silence(1)])),
    )
    listener.start()
    assert done.wait(10)
    assert translator.calls == []


def test_listener_reports_a_model_that_fails_to_load(monkeypatch):
    def broken(size, device, on_status):
        raise RuntimeError("no model")

    monkeypatch.setattr(speech, "load_model", broken)
    errors, done = [], threading.Event()
    listener = Listener(
        "auto",
        "en",
        Upper(),
        "auto",
        "auto",
        lambda c: None,
        errors.append,
        lambda text, fade: None,
        lambda _listener: done.set(),
        recorder_factory=lambda: FakeRecorder(np.zeros(0, np.float32)),
    )
    listener.start()
    assert done.wait(5) and errors == ["no model"]
