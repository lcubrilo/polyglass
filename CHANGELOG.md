# Changelog

Notable changes to Polyglass. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-20

First working version.

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
