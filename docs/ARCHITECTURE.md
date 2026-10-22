# Architecture

Polyglass is a small pipeline: **capture → OCR → layout → translate → paint**. Each stage lives in its own
module, so an OCR engine or translator can be swapped without touching the rest.

```
             hotkeys.py ──┐
                          ▼
  ui.AreaPicker ──► app.py (tray, menus, wiring) ──► ui.Overlay (paints translations)
                          │                                   ▲
                          ▼                                   │ blocks
                   worker.Worker thread ──────────────────────┘
                   capture (mss) → ocr.py → layout.py → translate.py (own thread)
```

## Modules

| Module | Job |
|---|---|
| `app.py` | Entry point. Tray icon and menus, hotkeys, single-instance guard, crash dialog, and the glue between picker, worker and overlay. |
| `worker.py` | Background loop for the watched area: grab it a few times a second, detect when content changed and then settled, run OCR and layout, look translations up in a cache and send the rest to the translator on a separate thread. |
| `ocr.py` | Windows' built-in OCR (`Windows.Media.Ocr` via WinRT). Returns lines with pixel boxes; upscales small areas because Windows OCR misses small text. |
| `layout.py` | Measures each line (background and text colour, font size, stroke weight), grows boxes over characters OCR dropped, and groups lines into blocks: paragraphs are joined with spaces, list items keep their line breaks. |
| `translate.py` | Translators behind one interface: Claude (structured JSON output, earlier blocks as context), DeepL, and an opt-in unofficial Google endpoint. |
| `ui.py` | The overlay window (click-through, always on top, excluded from screen capture) and the drag-to-select picker. |
| `hotkeys.py` | System-wide hotkeys through Win32 `RegisterHotKey`, on a thread with its own message loop. |
| `config.py` | Settings dataclass stored as JSON, with versioned migrations. Never holds API keys. |
| `keys.py` | API keys: environment variable first, otherwise Windows Credential Manager (via `keyring`). |
| `settings_window.py` | The settings dialog: translator and languages, keys, hotkeys, frame, start with Windows, update check. |
| `system.py` | Windows integration: start-with-Windows registry value, GitHub update check, pre-filled bug reports (3 a day). |
| `paths.py`, `logs.py` | Where files live (`%APPDATA%`, `%LOCALAPPDATA%`), the rotating log file and the unhandled-exception hooks. |

## Building and releasing

- `tools/build_icons.py` renders `assets/polyglass.svg` into the app and installer icons.
- `polyglass.spec` (PyInstaller) bundles the app into `dist/Polyglass/Polyglass.exe`.
- `installer/polyglass.iss` (Inno Setup) wraps that folder into a per-user installer.
- Pushing a `vX.Y.Z` tag runs `.github/workflows/release.yml`, which tests, builds both and publishes a
  GitHub release with the installer and a portable zip.
- `tools/third_party_notices.py` regenerates `THIRD_PARTY_NOTICES.md` after dependency changes.

## Design decisions

- **Physical pixels everywhere.** Qt runs with high-DPI scaling off, so overlay coordinates, OCR boxes and
  screen captures share one coordinate space even across monitors with different scaling.
- **The overlay is invisible to capture** (`SetWindowDisplayAffinity` with `WDA_EXCLUDEFROMCAPTURE`), so
  OCR never reads Polyglass's own translations back.
- **Only Qt touches windows.** Background threads talk to the UI through Qt signals (`app.Bridge`); the
  capture loop never waits on the network.
- **Change detection before OCR.** A cheap downscaled diff decides when to re-read; OCR runs only once
  content has changed *and* settled, so scrolling doesn't trigger a burst of translations.
- **Translate blocks, not lines.** Lines are grouped into paragraphs first so the translator sees whole
  sentences; translations are cached by normalised source text, so text seen before reappears instantly.
- **Qt before WinRT.** Importing PySide6 after the WinRT modules crashes the process, so `ocr.py` imports
  Qt first, and the QApplication is created before any WinRT call on the main thread.
