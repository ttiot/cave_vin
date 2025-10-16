"""Simple database migration runner executed on application startup."""

from __future__ import annotations

from typing import Callable, Iterable, List, Tuple

import unicodedata

from sqlalchemy import text
from sqlalchemy.engine import Connection

from models import db


Migration = Tuple[str, Callable[[Connection], None]]

DEFAULT_BADGE_BG_COLOR = "#6366f1"
DEFAULT_BADGE_TEXT_COLOR = "#ffffff"


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


def _add_subcategory_colors(connection: Connection) -> None:
    """Ajouter les colonnes de couleurs et migrer les valeurs existantes."""

    # Vérifier si les colonnes existent déjà
    table_info = connection.execute(
        text("PRAGMA table_info(alcohol_subcategory)")
    ).fetchall()
    
    existing_columns = {row[1] for row in table_info}
    
    # Ajouter badge_bg_color seulement si elle n'existe pas
    if "badge_bg_color" not in existing_columns:
        connection.execute(
            text(
                f"""
                ALTER TABLE alcohol_subcategory
                ADD COLUMN badge_bg_color VARCHAR(20) DEFAULT '{DEFAULT_BADGE_BG_COLOR}'
                """
            )
        )

    # Ajouter badge_text_color seulement si elle n'existe pas
    if "badge_text_color" not in existing_columns:
        connection.execute(
            text(
                f"""
                ALTER TABLE alcohol_subcategory
                ADD COLUMN badge_text_color VARCHAR(20) DEFAULT '{DEFAULT_BADGE_TEXT_COLOR}'
                """
            )
        )

    rows = connection.execute(
        text(
            """
            SELECT id, name FROM alcohol_subcategory
            """
        )
    ).fetchall()

    color_map = {
        # Vins
        "vin rouge": ("#7f1d1d", "#ffffff"),
        "red wine": ("#7f1d1d", "#ffffff"),
        "rouge": ("#7f1d1d", "#ffffff"),
        "vin blanc": ("#fef3c7", "#78350f"),
        "white wine": ("#fef3c7", "#78350f"),
        "blanc": ("#fef3c7", "#78350f"),
        "vin rose": ("#fce7f3", "#9f1239"),
        "rose wine": ("#fce7f3", "#9f1239"),
        "rose": ("#fce7f3", "#9f1239"),
        "vin orange": ("#fed7aa", "#7c2d12"),
        "orange wine": ("#fed7aa", "#7c2d12"),
        "orange": ("#fed7aa", "#7c2d12"),

        # Effervescents
        "champagne": ("#fef08a", "#713f12"),
        "cremant": ("#fef3c7", "#78350f"),
        "crémant": ("#fef3c7", "#78350f"),
        "prosecco": ("#fef3c7", "#78350f"),
        "cava": ("#fef3c7", "#78350f"),
        "mousseux": ("#fef3c7", "#78350f"),

        # Whiskies
        "whisky": ("#92400e", "#ffffff"),
        "scotch": ("#92400e", "#ffffff"),
        "bourbon": ("#b45309", "#ffffff"),
        "irish whiskey": ("#a16207", "#ffffff"),

        # Rhums
        "rhum blanc": ("#f5f5f4", "#44403c"),
        "rhum ambre": ("#d97706", "#ffffff"),
        "rhum ambré": ("#d97706", "#ffffff"),
        "rhum vieux": ("#78350f", "#ffffff"),
        "rhum": ("#78350f", "#ffffff"),

        # Spiritueux
        "cognac": ("#92400e", "#ffffff"),
        "armagnac": ("#92400e", "#ffffff"),
        "vodka": ("#e5e7eb", "#1f2937"),
        "gin": ("#dbeafe", "#1e3a8a"),
        "tequila": ("#fef3c7", "#78350f"),
        "mezcal": ("#d1d5db", "#1f2937"),

        # Bières
        "biere blonde": ("#fbbf24", "#78350f"),
        "bière blonde": ("#fbbf24", "#78350f"),
        "blonde": ("#fbbf24", "#78350f"),
        "biere brune": ("#78350f", "#ffffff"),
        "bière brune": ("#78350f", "#ffffff"),
        "brune": ("#78350f", "#ffffff"),
        "biere blanche": ("#fef3c7", "#78350f"),
        "bière blanche": ("#fef3c7", "#78350f"),
        "blanche": ("#fef3c7", "#78350f"),
        "biere ambree": ("#d97706", "#ffffff"),
        "bière ambrée": ("#d97706", "#ffffff"),
        "ambree": ("#d97706", "#ffffff"),
        "ipa": ("#f59e0b", "#ffffff"),
        "stout": ("#1c1917", "#ffffff"),
        "porter": ("#292524", "#ffffff"),

        # Liqueurs & apéritifs
        "liqueur": ("#ec4899", "#ffffff"),
        "creme": ("#fce7f3", "#9f1239"),
        "crème": ("#fce7f3", "#9f1239"),
        "aperitif": ("#10b981", "#ffffff"),
        "apéritif": ("#10b981", "#ffffff"),
        "vermouth": ("#dc2626", "#ffffff"),
        "pastis": ("#fef3c7", "#78350f"),
        "porto": ("#7f1d1d", "#ffffff"),

        # Autres
        "sake": ("#e0e7ff", "#3730a3"),
        "saké": ("#e0e7ff", "#3730a3"),
        "cidre": ("#fca5a5", "#7f1d1d"),
        "cider": ("#fca5a5", "#7f1d1d"),
    }

    for subcategory_id, name in rows:
        normalized = ''.join(
            c for c in unicodedata.normalize('NFD', name.lower())
            if unicodedata.category(c) != 'Mn'
        )

        colors = color_map.get(normalized)
        if not colors:
            for key, value in color_map.items():
                if key in normalized:
                    colors = value
                    break

        if not colors:
            continue

        bg_color, text_color = colors
        connection.execute(
            text(
                """
                UPDATE alcohol_subcategory
                SET badge_bg_color = :bg, badge_text_color = :text
                WHERE id = :id
                """
            ),
            {"bg": bg_color, "text": text_color, "id": subcategory_id},
        )


def _create_cellar_category_table(connection: Connection) -> None:
    """Créer la table pour les catégories de cave."""
    
    # Table des catégories de cave
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS cellar_category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(80) NOT NULL UNIQUE,
                description TEXT,
                display_order INTEGER DEFAULT 0
            )
            """
        )
    )
    
    # Ajouter la colonne category_id à la table cellar
    connection.execute(
        text(
            """
            ALTER TABLE cellar ADD COLUMN category_id INTEGER
            REFERENCES cellar_category(id)
            """
        )
    )


def _populate_default_cellar_categories(connection: Connection) -> None:
    """Insérer les catégories de cave par défaut."""
    
    # Vérifier si des catégories existent déjà
    existing = connection.execute(
        text("SELECT COUNT(*) FROM cellar_category")
    ).scalar()
    
    if existing > 0:
        return  # Ne pas réinsérer si des données existent déjà
    
    default_categories = [
        ("Cave naturelle", "Cave naturelle traditionnelle", 1),
        ("Cave électrique", "Cave électrique de conservation", 2),
        ("Cave de vieillissement", "Cave dédiée au vieillissement des vins", 3),
        ("Cave d'appoint", "Cave d'appoint ou de service", 4),
    ]
    
    for name, desc, order in default_categories:
        connection.execute(
            text(
                """
                INSERT INTO cellar_category (name, description, display_order)
                VALUES (:name, :description, :display_order)
                """
            ),
            {
                "name": name,
                "description": desc,
                "display_order": order,
            },
        )


def _migrate_cellar_type_to_category(connection: Connection) -> None:
    """Convertir les types de cave existants en catégories."""
    
    # Récupérer les IDs des catégories
    naturelle_id = connection.execute(
        text("SELECT id FROM cellar_category WHERE name = 'Cave naturelle'")
    ).scalar()
    
    electrique_id = connection.execute(
        text("SELECT id FROM cellar_category WHERE name = 'Cave électrique'")
    ).scalar()
    
    if not naturelle_id or not electrique_id:
        return  # Les catégories n'existent pas encore
    
    # Mettre à jour les caves existantes avec cellar_type
    connection.execute(
        text(
            """
            UPDATE cellar
            SET category_id = :naturelle_id
            WHERE cellar_type = 'naturelle' AND category_id IS NULL
            """
        ),
        {"naturelle_id": naturelle_id},
    )
    
    connection.execute(
        text(
            """
            UPDATE cellar
            SET category_id = :electrique_id
            WHERE cellar_type = 'electrique' AND category_id IS NULL
            """
        ),
        {"electrique_id": electrique_id},
    )
    
    # Supprimer la colonne cellar_type (SQLite ne supporte pas DROP COLUMN directement)
    # On doit recréer la table sans cette colonne
    connection.execute(
        text(
            """
            CREATE TABLE cellar_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL,
                floors INTEGER NOT NULL,
                bottles_per_floor INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                FOREIGN KEY(category_id) REFERENCES cellar_category(id)
            )
            """
        )
    )
    
    connection.execute(
        text(
            """
            INSERT INTO cellar_new (id, name, floors, bottles_per_floor, category_id)
            SELECT id, name, floors, bottles_per_floor, category_id
            FROM cellar
            """
        )
    )
    
    connection.execute(text("DROP TABLE cellar"))
    connection.execute(text("ALTER TABLE cellar_new RENAME TO cellar"))


MIGRATIONS: Iterable[Migration] = (
    ("0001_populate_cellar_floors", _migrate_cellar_floors),
    ("0002_create_wine_insight", _create_wine_insight_table),
    ("0003_create_wine_consumption", _create_wine_consumption_table),
    ("0004_create_alcohol_categories", _create_alcohol_categories_tables),
    ("0005_populate_default_categories", _populate_default_alcohol_categories),
    ("0006_add_subcategory_colors", _add_subcategory_colors),
    ("0007_create_cellar_categories", _create_cellar_category_table),
    ("0008_populate_default_cellar_categories", _populate_default_cellar_categories),
    ("0009_migrate_cellar_type_to_category", _migrate_cellar_type_to_category),
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
