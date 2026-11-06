"""Private user collections; existing collections remain shared."""
from alembic import op
import sqlalchemy as sa

revision = "0002_workspace"
down_revision = "0001_server"


def upgrade():
    op.add_column("collections", sa.Column("owner_id", sa.String(), nullable=True))
    op.add_column("collections", sa.Column("visibility", sa.String(), nullable=False, server_default="shared"))
    op.alter_column("collections", "visibility", server_default="private")
    op.create_foreign_key("collections_owner_fkey", "collections", "users", ["owner_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("collections_name_key", "collections", type_="unique")
    op.create_unique_constraint("collections_owner_name_key", "collections", ["owner_id", "name"])


def downgrade():
    # Explicitly refuse an unsafe rollback that could publish personal work.
    raise RuntimeError("Restore a compatible backup to roll back private collections")
