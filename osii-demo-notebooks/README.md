# OSII Python demonstrations

These files are intentionally flat Python scripts with Jupytext cell markers.
Run them as scripts or convert them to notebooks when you are ready:

```bash
cd osii-demo-notebooks
python -m pip install -r requirements.txt
jupytext --to ipynb 00_Setup_a_demo_workspace.py
```

Run the numbered files in order. They use `demo-workspace/` inside this folder,
which is ignored by Git. Start the normal OSII stack before the extraction and
embedding examples:

```bash
cd ..
make dev
```

The local walkthrough does not need a model gateway. The final examples show
where an optional OpenAI-compatible endpoint or custom Processor API service
fits into the same workflow.
