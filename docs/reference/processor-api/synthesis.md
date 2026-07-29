# Synthesis API

`POST /v1/synthesize` produces grounded Markdown for an object, folder,
collection, or root scope.

The core supplies preferred text. Synthesizers do not read `.osii` and must not
perform their own corpus traversal.

## Request

```json
{
  "api_version": "v1",
  "request_id": "synth-88",
  "scope": {
    "scope_type": "collection",
    "scope_id": "calibration-runs",
    "documents": [{
      "file_id": "sha256-a",
      "filename": "run-a.txt",
      "text": "Calibration drift was 0.4%...",
      "metadata": {"representation": "edited"}
    }]
  },
  "expert_context": "Focus on deviations from procedure Q-17.",
  "config": {"maximum_words": 400}
}
```

## Response

```json
{
  "api_version": "v1",
  "request_id": "synth-88",
  "processor": {"...descriptor": "..."},
  "markdown": "## Findings\nCalibration drift remained below 0.5%...",
  "citations": [{
    "file_id": "sha256-a",
    "char_start": 0,
    "char_end": 31
  }],
  "metadata": {"input_documents": 1},
  "warnings": []
}
```

Claims should be tied to citations whenever possible. Character offsets refer
to the exact document text sent in the request.

See `examples/synthesizer.py`.
