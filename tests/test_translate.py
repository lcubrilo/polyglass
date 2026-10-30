import json
from types import SimpleNamespace

import pytest

from polyglass import translate
from polyglass.config import Config
from polyglass.translate import (
    ClaudeTranslator,
    GoogleFreeTranslator,
    NoTranslator,
    available_translators,
    create_translator,
)


@pytest.fixture
def no_credentials(monkeypatch):
    monkeypatch.setattr(translate, "has_claude_credentials", lambda: False)
    monkeypatch.setattr(translate, "deepl_key", lambda: None)


def test_google_is_hidden_unless_explicitly_allowed(no_credentials):
    assert "google" not in available_translators(Config())
    assert isinstance(create_translator(Config()), NoTranslator)
    with pytest.raises(RuntimeError):
        create_translator(Config(translator="google"))


def test_google_is_used_when_allowed(no_credentials):
    cfg = Config(allow_unofficial_google=True)
    assert "google" in available_translators(cfg)
    assert create_translator(cfg).name == "google"


def test_no_translator_explains_itself():
    with pytest.raises(RuntimeError, match="Settings"):
        NoTranslator().translate(["x"], "fr-FR", "en", [])


def fake_claude(reply_items, stop_reason="end_turn"):
    """A ClaudeTranslator whose API client returns a canned structured-output reply."""
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        text = json.dumps({"translations": reply_items})
        return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])

    translator = ClaudeTranslator.__new__(ClaudeTranslator)
    translator._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    translator._model, translator._effort = "claude-opus-5-5", "low"
    return translator, calls


def test_claude_sends_items_with_context_and_returns_translations():
    translator, calls = fake_claude(["Account settings", "Log out"])
    result = translator.translate(["Paramètres du compte", "Se déconnecter"], "fr-FR", "en", ["Bonjour"])
    assert result == ["Account settings", "Log out"]
    payload = json.loads(calls[0]["messages"][0]["content"])
    assert payload["items"] == ["Paramètres du compte", "Se déconnecter"]
    assert payload["earlier_context"] == ["Bonjour"]
    assert payload["source_language"] == "French" and payload["target_language"] == "English"


def test_claude_item_count_mismatch_is_an_error():
    translator, _ = fake_claude(["only one"])
    with pytest.raises(RuntimeError, match="returned 1 items for 2"):
        translator.translate(["a", "b"], "fr-FR", "en", [])


def test_claude_refusal_is_an_error():
    translator, _ = fake_claude([], stop_reason="refusal")
    with pytest.raises(RuntimeError, match="declined"):
        translator.translate(["a"], "fr-FR", "en", [])


def test_google_falls_back_to_detection_when_a_language_code_returns_nothing(monkeypatch):
    calls = []

    def fake_request(self, text, sl, tl):
        calls.append(sl)
        return "" if sl == "sr" else "Today we talk about trains."

    monkeypatch.setattr(GoogleFreeTranslator, "_request", fake_request)
    assert GoogleFreeTranslator().translate(["Danas pričamo o vozovima."], "sr", "en", []) == [
        "Today we talk about trains."
    ]
    assert calls == ["sr", "auto"]
