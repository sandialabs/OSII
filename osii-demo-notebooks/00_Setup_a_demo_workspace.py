# %% [markdown]
# # 00 — Welcome and create a safe demo workspace
#
# OSII turns ordinary source files into a portable, inspectable sidecar. The
# source files remain untouched. This walkthrough uses a small generated corpus
# so every example is repeatable and safe to experiment with.
#
# Run the numbered files in order. Every generated file stays inside
# `demo-workspace/`, which Git ignores.

# %%
from __future__ import annotations

import shutil

from _demo_support import demo_paths, heading


paths = demo_paths()

# This is intentionally the only destructive line in the walkthrough. The
# target is a fixed child of osii-demo-notebooks, never a user-selected folder.
if paths.workspace.exists():
    shutil.rmtree(paths.workspace)

(paths.source_root / "experiments").mkdir(parents=True)
(paths.source_root / "references").mkdir(parents=True)
paths.exports.mkdir(parents=True)

# %% [markdown]
# ## A tiny but realistic corpus
#
# Repeated terminology and named organizations make later search, keyword, and
# entity examples easy to understand.

# %%
(paths.source_root / "experiments" / "thermal_calibration.txt").write_text(
    """Thermal Calibration Experiment 17

The Thermal Systems Team at Sandia National Laboratories calibrated Sensor A
in July. The thermal calibration procedure reduced measurement drift from
3.1 percent to 0.8 percent. Repeat the thermal calibration measurement after
the chamber reaches 24 C. Morgan Lee approved the calibration report.
""",
    encoding="utf-8",
)

(paths.source_root / "experiments" / "vibration_test.txt").write_text(
    """Vibration Qualification Experiment 18

The Mechanical Test Group at Sandia National Laboratories tested Sensor A.
The vibration qualification procedure used three low-frequency sweeps. Morgan
Lee requested a follow-up thermal calibration measurement before release.
""",
    encoding="utf-8",
)

(paths.source_root / "references" / "sensor_handbook.md").write_text(
    """# Sensor A handbook

Sensor A is a laboratory temperature sensor. The recommended thermal
calibration procedure uses a stable reference chamber and repeated calibration
measurements. Record chamber temperature, measurement drift, and operator.
""",
    encoding="utf-8",
)

(paths.source_root / "references" / "handling_notes.txt").write_text(
    """Handling notes

The Laboratory Safety Office requires an equipment inspection before vibration
qualification work. These generated demonstration files contain no sensitive
or proprietary information.
""",
    encoding="utf-8",
)

heading("Generated source corpus")
for source in paths.source_files():
    print("-", source.relative_to(paths.source_root).as_posix())

print(f"\nSource files: {paths.source_root}")
print(f"OSII sidecar: {paths.osii_root}")

# %% [markdown]
# Next, `01_Create_an_OSII_store.py` initializes the portable `.osii` sidecar.
# No service, container, database server, or model is needed yet.
