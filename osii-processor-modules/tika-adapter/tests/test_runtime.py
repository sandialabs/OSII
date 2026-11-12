import hashlib
import io
import socket
import sys
import threading
from types import SimpleNamespace

import pytest
from tika_adapter import runtime


def test_verified_download_is_atomic_and_reused(tmp_path, monkeypatch):
    body = b'verified runtime fixture'
    monkeypatch.setattr(runtime, 'SHA512', hashlib.sha512(body).hexdigest())
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(body))
    target = runtime.verified_jar(tmp_path)
    assert target.read_bytes() == body
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Cached jar must not download again'))
    assert runtime.verified_jar(tmp_path) == target


def test_checksum_failure_never_publishes_download(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'bad download'))
    with pytest.raises(RuntimeError, match='checksum'):
        runtime.verified_jar(tmp_path)
    assert not list(tmp_path.iterdir())


def test_disabled_runtime_does_not_download_or_start(monkeypatch):
    monkeypatch.setenv('OSII_TIKA_MANAGED', 'false')
    monkeypatch.setattr(runtime, 'verified_jar', lambda *a: pytest.fail('Disabled runtime downloaded'))
    managed = runtime.ManagedTika()
    managed.start()
    managed.close()
    assert managed.thread is None


def test_owned_jvm_stops_with_module(tmp_path, monkeypatch):
    monkeypatch.setenv('OSII_TIKA_SERVER_PORT', '0')
    monkeypatch.setenv('OSII_TIKA_MANAGED', 'true')
    monkeypatch.setattr(runtime, 'verified_jar', lambda *a: tmp_path/'tika.jar')
    monkeypatch.setitem(sys.modules, 'jdk4py', SimpleNamespace(JAVA='managed-java'))
    started = threading.Event()
    calls = []
    class Process:
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): self.returncode = 0
        def wait(self, **kwargs): return self.returncode
    process = Process()
    def launch(command):
        calls.append(command)
        started.set()
        return process
    monkeypatch.setattr(runtime.subprocess, 'Popen', launch)
    managed = runtime.ManagedTika()
    managed.start()
    assert started.wait(2)
    managed.close()
    assert process.returncode == 0
    assert calls[0][0] == 'managed-java'
    assert '--noFork' in calls[0]


def test_runtime_failure_is_isolated_and_port_ownership_preserved(monkeypatch):
    monkeypatch.setenv('OSII_TIKA_MANAGED', 'true')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0)); listener.listen()
        monkeypatch.setenv('OSII_TIKA_SERVER_PORT', str(listener.getsockname()[1]))
        monkeypatch.setattr(runtime, 'verified_jar', lambda *a: pytest.fail('Must not prepare after a port conflict'))
        managed = runtime.ManagedTika()
        managed.start(); managed.thread.join(2); managed.close()
        assert 'already in use' in managed.error
        assert managed.process is None
        assert listener.fileno() >= 0
