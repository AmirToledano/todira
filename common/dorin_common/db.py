"""Engine/session setup. Reads DATABASE_URL from the environment lazily, so importing this
module never fails just because the env var isn't set yet (e.g. Alembic's env.py sets it up
itself before ever needing get_session())."""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Session:
    """Return a new Session. Use as a context manager (`with get_session() as session:`)."""
    return _session_factory()()
