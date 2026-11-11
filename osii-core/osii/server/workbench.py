"""Hosted home counts and configuration flags; no corpus/vector materialization."""

from sqlalchemy import text, select
from sqlalchemy.dialects.postgresql import insert as upsert
from osii.persistence.postgres import datasets, settings as settings_table
from osii.domain.workbench import home_state
from osii.server.model_connections import ModelConnections


def hosted_home(store, settings, actor):
    counts = store.statistics(use_cache=True)
    config = store.configuration()
    model = config.get("embedding_model", "")
    index_ready = _index_ready(store, model)
    endpoint = ModelConnections(store, settings).endpoints()["chat"]
    return home_state(
        documents=counts["documents"],
        text_documents=counts["text_documents"],
        indexed_documents=counts["indexed_documents"] if index_ready else 0,
        index_ready=index_ready,
        chat_configured=bool(config.get("chat_model") and endpoint.base_url),
        setup_dismissed=store.setting("home_setup", {}).get("dismissed") is True,
        can_setup=actor["role"] == "admin",
    )


def _index_ready(store, model):
    """Coalesce metadata checks; invalidate with canonical corpus/model changes."""
    if not model:
        return False
    with store.transaction() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('osii:home-index-shape'))")
        )
        revision = connection.execute(
            select(datasets.c.revision).where(datasets.c.id == "shared")
        ).scalar_one()
        identity = ["home-index-v1", revision, model]
        cached = (
            connection.execute(
                select(settings_table.c.value).where(
                    settings_table.c.id == "home_index_shape"
                )
            ).scalar()
            or {}
        )
        if cached.get("identity") == identity and type(cached.get("ready")) is bool:
            return cached["ready"]
        shape = connection.execute(
            text("""SELECT min(dimension), max(dimension)
            FROM (SELECT CASE WHEN jsonb_typeof(c.embedding)='array'
                THEN jsonb_array_length(c.embedding) ELSE 0 END AS dimension
            FROM chunks c JOIN documents d ON d.file_id=c.file_id
            WHERE d.active AND c.embedding_model=:model) vectors"""),
            {"model": model},
        ).one()
        ready = bool(shape[0] and 1 <= shape[0] == shape[1] <= 8192)
        value = {"identity": identity, "ready": ready}
        statement = upsert(settings_table).values(id="home_index_shape", value=value)
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=[settings_table.c.id], set_={"value": value}
            )
        )
        return ready
