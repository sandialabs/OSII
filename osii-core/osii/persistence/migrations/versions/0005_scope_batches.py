"""Durable, bounded inputs and results for whole-scope processor runs."""

from alembic import op

revision = "0005_scope_batches"
down_revision = "0004_inventory_tools"


def upgrade():
    op.execute("""CREATE TABLE scope_tool_batches (
      job_id VARCHAR NOT NULL REFERENCES jobs(id), id VARCHAR NOT NULL, ordinal INTEGER NOT NULL,
      phase VARCHAR NOT NULL, level INTEGER NOT NULL DEFAULT 0,
      inputs JSONB NOT NULL, source_ranges JSONB NOT NULL,
      result JSONB, calls JSONB NOT NULL DEFAULT '{}',
      PRIMARY KEY(job_id,id))""")
    op.execute(
        """CREATE TABLE scope_tool_sources (job_id VARCHAR NOT NULL REFERENCES jobs(id), file_id VARCHAR NOT NULL, record JSONB NOT NULL, PRIMARY KEY(job_id,file_id))"""
    )
    op.execute(
        "CREATE INDEX scope_tool_batch_queue ON scope_tool_batches(job_id,phase,level,ordinal)"
    )


def downgrade():
    raise RuntimeError(
        "Frozen scope inputs and results are retained evidence; restore a compatible backup to roll back"
    )
