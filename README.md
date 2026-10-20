# Polyglass

**Live on-screen translation for Windows.** Pick any area of the screen. Polyglass keeps reading it and
paints the translation right over the original text, matching its background, colour, size and weight.
It works on anything you can see: apps, games, videos with burned-in subtitles, chats, images.

<!-- TODO: demo GIF -->

> Status: early alpha (0.1). Windows 10/11 only.

## How it works

1. Press **Ctrl+Alt+L** and drag over the text you want translated.
2. Polyglass watches that area. Whenever its content changes and settles (scrolling, new subtitles), it
   reads the text with Windows' built-in OCR, groups it into paragraphs and list items, and translates them.
3. Each translation is painted over its original, in matching colours. The overlay ignores the mouse, so
   you keep clicking and scrolling underneath, and it is invisible to screenshots.

| Hotkey | Action |
|---|---|
| **Ctrl+Alt+L** | Pick an area (again to move it) |
| **Ctrl+Alt+K** | Hide/show the overlay to peek at the original |
| **Ctrl+Alt+X** | Stop watching |

Everything else is in the tray menu: source and target language, translator, log folder.

## Translators

| Translator | Needs | Notes |
|---|---|---|
| Claude | `ANTHROPIC_API_KEY` environment variable | Best with context and slang; model and effort configurable |
| DeepL | `DEEPL_API_KEY` environment variable | The free plan covers 500,000 characters a month |

Set a key once in PowerShell, then restart Polyglass:

```powershell
[Environment]::SetEnvironmentVariable("DEEPL_API_KEY", "<your key>", "User")
```

Offline translation (downloadable language packs, no key needed) is planned.

## Languages

Text is read by Windows' own OCR, so the languages you can translate *from* are the Windows OCR languages
installed on your PC (Settings → Time & language → Language & region → add a language). Any language the
translator supports works as the target.

## Privacy

The screen area you pick is processed on your PC. Only the recognised text is sent, to the translator you
chose. Polyglass has no telemetry. Details in [docs/PRIVACY.md](docs/PRIVACY.md).

## Install

Installers are coming with the first release. Until then, from source (Python 3.11+):

```powershell
git clone <repository url> polyglass
cd polyglass
py -3.11 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\pythonw -m polyglass
```

Settings live in `%APPDATA%\Polyglass\config.json`, logs in `%LOCALAPPDATA%\Polyglass\logs`.

## Contributing

Bug reports, ideas and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[architecture overview](docs/ARCHITECTURE.md).

## License

[GNU GPL v3 or later](LICENSE). Polyglass builds on the open-source libraries listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
