from pathlib import Path
import os

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text

from osii.persistence.postgres import PostgresStore, metadata
from osii.server.api import create_app
from osii.server.auth import password_hash
from osii.server.config import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def store():
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    if not url.split("?", 1)[0].endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
    store = PostgresStore(url)
    with store.transaction() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "osii/persistence/migrations"))
    config.attributes["database_url"] = url.replace("postgresql://", "postgresql+psycopg://", 1)
    command.upgrade(config, "head")
    yield store
    store.engine.dispose()


class Provider:
    calls = 0

    def catalog(self):
        return [{"id": "vendor/model-id", "name": "Friendly name", "capabilities": ["chat"]}]

    def chat(self, model, messages, max_tokens=900, **kwargs):
        self.calls += 1
        return "The detector uses neutrons.", {"completion_tokens": 7}

    def embed(self, model, texts):
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def app(store, tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    for name, role in (("admin", "admin"), ("reader", "reader"), ("curator", "curator")):
        store.create_account(name, password_hash("sufficiently-long-test-password"), role, bootstrap=name == "admin")
        if name != "admin":
            store.change_account(store.account(username=name)["id"], {"must_change_password": False})
    settings = Settings(str(store.engine.url), source, "https://provider.test/v1", "secret-not-for-clients", "http://extractor.test", ("http://testserver",), False)
    return create_app(settings, store, Provider())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def login(client, username="admin", password="sufficiently-long-test-password"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r.json()["user"]


def document(store, root, *, name="report.txt", content="The neutron detector uses thermal neutrons."):
    from osii.server.worker import ingest_file
    from osii.processor_sdk.models import ExtractionResponse, ProcessorDescriptor, ProcessorKind, TextSegment

    class Extractor:
        def extract(self, request):
            return ExtractionResponse(request_id=request.request_id, processor=ProcessorDescriptor(
                name="test.extractor", version="1", display_name="Test", description="Test", kind=ProcessorKind.EXTRACTOR),
                segments=[TextSegment(id="page-1", text=content, source_origin={"page": 1})])
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    ingest_file(store, Provider(), Extractor(), root, path)
    return next(d for d in store.snapshot()[1] if d["source_relpath"] == name)
