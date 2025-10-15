"""Simple database migration runner executed on application startup."""

from __future__ import annotations

from typing import Callable, Iterable, List, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

from models import db


Migration = Tuple[str, Callable[[Connection], None]]


def _ensure_migration_table(connection: Connection) -> None:
    """Create the schema_migrations bookkeeping table when missing."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY
            )
            """
        )
    )


def _fetch_applied_versions(connection: Connection) -> List[str]:
    result = connection.execute(text("SELECT version FROM schema_migrations"))
    return [row[0] for row in result]


def _mark_version_applied(connection: Connection, version: str) -> None:
    connection.execute(
        text("INSERT INTO schema_migrations (version) VALUES (:version)"),
        {"version": version},
    )


def _migrate_cellar_floors(connection: Connection) -> None:
    """Populate cellar_floor table for existing cellars when missing."""

    cellars = connection.execute(
        text(
            """
            SELECT id, floors, bottles_per_floor
            FROM cellar
            ORDER BY id
            """
        )
    ).fetchall()

    for cellar_id, floor_count, bottles_per_floor in cellars:
        if not floor_count or not bottles_per_floor:
            continue

        for level in range(1, floor_count + 1):
            existing = connection.execute(
                text(
                    """
                    SELECT 1 FROM cellar_floor
                    WHERE cellar_id = :cellar_id AND level = :level
                    """
                ),
                {"cellar_id": cellar_id, "level": level},
            ).first()

            if existing:
                continue

            connection.execute(
                text(
                    """
                    INSERT INTO cellar_floor (cellar_id, level, capacity)
                    VALUES (:cellar_id, :level, :capacity)
                    """
                ),
                {
                    "cellar_id": cellar_id,
                    "level": level,
                    "capacity": bottles_per_floor,
                },
            )


MIGRATIONS: Iterable[Migration] = (
    ("0001_populate_cellar_floors", _migrate_cellar_floors),
)


def run_migrations(app) -> None:
    """Execute any pending migrations. Safe to run multiple times."""

    with app.app_context():
        engine = db.engine

        with engine.begin() as connection:
            _ensure_migration_table(connection)

        with engine.connect() as connection:
            applied_versions = set(_fetch_applied_versions(connection))

        for version, migration in MIGRATIONS:
            if version in applied_versions:
                continue

            with engine.begin() as connection:
                migration(connection)
                _mark_version_applied(connection, version)
