"""baseline legacy schema

Revision ID: 0001_baseline_existing
Revises:
Create Date: 2026-08-17

Production was stamped at this revision because these legacy tables already
existed before Alembic was introduced.

For a fresh database, this revision creates the legacy schema so the complete
migration chain can be replayed from an empty database.
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline_existing"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("wifi_ssid", sa.String(length=128), nullable=True),
        sa.Column("wifi_password", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_devices_device_id",
        "devices",
        ["device_id"],
        unique=True,
    )

    op.create_table(
        "job_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cleaned_rows", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_records_device_id",
        "job_records",
        ["device_id"],
        unique=False,
    )

    op.create_table(
        "firmware_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_model", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("download_url", sa.String(length=512), nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_firmware_meta_device_model",
        "firmware_meta",
        ["device_model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_firmware_meta_device_model",
        table_name="firmware_meta",
    )
    op.drop_table("firmware_meta")

    op.drop_index(
        "ix_job_records_device_id",
        table_name="job_records",
    )
    op.drop_table("job_records")

    op.drop_index(
        "ix_devices_device_id",
        table_name="devices",
    )
    op.drop_table("devices")

    op.drop_index(
        "ix_users_email",
        table_name="users",
    )
    op.drop_table("users")
