"""app platform v1 schema

Revision ID: 0002_app_platform_v1
Revises: 0001_baseline_existing
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_app_platform_v1"
down_revision = "0001_baseline_existing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # devices
    # ------------------------------------------------------------------
    op.add_column(
        "devices",
        sa.Column("product_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Known current product identity.
    op.execute(
        """
        UPDATE devices
        SET product_type = 'crawler'
        WHERE device_id LIKE 'crawler_%'
          AND product_type IS NULL
        """
    )

    # Legacy development devices remain intact and explicitly marked.
    op.execute(
        """
        UPDATE devices
        SET product_type = 'legacy'
        WHERE product_type IS NULL
        """
    )

    # ------------------------------------------------------------------
    # user_device_bindings
    # ------------------------------------------------------------------
    op.create_table(
        "user_device_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "device_id",
            name="uq_user_device_bindings_user_device",
        ),
    )

    op.create_index(
        "ix_user_device_bindings_user_id",
        "user_device_bindings",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_user_device_bindings_device_id",
        "user_device_bindings",
        ["device_id"],
        unique=False,
    )

    # Preserve every existing owner relationship as an admin binding.
    op.execute(
        """
        INSERT INTO user_device_bindings
            (user_id, device_id, role, created_at)
        SELECT
            owner_user_id,
            id,
            'admin',
            CURRENT_TIMESTAMP
        FROM devices
        ON CONFLICT (user_id, device_id) DO NOTHING
        """
    )

    # ------------------------------------------------------------------
    # sessions
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "refresh_token_hash",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_sessions_user_id",
        "sessions",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_sessions_status",
        "sessions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index(
        "ix_user_device_bindings_device_id",
        table_name="user_device_bindings",
    )
    op.drop_index(
        "ix_user_device_bindings_user_id",
        table_name="user_device_bindings",
    )
    op.drop_table("user_device_bindings")

    op.drop_column("devices", "updated_at")
    op.drop_column("devices", "created_at")
    op.drop_column("devices", "status")
    op.drop_column("devices", "product_type")

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "status")
    op.drop_column("users", "display_name")
