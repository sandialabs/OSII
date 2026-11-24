# OCRia-nano-1 via LiteParse

An opt-in OSII extractor for PDFs and PNG/JPEG scans. LiteParse uses
OCRia-nano-1 locally on the CPU when it needs OCR and uses a PDF's existing
text layer when suitable. The adapter returns page-linked Markdown or text;
LiteParse can reconstruct tables, but this adapter does not emit separate
table artifacts or region boxes.

## License: read before staging the model

- **LiteParse software:** [Apache License 2.0](https://github.com/run-llama/liteparse/blob/main/LICENSE).
  The adapter uses the separately installed LiteParse Python package. ONNX
  Runtime has its own [MIT license](https://github.com/microsoft/onnxruntime/blob/main/LICENSE).
- **OCRia-nano-1 model weights and accompanying licensed files:** the
  [OCRia-nano-1 Model License](https://huggingface.co/llamaindex/OCRia-nano-1/resolve/main/LICENSE),
  a modified Open RAIL-M license, **not Apache-2.0 or an unrestricted
  open-source license**. The branch and its ZIP contain the adapter, not the
  weights, model configuration, or ONNX runtime binaries.
- Attachment A restricts use above **US$2 million in prior-year gross
  revenue** or **US$2 million in total equity or debt funding**, with
  exceptions for personal use or the license's defined research purposes.
  It also restricts competing document-parsing/OCR/extraction products or
  services regardless of size, except for research purposes. Evaluation can
  qualify as research; do not assume internal production use qualifies.
- The license also restricts certain uses of outputs and sets conditions
  on redistribution. Read the full agreement. Confirm your organization's
  authorized use and, if needed, [obtain a license from LlamaIndex](https://www.llamaindex.ai/contact)
  before downloading, deploying, or distributing the model. The environment
  flag below records an operator decision; it grants no rights.

## Set up and run

After confirming authorization, from this module's directory:

```sh
uv run --python 3.12 lit models pull ocria-nano
```

For an offline install with an approved local model package, use
`uv run --python 3.12 lit models pull ocria-nano --from /path/to/package`.
The same model directory must be visible to LiteParse when OSII runs. If you
override `LITEPARSE_MODEL_DIR`, use the same absolute path in the installation
shell and in OSII's ignored root `.env`. The adapter never downloads models.

In the ignored root `.env`, add:

```dotenv
OSII_ENABLE_OCRIA=true
OSII_OCRIA_LICENSE_ACKNOWLEDGED=true
```

Restart `make dev` on macOS/Linux or `.\scripts\osii.ps1 dev` on Windows.
In Intake select **OCRia-nano-1 via LiteParse** as the extractor. It isn't a
default route. Inputs are capped at 20 MiB, 25 PDF pages, and a 24-megapixel
render per page (10,000 pixels max per side). Blank pages can have no text;
an incomplete parse is rejected instead of silently saved.

For manual registration, start from the module directory with the
acknowledgment and model directory set in the process environment:

```sh
uv run --python 3.12 python -m uvicorn osii_ocria.main:app --host 127.0.0.1 --port 8117
```

Register `http://127.0.0.1:8117` in Setup. `/health` checks the adapter,
`/ready` checks acknowledgment and model staging without parsing, and
`/docs` shows the Processor API. Set `OSII_OCRIA_PORT` to override the
launcher port. Test without downloading a model using
`uv run --python 3.12 --extra dev python -m pytest -q`.
