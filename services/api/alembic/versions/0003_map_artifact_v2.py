"""map artifact v2 schema

Revision ID: 0003_map_artifact_v2
Revises: 0002_app_platform_v1
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_map_artifact_v2"
down_revision = "0002_app_platform_v1"
branch_labels = None
depends_on = None


UINT32_MAX = 4294967295


def upgrade() -> None:
    # ------------------------------------------------------------------
    # map_artifacts
    # ------------------------------------------------------------------
    op.create_table(
        "map_artifacts",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "product_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "map_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "map_version",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "map_name",
            sa.String(length=256),
            nullable=True,
        ),
        sa.Column(
            "checksum",
            sa.String(length=71),
            nullable=False,
        ),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "storage_key",
            sa.String(length=1024),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            f"map_id >= 0 AND map_id <= {UINT32_MAX}",
            name="ck_map_artifacts_map_id_uint32",
        ),
        sa.CheckConstraint(
            f"map_version >= 0 AND map_version <= {UINT32_MAX}",
            name="ck_map_artifacts_map_version_uint32",
        ),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_map_artifacts_file_size_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_type",
            "device_id",
            "map_id",
            "map_version",
            name="uq_map_artifacts_identity",
        ),
    )

    op.create_index(
        "ix_map_artifacts_device",
        "map_artifacts",
        ["product_type", "device_id"],
        unique=False,
    )

    op.create_index(
        "ix_map_artifacts_status",
        "map_artifacts",
        ["status"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # device_active_maps
    # ------------------------------------------------------------------
    op.create_table(
        "device_active_maps",
        sa.Column(
            "product_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "active_revision",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "activation_request_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_reported_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "active_revision >= 1",
            name="ck_device_active_maps_revision_positive",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["map_artifacts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "product_type",
            "device_id",
        ),
    )

    op.create_index(
        "ix_device_active_maps_artifact_id",
        "device_active_maps",
        ["artifact_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # map_activation_requests
    # ------------------------------------------------------------------
    op.create_table(
        "map_activation_requests",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "product_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "map_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "map_version",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "checksum",
            sa.String(length=71),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "active_revision",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            f"map_id >= 0 AND map_id <= {UINT32_MAX}",
            name="ck_map_activation_requests_map_id_uint32",
        ),
        sa.CheckConstraint(
            f"map_version >= 0 AND map_version <= {UINT32_MAX}",
            name="ck_map_activation_requests_map_version_uint32",
        ),
        sa.CheckConstraint(
            "active_revision >= 1",
            name="ck_map_activation_requests_revision_positive",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_type",
            "device_id",
            "request_id",
            name="uq_map_activation_requests_idempotency",
        ),
    )

    op.create_index(
        "ix_map_activation_requests_device",
        "map_activation_requests",
        ["product_type", "device_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_map_activation_requests_device",
        table_name="map_activation_requests",
    )
    op.drop_table("map_activation_requests")

    op.drop_index(
        "ix_device_active_maps_artifact_id",
        table_name="device_active_maps",
    )
    op.drop_table("device_active_maps")

    op.drop_index(
        "ix_map_artifacts_status",
        table_name="map_artifacts",
    )
    op.drop_index(
        "ix_map_artifacts_device",
        table_name="map_artifacts",
    )
    op.drop_table("map_artifacts")
