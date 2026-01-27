"""Database bootstrap helpers for a fresh installation."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import func, inspect, text

from models import (
    AlcoholCategory,
    AlcoholFieldRequirement,
    AlcoholSubcategory,
    BottleFieldDefinition,
    CellarCategory,
    db,
)
from app.field_config import DEFAULT_FIELD_DEFINITIONS

DEFAULT_DISPLAY_ORDERS = {
    field["name"]: int(field.get("display_order", 0))
    for field in DEFAULT_FIELD_DEFINITIONS
}


def apply_schema_updates() -> None:
    """Apply idempotent schema tweaks required by recent releases."""

    engine = db.engine
    inspector = inspect(engine)

    # Migration: Add comment column to wine_consumption table
    if "wine_consumption" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("wine_consumption")}
        if "comment" not in columns:
            # Older installations miss the ``comment`` column that now backs optional
            # tasting notes. Add it on the fly to avoid breaking the application at
            # startup when the ORM issues SELECT statements.
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE wine_consumption ADD COLUMN comment TEXT"))

    # Migration: Add default_cellar_id column to user table
    if "user" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("user")}
        if "default_cellar_id" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE user ADD COLUMN default_cellar_id INTEGER REFERENCES cellar(id) ON DELETE SET NULL"))


ALCOHOL_CATEGORIES: list[dict[str, object]] = [
    {
        "name": "Vins",
        "description": "Vins de toutes origines",
        "display_order": 1,
        "subcategories": (
            {
                "name": "Vin rouge",
                "description": "Vins rouges",
                "display_order": 1,
                "badge_bg_color": "#7f1d1d",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Vin blanc",
                "description": "Vins blancs",
                "display_order": 2,
                "badge_bg_color": "#fef3c7",
                "badge_text_color": "#78350f",
            },
            {
                "name": "Vin rosé",
                "description": "Vins rosés",
                "display_order": 3,
                "badge_bg_color": "#fce7f3",
                "badge_text_color": "#9f1239",
            },
            {
                "name": "Champagne",
                "description": "Champagnes et vins effervescents",
                "display_order": 4,
                "badge_bg_color": "#fef08a",
                "badge_text_color": "#713f12",
            },
            {
                "name": "Vin doux",
                "description": "Vins doux naturels et liquoreux",
                "display_order": 5,
                "badge_bg_color": "#fde68a",
                "badge_text_color": "#92400e",
            },
        ),
    },
    {
        "name": "Spiritueux",
        "description": "Alcools distillés",
        "display_order": 2,
        "subcategories": (
            {
                "name": "Rhum blanc",
                "description": "Rhums blancs agricoles ou traditionnels",
                "display_order": 1,
                "badge_bg_color": "#f5f5f4",
                "badge_text_color": "#44403c",
            },
            {
                "name": "Rhum ambré",
                "description": "Rhums ambrés vieillis en fût",
                "display_order": 2,
                "badge_bg_color": "#d97706",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Rhum vieux",
                "description": "Rhums vieux longuement vieillis",
                "display_order": 3,
                "badge_bg_color": "#78350f",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Whisky",
                "description": "Whiskies écossais, irlandais, américains, etc.",
                "display_order": 4,
                "badge_bg_color": "#92400e",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Cognac",
                "description": "Cognacs et eaux-de-vie de vin",
                "display_order": 5,
                "badge_bg_color": "#92400e",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Armagnac",
                "description": "Armagnacs",
                "display_order": 6,
                "badge_bg_color": "#92400e",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Calvados",
                "description": "Calvados et eaux-de-vie de cidre",
                "display_order": 7,
                "badge_bg_color": "#f97316",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Vodka",
                "description": "Vodkas",
                "display_order": 8,
                "badge_bg_color": "#e5e7eb",
                "badge_text_color": "#1f2937",
            },
            {
                "name": "Gin",
                "description": "Gins",
                "display_order": 9,
                "badge_bg_color": "#dbeafe",
                "badge_text_color": "#1e3a8a",
            },
            {
                "name": "Tequila",
                "description": "Tequilas et mezcals",
                "display_order": 10,
                "badge_bg_color": "#fef3c7",
                "badge_text_color": "#78350f",
            },
            {
                "name": "Liqueur",
                "description": "Liqueurs diverses",
                "display_order": 11,
                "badge_bg_color": "#fbcfe8",
                "badge_text_color": "#831843",
            },
        ),
    },
    {
        "name": "Bières",
        "description": "Bières et cidres",
        "display_order": 3,
        "subcategories": (
            {
                "name": "Bière blonde",
                "description": "Bières blondes",
                "display_order": 1,
                "badge_bg_color": "#fbbf24",
                "badge_text_color": "#78350f",
            },
            {
                "name": "Bière ambrée",
                "description": "Bières ambrées",
                "display_order": 2,
                "badge_bg_color": "#fb923c",
                "badge_text_color": "#7c2d12",
            },
            {
                "name": "Bière brune",
                "description": "Bières brunes et stouts",
                "display_order": 3,
                "badge_bg_color": "#78350f",
                "badge_text_color": "#fef3c7",
            },
            {
                "name": "IPA",
                "description": "India Pale Ales",
                "display_order": 4,
                "badge_bg_color": "#f97316",
                "badge_text_color": "#ffffff",
            },
            {
                "name": "Bière blanche",
                "description": "Bières blanches",
                "display_order": 5,
                "badge_bg_color": "#fef3c7",
                "badge_text_color": "#1f2937",
            },
            {
                "name": "Cidre",
                "description": "Cidres",
                "display_order": 6,
                "badge_bg_color": "#fde68a",
                "badge_text_color": "#92400e",
            },
        ),
    },
]


CELLAR_CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("Cave naturelle", "Cave naturelle traditionnelle", 1),
    ("Cave électrique", "Cave électrique de conservation", 2),
    ("Cave de vieillissement", "Cave dédiée au vieillissement des vins", 3),
    ("Cave d'appoint", "Cave d'appoint ou de service", 4),
)


def initialize_database() -> None:
    """Ensure the database contains the default configuration."""

    modified = False
    modified |= _ensure_alcohol_categories()
    modified |= _ensure_cellar_categories()
    modified |= _ensure_field_definitions()
    modified |= _ensure_field_requirements()

    if modified:
        db.session.commit()


def _ensure_alcohol_categories() -> bool:
    modified = False

    for category_data in ALCOHOL_CATEGORIES:
        category = AlcoholCategory.query.filter(
            func.lower(AlcoholCategory.name) == category_data["name"].lower()
        ).first()

        if category is None:
            category = AlcoholCategory(
                name=category_data["name"],
                description=category_data["description"],
                display_order=category_data["display_order"],
            )
            db.session.add(category)
            modified = True
        else:
            if category.description != category_data["description"]:
                category.description = category_data["description"]
                modified = True
            if category.display_order != category_data["display_order"]:
                category.display_order = category_data["display_order"]
                modified = True

        existing_subcategories = {
            subcategory.name: subcategory for subcategory in category.subcategories
        }
        for subcategory_data in category_data["subcategories"]:
            subcategory = existing_subcategories.get(subcategory_data["name"])
            if subcategory is None:
                subcategory = AlcoholSubcategory(
                    name=subcategory_data["name"],
                    description=subcategory_data["description"],
                    display_order=subcategory_data["display_order"],
                    badge_bg_color=subcategory_data["badge_bg_color"],
                    badge_text_color=subcategory_data["badge_text_color"],
                )
                category.subcategories.append(subcategory)
                modified = True
            else:
                modified |= _update_subcategory(subcategory, subcategory_data)

    if modified:
        db.session.flush()

    return modified


def _update_subcategory(
    subcategory: AlcoholSubcategory, data: dict[str, object]
) -> bool:
    modified = False

    for field in ("description", "display_order", "badge_bg_color", "badge_text_color"):
        value = data[field]
        if getattr(subcategory, field) != value:
            setattr(subcategory, field, value)
            modified = True

    return modified


def _ensure_cellar_categories() -> bool:
    modified = False

    existing = {
        category.name: category for category in CellarCategory.query.all()
    }

    for name, description, display_order in CELLAR_CATEGORIES:
        category = existing.get(name)
        if category is None:
            db.session.add(
                CellarCategory(
                    name=name,
                    description=description,
                    display_order=display_order,
                )
            )
            modified = True
        else:
            if category.description != description:
                category.description = description
                modified = True
            if category.display_order != display_order:
                category.display_order = display_order
                modified = True

    if modified:
        db.session.flush()

    return modified


def _ensure_field_definitions() -> bool:
    modified = False

    existing = {
        definition.name: definition for definition in BottleFieldDefinition.query.all()
    }

    for definition_data in DEFAULT_FIELD_DEFINITIONS:
        definition = existing.get(definition_data["name"])
        if definition is None:
            definition = BottleFieldDefinition(name=definition_data["name"])
            db.session.add(definition)
            existing[definition.name] = definition
            modified = True

        modified |= _update_definition(definition, definition_data)

    if modified:
        db.session.flush()

    return modified


def _update_definition(
    definition: BottleFieldDefinition, data: dict[str, object]
) -> bool:
    modified = False

    field_map = {
        "label": data.get("label"),
        "help_text": data.get("help_text"),
        "placeholder": data.get("placeholder"),
        "input_type": data.get("input_type", "text"),
        "form_width": int(data.get("form_width", 12)),
        "is_builtin": bool(data.get("is_builtin", False)),
        "display_order": int(data.get("display_order", 0)),
    }

    for field, value in field_map.items():
        if getattr(definition, field) != value:
            setattr(definition, field, value)
            modified = True

    return modified


def _ensure_field_requirements() -> bool:
    modified = False

    requirements: Iterable[dict[str, object]] = (
        {
            "field_name": "region",
            "category": None,
            "subcategory": None,
            "is_enabled": True,
            "is_required": False,
        },
        {
            "field_name": "year",
            "category": None,
            "subcategory": None,
            "is_enabled": True,
            "is_required": False,
        },
        {
            "field_name": "volume_ml",
            "category": None,
            "subcategory": None,
            "is_enabled": True,
            "is_required": True,
        },
        {
            "field_name": "description",
            "category": None,
            "subcategory": None,
            "is_enabled": True,
            "is_required": False,
        },
    )

    for requirement in requirements:
        modified |= _ensure_requirement(**requirement)

    wine_category = AlcoholCategory.query.filter_by(name="Vins").first()
    if wine_category is not None:
        modified |= _ensure_requirement(
            field_name="grape",
            category=wine_category,
            subcategory=None,
            is_enabled=True,
            is_required=False,
        )

    if modified:
        db.session.flush()

    return modified


def _ensure_requirement(
    *,
    field_name: str,
    category: AlcoholCategory | None,
    subcategory: AlcoholSubcategory | None,
    is_enabled: bool,
    is_required: bool,
) -> bool:
    modified = False

    category_id = category.id if category is not None else None
    subcategory_id = subcategory.id if subcategory is not None else None

    requirement = AlcoholFieldRequirement.query.filter_by(
        field_name=field_name,
        category_id=category_id,
        subcategory_id=subcategory_id,
    ).first()

    definition = BottleFieldDefinition.query.filter_by(name=field_name).first()
    if definition is None:
        definition = BottleFieldDefinition(
            name=field_name,
            label=field_name.replace("_", " ").title(),
            input_type="text",
            form_width=12,
            is_builtin=False,
            display_order=DEFAULT_DISPLAY_ORDERS.get(field_name, 0),
        )
        db.session.add(definition)
        modified = True
        db.session.flush()

    display_order = DEFAULT_DISPLAY_ORDERS.get(field_name, definition.display_order)

    if requirement is None:
        requirement = AlcoholFieldRequirement(
            field_name=field_name,
            category_id=category_id,
            subcategory_id=subcategory_id,
            is_enabled=is_enabled,
            is_required=is_required,
            display_order=display_order,
            field=definition,
        )
        db.session.add(requirement)
        modified = True
    else:
        if requirement.is_enabled != is_enabled:
            requirement.is_enabled = is_enabled
            modified = True
        if requirement.is_required != is_required:
            requirement.is_required = is_required
            modified = True
        if requirement.display_order != display_order:
            requirement.display_order = display_order
            modified = True
        if requirement.field_id != definition.id:
            requirement.field = definition
            modified = True

    return modified
