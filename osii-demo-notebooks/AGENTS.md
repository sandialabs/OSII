# Notebook directory guidance

The `.ipynb` files in this directory are human-facing artifacts. Agents must
not read, edit, format, or rewrite them unless the human explicitly requests
work on a named notebook. Use the same-basename `.py` files for normal review
and code changes.

The canonical walkthrough is the stem list in `manage_notebooks.py`. Convert
its reviewable Python sources to notebooks with:

```bash
python manage_notebooks.py to-notebooks
```

Convert human-edited notebooks back to percent-format Python with:

```bash
python manage_notebooks.py to-python --force
```

Always review the resulting diff. Never hand-edit notebook JSON.
