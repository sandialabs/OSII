# Notebook directory guidance

The `.ipynb` files in this directory are human-facing artifacts. Agents must
not read, edit, format, or rewrite them unless the human explicitly requests
work on a named notebook. Use the same-basename `.py` files for normal review
and code changes.

The canonical walkthrough is discovered from the Jupytext-marked Python files
in this directory. Convert all reviewable Python sources to notebooks with:

```bash
python manage_notebooks.py to-notebooks
```

Convert human-edited notebooks back to percent-format Python with:

```bash
python manage_notebooks.py to-python
```

Always review the resulting diff. Never hand-edit notebook JSON.

## Instructional design

- Treat every notebook as a guided research conversation, not a dump of runnable
  code. State the question and architectural reason before introducing the
  mechanism.
- Keep one primary learning objective per section. Split setup, configuration,
  discovery, execution, and inspection into short cells with visible outputs.
- Prefer small copyable operations over long orchestration blocks. When a loop
  or helper is necessary, first demonstrate the operation on one representative
  object.
- Explain why OSII separates originals, canonical sidecars, rebuildable indexes,
  and derived artifacts. Ask the reader to inspect those boundaries as they are
  created.
- Reinforce the processor rule throughout the series: processors compute typed
  results; OSII core validates provenance and owns persistence.
- Teach explicit objects and scopes as context shared by people, Python, REST,
  the dashboard, MCP, and future agents. Do not frame ambient filesystem access
  as the normal agent workflow.
- Start from local and model-free behavior, then label optional OCR, model,
  corporate, and emulated paths accurately. Never hide a network or model call
  inside an otherwise local-looking cell.
- Use `osii_processor_sdk` top-level imports in extension lessons. Show a
  descriptor, typed sample request, direct algorithm test, assertions, and the
  generated HTTP adapter in distinct steps.
- Use core `osii` imports deliberately. If an example reaches into a focused
  internal module because no friendly facade exists yet, explain that status
  rather than presenting the path as an established public API.
- End each notebook with what the reader should now understand, what artifact or
  provenance to inspect, and which next notebook builds naturally on it.

## Environment clarity

- The canonical notebook kernel is `osii-demo-notebooks/.venv`, created from
  this directory with Python 3.11 and `requirements.txt`.
- `osii-env` is launcher-managed application-service state for `make dev` and
  `scripts/osii.ps1 dev`; do not tell notebook users to activate it or select it
  as their Jupyter kernel.
- Optional processors run as separate services. Put the exact cross-platform
  launch command and health endpoint beside the first cell that calls one, and
  fail or skip with a readable next action when it is offline.
