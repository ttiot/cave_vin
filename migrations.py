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


def _create_alcohol_categories_tables(connection: Connection) -> None:
    """Créer les tables pour les catégories et sous-catégories d'alcool."""
    
    # Table des catégories principales
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alcohol_category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(80) NOT NULL UNIQUE,
                description TEXT,
                display_order INTEGER DEFAULT 0
            )
            """
        )
    )
    
    # Table des sous-catégories
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alcohol_subcategory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(80) NOT NULL,
                category_id INTEGER NOT NULL,
                description TEXT,
                display_order INTEGER DEFAULT 0,
                CONSTRAINT fk_subcategory_category FOREIGN KEY(category_id) REFERENCES alcohol_category(id) ON DELETE CASCADE,
                CONSTRAINT uq_category_subcategory UNIQUE(category_id, name)
            )
            """
        )
    )
    
    # Ajouter la colonne subcategory_id à la table wine
    connection.execute(
        text(
            """
            ALTER TABLE wine ADD COLUMN subcategory_id INTEGER
            REFERENCES alcohol_subcategory(id)
            """
        )
    )


def _populate_default_alcohol_categories(connection: Connection) -> None:
    """Insérer les catégories et sous-catégories par défaut."""
    
    # Vérifier si des catégories existent déjà
    existing = connection.execute(
        text("SELECT COUNT(*) FROM alcohol_category")
    ).scalar()
    
    if existing > 0:
        return  # Ne pas réinsérer si des données existent déjà
    
    # Catégorie Vins
    connection.execute(
        text(
            """
            INSERT INTO alcohol_category (name, description, display_order)
            VALUES ('Vins', 'Vins de toutes origines', 1)
            """
        )
    )
    wine_category_id = connection.execute(text("SELECT last_insert_rowid()")).scalar()
    
    wine_subcategories = [
        ("Vin rouge", "Vins rouges", 1),
        ("Vin blanc", "Vins blancs", 2),
        ("Vin rosé", "Vins rosés", 3),
        ("Champagne", "Champagnes et vins effervescents", 4),
        ("Vin doux", "Vins doux naturels et liquoreux", 5),
    ]
    
    for name, desc, order in wine_subcategories:
        connection.execute(
            text(
                """
                INSERT INTO alcohol_subcategory (name, category_id, description, display_order)
                VALUES (:name, :category_id, :description, :display_order)
                """
            ),
            {
                "name": name,
                "category_id": wine_category_id,
                "description": desc,
                "display_order": order,
            },
        )
    
    # Catégorie Spiritueux
    connection.execute(
        text(
            """
            INSERT INTO alcohol_category (name, description, display_order)
            VALUES ('Spiritueux', 'Alcools distillés', 2)
            """
        )
    )
    spirits_category_id = connection.execute(text("SELECT last_insert_rowid()")).scalar()
    
    spirits_subcategories = [
        ("Rhum blanc", "Rhums blancs agricoles ou traditionnels", 1),
        ("Rhum ambré", "Rhums ambrés vieillis en fût", 2),
        ("Rhum vieux", "Rhums vieux longuement vieillis", 3),
        ("Whisky", "Whiskies écossais, irlandais, américains, etc.", 4),
        ("Cognac", "Cognacs et eaux-de-vie de vin", 5),
        ("Armagnac", "Armagnacs", 6),
        ("Calvados", "Calvados et eaux-de-vie de cidre", 7),
        ("Vodka", "Vodkas", 8),
        ("Gin", "Gins", 9),
        ("Tequila", "Tequilas et mezcals", 10),
        ("Liqueur", "Liqueurs diverses", 11),
    ]
    
    for name, desc, order in spirits_subcategories:
        connection.execute(
            text(
                """
                INSERT INTO alcohol_subcategory (name, category_id, description, display_order)
                VALUES (:name, :category_id, :description, :display_order)
                """
            ),
            {
                "name": name,
                "category_id": spirits_category_id,
                "description": desc,
                "display_order": order,
            },
        )
    
    # Catégorie Bières
    connection.execute(
        text(
            """
            INSERT INTO alcohol_category (name, description, display_order)
            VALUES ('Bières', 'Bières et cidres', 3)
            """
        )
    )
    beer_category_id = connection.execute(text("SELECT last_insert_rowid()")).scalar()
    
    beer_subcategories = [
        ("Bière blonde", "Bières blondes", 1),
        ("Bière ambrée", "Bières ambrées", 2),
        ("Bière brune", "Bières brunes et stouts", 3),
        ("IPA", "India Pale Ales", 4),
        ("Bière blanche", "Bières blanches", 5),
        ("Cidre", "Cidres", 6),
    ]
    
    for name, desc, order in beer_subcategories:
        connection.execute(
            text(
                """
                INSERT INTO alcohol_subcategory (name, category_id, description, display_order)
                VALUES (:name, :category_id, :description, :display_order)
                """
            ),
            {
                "name": name,
                "category_id": beer_category_id,
                "description": desc,
                "display_order": order,
            },
        )


MIGRATIONS: Iterable[Migration] = (
    ("0001_populate_cellar_floors", _migrate_cellar_floors),
    ("0002_create_wine_insight", _create_wine_insight_table),
    ("0003_create_wine_consumption", _create_wine_consumption_table),
    ("0004_create_alcohol_categories", _create_alcohol_categories_tables),
    ("0005_populate_default_categories", _populate_default_alcohol_categories),
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
