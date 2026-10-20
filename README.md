# Lens Overlay

Live, Google Lens style screen translation for Windows. Pick an area of the screen; the app keeps
watching it, reads the text with Windows' built-in OCR, translates it, and paints the translation
over the original text, matching its background colour, text colour, size and weight.

## Use

- `Lens Overlay.cmd` starts it (tray icon, blue "文A").
- **Ctrl+Alt+L**: drag over the text to translate (Esc cancels). Pick again to move the area.
- **Ctrl+Alt+K**: hide/show the overlay to peek at the original.
- **Ctrl+Alt+X**: stop watching.
- Tray menu: source language (installed Windows OCR languages), target language, translator, quit.

The overlay ignores the mouse, so you can keep clicking and scrolling underneath it. When the
content changes (scrolling, new subtitles), it re-reads the area once the picture settles. Text it
has seen before is translated instantly from a cache.

## Translators

`translator` in `config.json` (or the tray menu):

| value    | needs                                         | notes                                             |
|----------|-----------------------------------------------|---------------------------------------------------|
| `claude` | `ANTHROPIC_API_KEY` environment variable      | best context handling; model and effort in config |
| `deepl`  | `DEEPL_API_KEY` environment variable          | free plan: 500k characters/month                  |
| `google` | nothing                                       | keyless endpoint, no context awareness            |
| `auto`   |                                               | first of claude, deepl, google that is available  |

Set a key once in PowerShell with
`[Environment]::SetEnvironmentVariable("DEEPL_API_KEY", "<key>", "User")`, then restart the app.

## Languages

Source languages are the Windows OCR languages installed on this PC (Settings → Time & language →
Language → add a language with "Optical character recognition"). Currently: English, French, Serbian.

## Setup on a new machine

Run `setup.cmd` once (needs Python 3.11+).
