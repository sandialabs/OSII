# Python demonstrations

OSII includes numbered, code-first demonstrations in
`osii-demo-notebooks/`. The files are flat Python scripts with Jupytext cell
markers, so they can be run directly or converted into notebooks.

From the repository root, install the demonstration dependencies and convert
the first script:

```bash
cd osii-demo-notebooks
python -m pip install -r requirements.txt
jupytext --to ipynb 00_Setup_a_demo_workspace.py
```

Run the numbered files in order. They create a `demo-workspace/` directory
inside the demonstrations directory; that generated workspace is ignored by
Git.

Start the normal OSII stack before running the extraction and embedding
examples. On macOS or Linux:

```bash
cd ..
make dev
```

On Windows PowerShell, run this from the repository root:

```powershell
.\scripts\osii.ps1 dev
```

The local walkthrough does not require a model gateway. The final examples
show how an optional OpenAI-compatible endpoint or custom Processor API
service fits into the same workflow.

## Source format

The `.py` files are the reviewable source format for the demonstrations.
Legacy `.ipynb` files are retained for notebook users. To regenerate a Python
companion from an existing notebook, run this command from the repository root
with the Python launcher available on your platform:

```bash
python scripts/notebook_to_py.py osii-demo-notebooks/01_Welcome_to_OSII_the_On-Store_Intelligence_Index.ipynb
```

Do not edit notebook JSON by hand. Make changes in the Python companion unless
the notebook itself specifically needs to be regenerated.
