# Vision model document reader

Read images and short PDFs with a vision-language model (VLM) you already
operate or are authorized to use. The endpoint must implement
[OpenAI-compatible Chat Completions with image inputs](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)
and accept JPEG data URLs and the `max_tokens` request field. A text-only
chat endpoint will not work.

## Use in OSII

1. Add your endpoint and vision model to the repository's ignored `.env`.
   The base URL includes the endpoint's API prefix, typically `/v1`, but
   not `/chat/completions`. Omit the key if your endpoint does not require one.

   ```dotenv
   OSII_ENABLE_VLM_ENDPOINT=true
   OSII_VLM_BASE_URL=https://vision.example.com/v1
   OSII_VLM_MODEL=your-vision-model
   OSII_VLM_API_KEY=replace-with-your-key
   ```

2. Restart `make dev` (Windows: `.\scripts\osii.ps1 dev`). In **Intake**,
   select an image or short PDF and choose **Vision model document reader**
   for extraction.

The processor sends the pixels of each selected page or image to that endpoint.
Use a provider approved to receive the documents. The adapter does not send
source filenames, filesystem paths, or expert context. The service's key is
not saved in the library or selectable per request. HTTPS is required when
using a key with a non-loopback endpoint.

Inputs: PNG, JPEG, WebP still images, and PDFs (including scanned pages).
Limits: 20 MiB per input, 24 megapixels per input image, and 10 PDF pages.
Each page is sent separately as a JPEG no larger than 2,048 pixels on its
longest edge. Use a smaller PDF if the endpoint cannot finish within the Core
request timeout. Output is a model-generated transcription with page and model
provenance, not bounding boxes; verify important text against the original.
A failed or truncated upstream completion rejects the extraction rather than
silently saving partial results.

## Run or test independently

From this module's directory, set `OSII_VLM_BASE_URL`, `OSII_VLM_MODEL`,
and, if needed, `OSII_VLM_API_KEY` in your shell, then run:

```sh
uv run --python 3.12 python -m uvicorn osii_vlm_endpoint.main:app --host 127.0.0.1 --port 8116
```

Register `http://127.0.0.1:8116` as an extractor in Setup if using a different
checkout. The OSII API process must be able to reach that address. For source
launches, `OSII_VLM_ENDPOINT_PORT` overrides the port. Live docs are at
`/docs`; `/health` checks the adapter, and `/ready` checks configuration
without calling the provider. To verify provider access, explicitly test
extraction with a non-sensitive sample.

Run `uv run --python 3.12 --extra dev python -m pytest -q` for the offline
contract tests. They render generated images/PDFs and use a mock endpoint;
they do not contact a live provider.
