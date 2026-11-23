# Whisper speech to text

Turn a recording into searchable text with the **Whisper speech to text**
extractor. It runs on the CPU with [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
keeps audio local, and returns start and end times for each text segment.
OSII Core saves and indexes the transcript. This processor does not identify
speakers or translate the speech.

## Use in OSII

1. Stage an approved **CTranslate2-format Whisper** model on the machine running
   the processor. Start with a small multilingual `base` model, or `base.en`
   for English only. The directory must contain `model.bin`, `config.json`,
   and `tokenizer.json`. A PyTorch checkpoint or GGML model is not compatible.
   Neither startup nor extraction downloads weights.
2. Add these settings to the repository's ignored `.env` (on Windows, an
   absolute path such as `C:/models/whisper-base` works):

   ```dotenv
   OSII_ENABLE_WHISPER=true
   OSII_WHISPER_MODEL_DIR=/absolute/path/to/whisper-base-ct2
   ```

3. Restart `make dev` (Windows: `.\scripts\osii.ps1 dev`). In **Intake**,
   select a short recording and choose **Whisper speech to text** for
   extraction. Leave **Spoken language code** blank to detect the language,
   or set a supported lowercase code such as `en`.

This module accepts WAV, MP3, M4A, FLAC, Ogg, Opus, and WebM with an audio
stream. It transcribes the first audio stream, up to 24 MiB and 10 minutes of
decoded audio per request. Split longer recordings. Start with a short clip:
CPU speed varies and Core's normal Processor API timeout still applies.
Timestamps are stored as `start_seconds` and `end_seconds` in segment provenance;
this module does not add an audio player or playback controls to OSII.

## Run or test independently

From this module's directory, set `OSII_WHISPER_MODEL_DIR` in your shell, then run:

```sh
uv run --python 3.12 python -m uvicorn osii_whisper.main:app --host 127.0.0.1 --port 8115
```

Register `http://127.0.0.1:8115` as an extractor in Setup if using a different
checkout. The OSII API process must be able to reach that address. For source
launches, `OSII_WHISPER_PORT` overrides the port. Live API docs are at `/docs`;
`/health` checks the adapter and `/ready` checks staged files without loading
weights. Intake's synthetic processor test does not provide an audio sample;
use a short recording for a real check.

Run `uv run --python 3.12 --extra dev python -m pytest -q` for the offline
contract tests. They decode a generated WAV and stub recognition. Model
accuracy and performance require a separate test with staged weights.
