"""Simple database migration runner executed on application startup."""

from __future__ import annotations

from typing import Callable, Iterable, List, Tuple

import unicodedata

from sqlalchemy import text
from sqlalchemy.engine import Connection

from models import db
from app.field_config import DEFAULT_FIELD_DEFINITIONS


DEFAULT_DISPLAY_ORDERS = {
    field["name"]: int(field.get("display_order", 0))
    for field in DEFAULT_FIELD_DEFINITIONS
}


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
    
    # Vérifier si la colonne subcategory_id existe déjà
    columns = connection.execute(text("PRAGMA table_info(wine)")).fetchall()
    column_names = {row[1] for row in columns}
    
    # Ajouter la colonne subcategory_id à la table wine si elle n'existe pas
    if "subcategory_id" not in column_names:
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


def _add_wine_volume_column(connection: Connection) -> None:
    """Ajouter la colonne volume_ml à la table wine si nécessaire."""

    columns = connection.execute(text("PRAGMA table_info(wine)")).fetchall()
    column_names = {row[1] for row in columns}

    if "volume_ml" not in column_names:
        connection.execute(
            text("ALTER TABLE wine ADD COLUMN volume_ml INTEGER")
        )


def _create_field_requirement_table(connection: Connection) -> None:
    """Créer la table décrivant les champs nécessaires par catégorie."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alcohol_field_requirement (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name VARCHAR(50) NOT NULL,
                category_id INTEGER REFERENCES alcohol_category(id),
                subcategory_id INTEGER REFERENCES alcohol_subcategory(id),
                is_enabled BOOLEAN NOT NULL DEFAULT 1,
                is_required BOOLEAN NOT NULL DEFAULT 0,
                display_order INTEGER NOT NULL DEFAULT 0,
                CONSTRAINT uq_field_scope UNIQUE(field_name, category_id, subcategory_id)
            )
            """
        )
    )


def _populate_default_field_requirements(connection: Connection) -> None:
    """Initialiser la configuration des champs par défaut."""

    def _ensure_requirement(field_name, category_id, subcategory_id, is_enabled, is_required, display_order):
        existing = connection.execute(
            text(
                """
                SELECT 1 FROM alcohol_field_requirement
                WHERE field_name = :field_name
                  AND ((:category_id IS NULL AND category_id IS NULL) OR category_id = :category_id)
                  AND ((:subcategory_id IS NULL AND subcategory_id IS NULL) OR subcategory_id = :subcategory_id)
                LIMIT 1
                """
            ),
            {
                "field_name": field_name,
                "category_id": category_id,
                "subcategory_id": subcategory_id,
            },
        ).first()

        if existing:
            return

        connection.execute(
            text(
                """
                INSERT INTO alcohol_field_requirement
                    (field_name, category_id, subcategory_id, is_enabled, is_required, display_order)
                VALUES (:field_name, :category_id, :subcategory_id, :is_enabled, :is_required, :display_order)
                """
            ),
            {
                "field_name": field_name,
                "category_id": category_id,
                "subcategory_id": subcategory_id,
                "is_enabled": is_enabled,
                "is_required": is_required,
                "display_order": display_order,
            },
        )

    global_defaults = [
        {
            "field_name": "region",
            "category_id": None,
            "subcategory_id": None,
            "is_enabled": True,
            "is_required": False,
        },
        {
            "field_name": "year",
            "category_id": None,
            "subcategory_id": None,
            "is_enabled": True,
            "is_required": False,
        },
        {
            "field_name": "volume_ml",
            "category_id": None,
            "subcategory_id": None,
            "is_enabled": True,
            "is_required": True,
        },
        {
            "field_name": "description",
            "category_id": None,
            "subcategory_id": None,
            "is_enabled": True,
            "is_required": False,
        },
    ]

    for default in global_defaults:
        default["display_order"] = DEFAULT_DISPLAY_ORDERS.get(
            default["field_name"], 0
        )
        _ensure_requirement(**default)

    wine_category_id = connection.execute(
        text("SELECT id FROM alcohol_category WHERE LOWER(name) = 'vins'")
    ).scalar()

    if wine_category_id:
        _ensure_requirement(
            field_name="grape",
            category_id=wine_category_id,
            subcategory_id=None,
            is_enabled=True,
            is_required=False,
            display_order=DEFAULT_DISPLAY_ORDERS.get("grape", 0),
        )


def _create_field_definition_table(connection: Connection) -> None:
    """Create the table storing available dynamic bottle fields."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS bottle_field_definition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                label VARCHAR(120) NOT NULL,
                help_text TEXT,
                placeholder VARCHAR(255),
                input_type VARCHAR(20) NOT NULL DEFAULT 'text',
                form_width INTEGER NOT NULL DEFAULT 12,
                is_builtin BOOLEAN NOT NULL DEFAULT 0,
                display_order INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    )


def _populate_default_field_definitions(connection: Connection) -> None:
    """Seed the default bottle field definitions when missing."""

    for definition in DEFAULT_FIELD_DEFINITIONS:
        name = definition["name"]
        existing = connection.execute(
            text(
                """
                SELECT id FROM bottle_field_definition WHERE name = :name
                """
            ),
            {"name": name},
        ).first()

        if existing:
            continue

        connection.execute(
            text(
                """
                INSERT INTO bottle_field_definition (
                    name,
                    label,
                    help_text,
                    placeholder,
                    input_type,
                    form_width,
                    is_builtin,
                    display_order
                ) VALUES (
                    :name,
                    :label,
                    :help_text,
                    :placeholder,
                    :input_type,
                    :form_width,
                    :is_builtin,
                    :display_order
                )
                """
            ),
            {
                "name": name,
                "label": definition["label"],
                "help_text": definition.get("help_text"),
                "placeholder": definition.get("placeholder"),
                "input_type": definition.get("input_type", "text"),
                "form_width": int(definition.get("form_width", 12)),
                "is_builtin": 1 if definition.get("is_builtin") else 0,
                "display_order": int(definition.get("display_order", 0)),
            },
        )


def _add_wine_extra_attributes(connection: Connection) -> None:
    """Ensure the wine table can store dynamic attributes."""

    columns = connection.execute(text("PRAGMA table_info(wine)")).fetchall()
    column_names = {row[1] for row in columns}

    if "extra_attributes" not in column_names:
        connection.execute(
            text("ALTER TABLE wine ADD COLUMN extra_attributes TEXT")
        )

    connection.execute(
        text(
            """
            UPDATE wine
            SET extra_attributes = '{}'
            WHERE extra_attributes IS NULL
            """
        )
    )


def _link_requirements_to_field_definitions(connection: Connection) -> None:
    """Attach requirement rows to their corresponding field definitions."""

    columns = connection.execute(
        text("PRAGMA table_info(alcohol_field_requirement)")
    ).fetchall()
    column_names = {row[1] for row in columns}

    if "field_id" not in column_names:
        connection.execute(
            text(
                """
                ALTER TABLE alcohol_field_requirement
                ADD COLUMN field_id INTEGER REFERENCES bottle_field_definition(id)
                """
            )
        )

    rows = connection.execute(
        text(
            """
            SELECT id, field_name FROM alcohol_field_requirement
            """
        )
    ).fetchall()

    for requirement_id, field_name in rows:
        field = connection.execute(
            text(
                """
                SELECT id, display_order FROM bottle_field_definition
                WHERE name = :name
                """
            ),
            {"name": field_name},
        ).first()

        if field is None:
            display_order = connection.execute(
                text(
                    "SELECT COALESCE(MAX(display_order), 0) + 10 FROM bottle_field_definition"
                )
            ).scalar()
            connection.execute(
                text(
                    """
                    INSERT INTO bottle_field_definition (
                        name, label, input_type, form_width, is_builtin, display_order
                    ) VALUES (
                        :name, :label, 'text', 12, 0, :display_order
                    )
                    """
                ),
                {
                    "name": field_name,
                    "label": field_name.replace('_', ' ').title(),
                    "display_order": display_order or 0,
                },
            )
            field = connection.execute(
                text(
                    """
                    SELECT id, display_order FROM bottle_field_definition
                    WHERE name = :name
                    """
                ),
                {"name": field_name},
            ).first()

        field_id, display_order = field
        connection.execute(
            text(
                """
                UPDATE alcohol_field_requirement
                SET field_id = :field_id,
                    display_order = :display_order
                WHERE id = :requirement_id
                """
            ),
            {
                "field_id": field_id,
                "display_order": display_order,
                "requirement_id": requirement_id,
            },
        )


def _add_wine_timestamps(connection: Connection) -> None:
    """Ajouter created_at et updated_at à la table wine si nécessaire."""

    existing_columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(wine)"))
    }

    if "created_at" not in existing_columns:
        connection.execute(text("ALTER TABLE wine ADD COLUMN created_at DATETIME"))
        connection.execute(
            text("UPDATE wine SET created_at = datetime('now') WHERE created_at IS NULL")
        )

    if "updated_at" not in existing_columns:
        connection.execute(text("ALTER TABLE wine ADD COLUMN updated_at DATETIME"))
        connection.execute(
            text(
                "UPDATE wine SET updated_at = datetime('now') WHERE updated_at IS NULL"
            )
        )


def _add_wine_label_image(connection: Connection) -> None:
    """Ajouter la colonne label_image_data si elle est absente."""

    existing_columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(wine)"))
    }

    if "label_image_data" in existing_columns:
        return

    connection.execute(text("ALTER TABLE wine ADD COLUMN label_image_data TEXT"))


def _add_user_admin_column(connection: Connection) -> None:
    """Ajouter la colonne is_admin à la table user et promouvoir l'admin par défaut."""

    existing_columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(user)"))
    }

    if "is_admin" in existing_columns:
        return

    connection.execute(
        text("ALTER TABLE user ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
    )
    connection.execute(
        text("UPDATE user SET is_admin = 1 WHERE username = 'admin'")
    )


def _add_cellar_user_column(connection: Connection) -> None:
    """Associer les caves à un utilisateur propriétaire."""

    existing_columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(cellar)"))
    }

    if "user_id" not in existing_columns:
        connection.execute(
            text(
                "ALTER TABLE cellar ADD COLUMN user_id INTEGER REFERENCES user(id)"
            )
        )

    connection.execute(
        text(
            """
            UPDATE cellar
            SET user_id = (
                SELECT id FROM user WHERE username = 'admin' ORDER BY id LIMIT 1
            )
            WHERE user_id IS NULL
            """
        )
    )


def _add_wine_user_column(connection: Connection) -> None:
    """Ajouter la colonne user_id à la table wine et synchroniser les valeurs."""

    existing_columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(wine)"))
    }

    if "user_id" not in existing_columns:
        connection.execute(
            text(
                "ALTER TABLE wine ADD COLUMN user_id INTEGER REFERENCES user(id)"
            )
        )

    connection.execute(
        text(
            """
            UPDATE wine
            SET user_id = (
                SELECT user_id FROM cellar WHERE cellar.id = wine.cellar_id
            )
            WHERE user_id IS NULL
            """
        )
    )

    connection.execute(
        text(
            """
            UPDATE wine
            SET user_id = (
                SELECT id FROM user WHERE username = 'admin' ORDER BY id LIMIT 1
            )
            WHERE user_id IS NULL
            """
        )
    )


def _add_consumption_user_column(connection: Connection) -> None:
    """Ajouter la colonne user_id à la table wine_consumption."""

    existing_columns = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(wine_consumption)"))
    }

    if "user_id" not in existing_columns:
        connection.execute(
            text(
                "ALTER TABLE wine_consumption ADD COLUMN user_id INTEGER REFERENCES user(id)"
            )
        )

    connection.execute(
        text(
            """
            UPDATE wine_consumption
            SET user_id = (
                SELECT user_id FROM wine WHERE wine.id = wine_consumption.wine_id
            )
            WHERE user_id IS NULL
            """
        )
    )

    connection.execute(
        text(
            """
            UPDATE wine_consumption
            SET user_id = (
                SELECT id FROM user WHERE username = 'admin' ORDER BY id LIMIT 1
            )
            WHERE user_id IS NULL
            """
        )
    )


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
    ("0010_add_wine_volume_column", _add_wine_volume_column),
    ("0011_create_field_requirement_table", _create_field_requirement_table),
    ("0012_populate_field_requirements", _populate_default_field_requirements),
    ("0013_create_field_definition_table", _create_field_definition_table),
    ("0014_populate_field_definitions", _populate_default_field_definitions),
    ("0015_add_wine_extra_attributes", _add_wine_extra_attributes),
    ("0016_link_field_requirements", _link_requirements_to_field_definitions),
    ("0017_add_wine_timestamps", _add_wine_timestamps),
    ("0018_add_wine_label_image", _add_wine_label_image),
    ("0019_add_user_admin_column", _add_user_admin_column),
    ("0020_add_cellar_user_column", _add_cellar_user_column),
    ("0021_add_wine_user_column", _add_wine_user_column),
    ("0022_add_consumption_user_column", _add_consumption_user_column),
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
