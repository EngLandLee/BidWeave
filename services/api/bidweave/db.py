# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed database setup; no warranty.
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def configure_engine(url: str | None = None):
    global _engine, _SessionLocal
    database_url = url or get_settings().database_url
    kwargs = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    _engine = create_engine(database_url, **kwargs)
    _SessionLocal = sessionmaker(_engine, class_=Session, expire_on_commit=False)
    return _engine


def engine():
    global _engine
    if _engine is None:
        configure_engine()
    return _engine


def SessionLocal():
    global _SessionLocal
    if _SessionLocal is None:
        configure_engine()
    return _SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine())
