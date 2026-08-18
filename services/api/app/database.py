"""Shared SQLAlchemy database primitives."""

from __future__ import annotations

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def build_database_url() -> str | URL:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "vgsolar"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "vgsolar"),
    )


engine = create_engine(build_database_url(), pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
