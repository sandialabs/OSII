from pathlib import Path
import subprocess
import sys

import pytest

from osii.library_lock import LibraryLock


def test_another_launcher_cannot_own_the_same_library(tmp_path):
    command = [sys.executable, "-c", "from pathlib import Path; from osii.library_lock import LibraryLock; "
               "lock=LibraryLock(Path(__import__('sys').argv[1])).acquire()", str(tmp_path)]
    with LibraryLock(tmp_path):
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode != 0
        assert "already open" in result.stderr
    assert subprocess.run(command, capture_output=True).returncode == 0


def test_crashed_owner_releases_the_os_lock(tmp_path):
    code = ("from pathlib import Path; import os,sys; from osii.library_lock import LibraryLock; "
            "lock=LibraryLock(Path(sys.argv[1])).acquire(); os._exit(17)")
    assert subprocess.run([sys.executable, "-c", code, str(tmp_path)]).returncode == 17
    with LibraryLock(tmp_path):
        with pytest.raises(RuntimeError, match="already open"):
            LibraryLock(tmp_path).acquire()
