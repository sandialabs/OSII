"""Build and install OSII outside the checkout, as a pip user would.

Run with: uv run --no-project --python 3.12 --with build python scripts/check_python_distribution.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from zipfile import ZipFile


def main() -> None:
    core = Path(__file__).resolve().parents[1] / "osii-core"
    with tempfile.TemporaryDirectory(prefix="osii-package-") as directory:
        temporary = Path(directory)
        distributions = temporary / "dist"
        # By default, build creates the wheel from the sdist. This checks both.
        subprocess.run(
            [sys.executable, "-m", "build", str(core), "--outdir", str(distributions)],
            check=True,
        )
        wheel, = distributions.glob("*.whl")
        with ZipFile(wheel) as archive:
            packaged_files = set(archive.namelist())
        for package in ("osii", "osii_processor_sdk"):
            for source in (core / package).rglob("*.py"):
                assert source.relative_to(core).as_posix() in packaged_files, source
        environment = temporary / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheel)],
            cwd=temporary,
            check=True,
        )
        subprocess.run([str(python), "-m", "pip", "check"], cwd=temporary, check=True)
        subprocess.run(
            [str(python), "-I", "-c", """
from importlib.metadata import distribution, distributions
import osii.processor_sdk as sdk
import osii_processor_sdk as legacy
from osii_processor_sdk.models import ExtractionRequest
from osii.processors import remote

assert ExtractionRequest is sdk.ExtractionRequest
assert legacy.Extractor is sdk.Extractor
assert all('osii-processor-sdk' not in requirement for requirement in distribution('osii').requires)
assert 'osii-processor-sdk' not in {package.metadata['Name'] for package in distributions()}
print('OSII wheel installed successfully, including current and legacy processor imports.')
"""],
            cwd=temporary,
            check=True,
        )


if __name__ == "__main__":
    main()
