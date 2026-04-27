"""add tenants roles users

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "subscription_plan",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'free'::character varying"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_tenants_email", "tenants", ["email"], unique=True)
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=False)
    op.create_index("ix_tenants_is_active", "tenants", ["is_active"], unique=False)

    op.create_table(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_users_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_users_role_id_roles",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
    op.create_index("ix_users_role_id", "users", ["role_id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_is_active", "users", ["is_active"], unique=False)
    op.execute("CREATE INDEX ix_users_is_deleted ON users (is_deleted) WHERE is_deleted = false")


def downgrade() -> None:
    op.drop_index("ix_users_is_deleted", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")

    op.drop_table("roles")

    op.drop_index("ix_tenants_is_active", table_name="tenants")
    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_index("ix_tenants_email", table_name="tenants")
    op.drop_table("tenants")
