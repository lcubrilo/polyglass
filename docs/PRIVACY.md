# Privacy

Polyglass looks at your screen, so here is exactly what happens to what it sees.

## Stays on your PC

- **Screenshots of the area you pick.** They are taken a few times per second, kept in memory only, and
  never saved to disk or sent anywhere.
- **OCR.** Text is recognised by Windows' built-in OCR engine, on your PC.
- **Sound, for live captions.** While captions are on, Polyglass records what your speakers play (never the
  microphone), in memory only. Speech is transcribed by a Whisper model running on your PC; the audio is
  never saved or sent anywhere. Logs record how long each piece took, not what was said.
- **Settings** (`%APPDATA%\Polyglass\config.json`) and **logs** (`%LOCALAPPDATA%\Polyglass\logs`). Logs
  record what Polyglass did and any errors; they do not record the text it translated.

## Sent over the internet

- **The recognised text** (or transcribed speech), to the translation service you chose, and nothing
  else. With Claude, a few earlier text blocks or captions from the same session are included as context
  so translations stay consistent. Each
  service handles that text under its own terms:
  [Anthropic](https://www.anthropic.com/legal/privacy) · [DeepL](https://www.deepl.com/privacy).
- **API keys** go only to the service they belong to. They are kept in Windows Credential Manager (or
  read from environment variables) and never written to Polyglass's own files or logs.
- **The speech model download.** The first time live captions start, the Whisper model is downloaded from
  Hugging Face (the `Systran` or `mobiuslabsgmbh` faster-whisper models) into
  `%LOCALAPPDATA%\Polyglass\models`. Only the model is requested; nothing about you or your audio is sent.
- **Update check** (can be turned off in Settings): when Polyglass starts, it asks GitHub for the latest
  release version. The request contains nothing about you or your screen.
- **Bug reports** happen only when you click "Report on GitHub" after an error. That opens a pre-filled
  GitHub issue in your browser with the error and the end of the log; nothing is sent until you review it
  and submit it yourself. At most three a day can be started.

## Never

- No telemetry, analytics or usage statistics, and no crash reports unless you choose to send one.
- No account is needed.

Offline translation, planned for a later version, will keep the text on your PC as well.
