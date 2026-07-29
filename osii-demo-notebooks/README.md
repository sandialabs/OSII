# OSII Python demonstrations

These files are intentionally flat Python scripts with Jupytext cell markers.
Run them as scripts or convert them to notebooks when you are ready:

```bash
cd osii-demo-notebooks
python -m pip install -r requirements.txt
python py_to_notebook.py 00_Setup_a_demo_workspace.py
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

## Notebook companions

The legacy `.ipynb` demonstrations are retained for notebook users. Their
same-basename `.py` companions are the reviewable, agent-safe source format.
To regenerate a companion without manually editing notebook JSON, run:

```bash
python notebook_to_py.py 01_Welcome_to_OSII_the_On-Store_Intelligence_Index.ipynb
```

To generate a notebook from one of the new flat Python demonstrations:

```bash
python py_to_notebook.py 05_Build_and_search_a_lexical_index.py
```

Agents are instructed not to open or modify `.ipynb` files unless a human
explicitly requests it.
