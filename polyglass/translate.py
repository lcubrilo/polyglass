"""Translators share one interface: translate(texts, source, target, context) -> list of translations."""

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import Config, deepl_key, has_claude_credentials

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "sr": "Serbian",
    "hr": "Croatian",
    "ru": "Russian",
    "uk": "Ukrainian",
    "pl": "Polish",
    "nl": "Dutch",
    "tr": "Turkish",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
    "el": "Greek",
}


def iso(tag: str) -> str:
    return tag.split("-")[0].lower()


class Translator:
    name = "base"

    def translate(self, texts: list[str], source: str, target: str, context: list[str]) -> list[str]:
        raise NotImplementedError


class GoogleFreeTranslator(Translator):
    """Google's keyless web endpoint. Unofficial and outside Google's terms of service, so it is opt-in
    (allow_unofficial_google) and meant for personal use only. No context awareness."""

    name = "google"
    URL = "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&ie=UTF-8&oe=UTF-8&sl={sl}&tl={tl}"

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=4)

    def _one(self, text: str, source: str, target: str) -> str:
        url = self.URL.format(sl=iso(source), tl=iso(target))
        body = urllib.parse.urlencode({"q": text}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        first = data[0]
        return first if isinstance(first, str) else first[0]

    def translate(self, texts, source, target, context):
        return list(self._pool.map(lambda t: self._one(t, source, target), texts))


class DeepLTranslator(Translator):
    name = "deepl"

    def __init__(self, key: str):
        import deepl

        self._client = deepl.Translator(key)

    @staticmethod
    def _target_code(target: str) -> str:
        code = iso(target).upper()
        return {"EN": "EN-US", "PT": "PT-PT"}.get(code, code)

    def translate(self, texts, source, target, context):
        results = self._client.translate_text(
            texts,
            source_lang=iso(source).upper(),
            target_lang=self._target_code(target),
            context="\n".join(context) or None,
        )
        return [r.text for r in results]


class ClaudeTranslator(Translator):
    name = "claude"
    SYSTEM = (
        "You translate text captured from a screen with OCR. Each item is one block of text "
        "(a paragraph, a label, a button, a menu entry) in reading order. Translate every item, "
        "keep the same number of items in the same order, and keep each translation about as long "
        "as its source so it fits the original space. Keep the line breaks inside an item: one "
        "translated line per source line. Use the surrounding items and the earlier "
        "context to pick the right meaning and keep terminology consistent. Silently fix obvious "
        "OCR errors. Leave names, numbers, code and URLs unchanged. If an item is not in the source "
        "language or is not real text, return it unchanged."
    )

    def __init__(self, model: str, effort: str):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._model = model
        self._effort = effort

    def translate(self, texts, source, target, context):
        src = LANGUAGE_NAMES.get(iso(source), source)
        tgt = LANGUAGE_NAMES.get(iso(target), target)
        payload = {"source_language": src, "target_language": tgt, "earlier_context": context, "items": texts}
        response = self._client.beta.messages.create(
            model=self._model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=self.SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            output_config={
                "effort": self._effort,
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
                        "required": ["translations"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to translate this text")
        text = next(b.text for b in response.content if b.type == "text")
        translations = json.loads(text)["translations"]
        if len(translations) != len(texts):
            raise RuntimeError(f"Claude returned {len(translations)} items for {len(texts)} blocks")
        return translations


class NoTranslator(Translator):
    """Placeholder when nothing is configured, so the app still starts and can explain what to set up."""

    name = "none"

    def translate(self, texts, source, target, context):
        raise RuntimeError("No translator is set up. Set DEEPL_API_KEY or ANTHROPIC_API_KEY and restart Polyglass.")


def available_translators(cfg: Config) -> list[str]:
    names = ["auto", "claude", "deepl"]
    if cfg.allow_unofficial_google:
        names.append("google")
    return names


def create_translator(cfg: Config) -> Translator:
    choice = cfg.translator
    if choice == "auto":
        if has_claude_credentials():
            choice = "claude"
        elif deepl_key():
            choice = "deepl"
        elif cfg.allow_unofficial_google:
            choice = "google"
        else:
            return NoTranslator()
    if choice == "claude":
        return ClaudeTranslator(cfg.claude_model, cfg.claude_effort)
    if choice == "deepl":
        key = deepl_key()
        if not key:
            raise RuntimeError("translator is 'deepl' but DEEPL_API_KEY is not set")
        return DeepLTranslator(key)
    if choice == "google":
        if not cfg.allow_unofficial_google:
            raise RuntimeError("the keyless Google endpoint is off; set allow_unofficial_google in config.json")
        return GoogleFreeTranslator()
    raise RuntimeError(f"unknown translator '{choice}'")
