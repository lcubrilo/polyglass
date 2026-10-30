# Changelog

Notable changes to Polyglass. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-30

### Added

- Live captions (Ctrl+Alt+S, or the tray menu): speech in whatever the PC is playing is transcribed on the
  PC with Whisper (faster-whisper) and shown as translated subtitles at the bottom of the screen. Off by
  default. Runs on an NVIDIA GPU when the CUDA libraries are available (`pip install -e ".[gpu]"` from
  source), otherwise on the CPU. The speech model downloads once on first use.
- Settings → Live captions: language spoken (or automatic detection), speech model size, GPU or CPU.
- The self-test (`Polyglass.exe --selftest`) also checks that the speech libraries load.
- README: running from source, a script that creates a desktop or Start Menu shortcut
  (`tools/create_shortcut.ps1`), and how to translate a video's subtitles.

### Fixed

- The unofficial Google translator returned nothing for Serbian written in Latin script; it now falls back
  to Google's language detection.

## [0.1.0] - 2026-10-22

First public release.

### Added

- Pick an area of the screen (Ctrl+Alt+L) and watch it continuously; re-read it when its content changes
  and settles.
- Windows OCR with per-line positions; lines grouped into paragraphs and list items; background colour,
  text colour, size and weight measured per line.
- Click-through overlay that paints translations over the original text and is hidden from screen capture,
  with subtle corner marks around the watched area.
- Translators: Claude (with surrounding context) and DeepL; an unofficial keyless Google endpoint as an
  opt-in for personal use.
- Tray menu for languages and translator; hotkeys to hide/show (Ctrl+Alt+K) and stop (Ctrl+Alt+X).
- Settings in `%APPDATA%\Polyglass` with versioned migrations; rotating log file; crash dialog; a second
  launch reuses the running copy.
- Logo: Polly, a stained-glass parrot, as the app, tray and installer icon.
- Settings window: translator, languages, Claude model and effort, API keys, hotkeys, corner marks, start
  with Windows, update check. It opens by itself on first run when no translator is set up.
- API keys are stored in Windows Credential Manager.
- Update check at startup (can be turned off) and a "Report on GitHub" button in the error dialog that
  opens a pre-filled issue, at most three a day.
- Windows installer (per user, no admin rights) and portable zip, built and published automatically when a
  version tag is pushed.
