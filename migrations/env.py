from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# todira_common lives as a sibling directory to migrations/ both when run locally from the repo
# root (todira/common/todira_common) and inside the bot container (/app/todira_common,
# /app/migrations) — insert the parent dir so `import todira_common` resolves in both cases.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
sys.path.insert(0, os.path.dirname(__file__) + "/..")

from todira_common.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 2026-10-09: an ALTER TABLE (even ADD COLUMN) needs an ACCESS EXCLUSIVE lock, and it queues behind a long-running scraper
    # transaction — while it waits, EVERY new query on that table (website, bot) queues behind IT, so the site hung for minutes
    # during the migration deploy that landed in the middle of a scraper run (the helm pre-upgrade hook then timed out). A short
    # lock_timeout makes the attempt fail fast and release the queue; the migrations Job's own retry loop (30 attempts, 5 s apart)
    # tries again once the scraper's transaction is gone.
    connect_args = {"options": "-c lock_timeout=8000"} if database_url.startswith("postgresql") else {}
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
