"""Hosted home counts and configuration flags; no corpus/vector materialization."""

from sqlalchemy import text
from osii.domain.workbench import home_state
from osii.server.model_connections import ModelConnections


def hosted_home(store, settings, actor):
    counts = store.statistics(use_cache=True)
    config = store.configuration()
    model = config.get("embedding_model", "")
    with store.engine.connect() as connection:
        shape = connection.execute(
            text("""SELECT min(dimension), max(dimension)
            FROM (SELECT CASE WHEN jsonb_typeof(c.embedding)='array'
                THEN jsonb_array_length(c.embedding) ELSE 0 END AS dimension
            FROM chunks c JOIN documents d ON d.file_id=c.file_id
            WHERE d.active AND c.embedding_model=:model) vectors"""),
            {"model": model},
        ).one()
    index_ready = bool(model and shape[0] and 1 <= shape[0] == shape[1] <= 8192)
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
