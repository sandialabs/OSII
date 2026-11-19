# OSII demo notebooks

Learn OSII through small Python and Jupyter examples. This optional branch
contains the demonstrations, their helper, and a sample PDF. Install OSII Core
as a Python dependency; the application and dashboard are separate downloads.

## Download and install

Clone only this branch:

```bash
git clone --single-branch --branch osii-demo-notebooks git@github.com:heidikmkv/osii-private.git osii-demo-notebooks
cd osii-demo-notebooks
```

You can also download a ZIP after selecting `osii-demo-notebooks` on GitHub once
the branch is published. Installation requires Python 3.12, Git, and repository
access. `requirements.txt` pins OSII Core to the revision used by these examples.

On macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Then, on either platform:

```bash
python -m ipykernel install --user --name osii-demo --display-name "OSII demo"
python manage_notebooks.py to-notebooks
jupyter lab
```

Choose **OSII demo** as the kernel. The `.py` files are the reviewable sources;
the conversion command refreshes their notebook companions. You can also run
individual Python files directly. Keep this `.venv` separate from the running
application's managed environment.

## Follow the series

| Steps | What you learn |
| --- | --- |
| 00 | Create a store and inspect canonical sidecars |
| 01–02 | Extract grounded text and create a cited preview |
| 03–04 | Build a collection and search without a model |
| 05–07 | Add embeddings, standard artifacts, and optional models |
| 08–10 | Write an extractor, synthesizer, and enricher with the SDK |
| 11 | Read CSV datasets through a separately running processor |

Put your own files in `demo-workspace/documents/`. Extra documents and generated
state are ignored by Git. Originals remain unchanged; results are written to
`demo-workspace/.osii/`.

## Connect optional services

Some lessons call processors over HTTP. Install and start the OSII application
separately using its [startup guide](https://github.com/heidikmkv/osii-private/blob/main/docs/operations/runbook-development.md).
Run `make dev`, or `.\scripts\osii.ps1 dev` on Windows, from that application
checkout. Native Tesseract is required for the scanned sample PDF. Wait for
`http://127.0.0.1:8080/health` before running step 01.

For step 11, run `make demo-data` in the application checkout, then use `make dev`
to start the CSV processor on port 8097. Windows uses `.\scripts\osii.ps1 demo-data`
and `.\scripts\osii.ps1 dev`. Set `OSII_DEMO_DATA_DIR` to the resulting
`example-datasets` directory, or place a copy under `demo-workspace/example-datasets/`.
Model-backed lessons need an explicitly configured endpoint; they may make
billable requests. Services and model weights are not included in this branch.

## Edit the walkthrough

Edit the paired `.py` sources and run `python manage_notebooks.py to-notebooks`.
To bring deliberate Jupyter edits back into Python, run
`python manage_notebooks.py to-python`. Review the conversion diff.

Continue with the [Processor API](https://github.com/heidikmkv/osii-private/blob/main/docs/reference/processor-api/index.md)
when building an independent processor.
