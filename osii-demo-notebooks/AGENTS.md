# Notebook directory guidance

The `.ipynb` files in this directory are human-facing notebook artifacts.
Agents must not read, edit, format, or otherwise rewrite them unless the human
explicitly requests work on a named notebook. Use the same-basename `.py` file
for normal review and code changes.

To create or refresh a paired Python file without exposing notebook JSON in an
agent session, run:

```bash
python3 scripts/notebook_to_py.py osii-demo-notebooks/name.ipynb
```
