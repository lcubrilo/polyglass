# Privacy

Polyglass looks at your screen, so here is exactly what happens to what it sees.

## Stays on your PC

- **Screenshots of the area you pick.** They are taken a few times per second, kept in memory only, and
  never saved to disk or sent anywhere.
- **OCR.** Text is recognised by Windows' built-in OCR engine, on your PC.
- **Settings** (`%APPDATA%\Polyglass\config.json`) and **logs** (`%LOCALAPPDATA%\Polyglass\logs`). Logs
  record what Polyglass did and any errors; they do not record the text it translated.

## Sent over the internet

- **The recognised text**, to the translation service you chose, and nothing else. With Claude, a few
  earlier text blocks from the same session are included as context so translations stay consistent. Each
  service handles that text under its own terms:
  [Anthropic](https://www.anthropic.com/legal/privacy) · [DeepL](https://www.deepl.com/privacy).
- **API keys** go only to the service they belong to. Polyglass reads them from environment variables and
  never writes them to its own files or logs.

## Never

- No telemetry, analytics, usage statistics or crash reports are sent anywhere.
- No account is needed.

Offline translation, planned for a later version, will keep the text on your PC as well.
