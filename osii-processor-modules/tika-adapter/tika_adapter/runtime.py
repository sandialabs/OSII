"""Managed, cached Apache Tika runtime. No source documents enter this module."""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import urllib.request

VERSION = '3.3.3'
SHA512 = '5242b1c9d7aa455bdb0fe101304b2c4a274882406f4d054af39cc91eef678aecb7bf31127d8cc692cd5f47a9f602f4840139f9e8e44a708e312b2ba59d1ebe89'
JAR_NAME = f'tika-server-standard-{VERSION}.jar'
DOWNLOAD_URL = f'https://archive.apache.org/dist/tika/{VERSION}/{JAR_NAME}'
log = logging.getLogger('tika.runtime')


def verified_jar(cache: Path) -> Path:
    """Publish only a complete jar matching the pinned Apache release checksum."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / JAR_NAME
    if target.exists():
        with target.open('rb') as cached:
            if hashlib.file_digest(cached, 'sha512').hexdigest() == SHA512:
                return target
    temporary = None
    try:
        log.warning('Preparing Apache Tika %s (first startup downloads and caches its runtime).', VERSION)
        with tempfile.NamedTemporaryFile(dir=cache, suffix='.download', delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha512()
            with urllib.request.urlopen(DOWNLOAD_URL, timeout=30) as response:
                while block := response.read(1024 * 1024):
                    digest.update(block)
                    output.write(block)
        if digest.hexdigest() != SHA512:
            raise RuntimeError('Apache Tika download failed checksum verification; it will not be executed.')
        temporary.replace(target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ManagedTika:
    """Own the JVM only when enabled; a failed runtime leaves the adapter available."""
    def __init__(self) -> None:
        self.enabled = os.getenv('OSII_TIKA_MANAGED', 'true').lower() not in {'false', '0', 'no', 'off'}
        self.port = int(os.getenv('OSII_TIKA_SERVER_PORT', '9998'))
        runtime = Path(os.getenv('OSII_RUNTIME_DIR', str(Path(__file__).resolve().parents[3] / 'osii-data')))
        self.cache = Path(os.getenv('OSII_TIKA_CACHE_DIR', str(runtime / 'processor-cache' / 'tika')))
        self.process: subprocess.Popen | None = None
        self.error: str | None = None
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.enabled:
            self.thread = threading.Thread(target=self._run, daemon=True, name='managed-tika')
            self.thread.start()

    def _run(self) -> None:
        try:
            with socket.socket() as probe:
                probe.settimeout(.2)
                if probe.connect_ex(('127.0.0.1', self.port)) == 0:
                    raise RuntimeError(f'Port {self.port} is already in use. Set OSII_TIKA_MANAGED=false to use an external Tika server.')
            jar = verified_jar(self.cache)
            from jdk4py import JAVA
            if self.stop.is_set():
                return
            self.process = subprocess.Popen([str(JAVA), '-jar', str(jar), '--host', '127.0.0.1', '--port', str(self.port), '--noFork'])
            while not self.stop.wait(.5):
                if self.process.poll() is not None:
                    raise RuntimeError(f'Apache Tika exited with code {self.process.returncode}; see the module log.')
        except Exception as exc:
            self.error = str(exc)
            log.error('Managed Apache Tika unavailable: %s. Other intake processors remain available.', exc)
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=16)
