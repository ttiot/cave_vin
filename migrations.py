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


def _create_wine_insight_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS wine_insight (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wine_id INTEGER NOT NULL,
                category VARCHAR(50),
                title VARCHAR(200),
                content TEXT NOT NULL,
                source_name VARCHAR(120),
                source_url VARCHAR(255),
                weight INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT fk_wine_insight_wine FOREIGN KEY(wine_id) REFERENCES wine(id) ON DELETE CASCADE
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_wine_insight_wine_id
            ON wine_insight (wine_id)
            """
        )
    )


def _create_wine_consumption_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS wine_consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wine_id INTEGER NOT NULL,
                consumed_at DATETIME NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                snapshot_name VARCHAR(120) NOT NULL,
                snapshot_year INTEGER,
                snapshot_region VARCHAR(120),
                snapshot_grape VARCHAR(80),
                snapshot_cellar VARCHAR(120),
                CONSTRAINT fk_wine_consumption_wine FOREIGN KEY(wine_id) REFERENCES wine(id) ON DELETE CASCADE
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_wine_consumption_wine_id
            ON wine_consumption (wine_id)
            """
        )
    )


MIGRATIONS: Iterable[Migration] = (
    ("0001_populate_cellar_floors", _migrate_cellar_floors),
    ("0002_create_wine_insight", _create_wine_insight_table),
    ("0003_create_wine_consumption", _create_wine_consumption_table),
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
