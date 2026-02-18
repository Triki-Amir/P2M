from logging.config import fileConfig
import sys
from os.path import abspath, dirname

# Add the project root (c:\P2M) to sys.path so the 'app' package is importable
sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))

from app.database import Base
from app.models import Document  # Import models to register them with Base
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import re

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


def process_revision_directives(context, revision, directives):
    """Generate sequential revision IDs: 0001, 0002, 0003, ..."""
    if not directives:
        return

    # Get the versions directory
    migration_script = directives[0]
    versions_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "versions"
    )

    # Find the highest existing revision number
    max_rev = 0
    if os.path.isdir(versions_dir):
        for fname in os.listdir(versions_dir):
            match = re.match(r"^(\d+)_", fname)
            if match:
                max_rev = max(max_rev, int(match.group(1)))

    # Assign next sequential revision ID
    migration_script.rev_id = f"{max_rev + 1:04d}"

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
