# %% [markdown]
# # 00 — Set up a demo workspace
#
# This first script creates a small corpus. Run the numbered scripts from this
# folder in order. The generated `demo-workspace/` is safe to delete and retry.

# %%
import shutil

from _demo_support import demo_paths

NOTEBOOK_DIR, SOURCE_ROOT, OSII_ROOT = demo_paths()
# Reset only derived demo artifacts so the numbered walkthrough is repeatable.
if OSII_ROOT.exists():
    shutil.rmtree(OSII_ROOT)
sample = SOURCE_ROOT / "experiment_notes.txt"
sample.write_text(
    "Experiment 17 — thermal calibration\n\n"
    "The July calibration reduced drift from 3.1% to 0.8%. "
    "Repeat the measurement after the chamber reaches 24 C.\n",
    encoding="utf-8",
)

print(f"Source folder: {SOURCE_ROOT}")
print(f"OSII store:    {OSII_ROOT}")
print(f"Sample file:   {sample}")

# %% [markdown]
# The extraction and embedding demonstrations expect the normal OSII stack to
# be running (`make dev` from the repository root). It supplies local Tika at
# `http://localhost:9998`. The embedding demonstration uses its host-exposed
# port, `http://localhost:8085/v1`.
