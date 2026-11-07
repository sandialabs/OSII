"""Persist explicit per-session idle policies without changing existing sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0003_session_policy"
down_revision = "0002_workspace"


def upgrade():
    op.add_column("sessions", sa.Column("idle_seconds", sa.Integer(), nullable=False, server_default="1800"))


def downgrade():
    op.drop_column("sessions", "idle_seconds")
