"""Field metadata management helpers."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

from models import BottleFieldDefinition


# ---------------------------------------------------------------------------
# Default/built-in field definitions used when bootstrapping the database.
# ---------------------------------------------------------------------------

DEFAULT_FIELD_DEFINITIONS: List[dict[str, object]] = [
    {
        "name": "region",
        "label": "Région",
        "display_order": 10,
        "input_type": "text",
        "form_width": 6,
        "is_builtin": True,
        "placeholder": "Bordeaux, Bourgogne...",
    },
    {
        "name": "grape",
        "label": "Cépage",
        "display_order": 20,
        "input_type": "text",
        "form_width": 6,
        "is_builtin": True,
        "placeholder": "Merlot, Pinot Noir...",
    },
    {
        "name": "year",
        "label": "Année",
        "display_order": 30,
        "input_type": "number",
        "form_width": 3,
        "is_builtin": True,
    },
    {
        "name": "volume_ml",
        "label": "Contenance (mL)",
        "display_order": 40,
        "input_type": "number",
        "form_width": 3,
        "is_builtin": True,
        "help_text": "Indiquez la contenance en millilitres (ex\xa0: 750).",
    },
    {
        "name": "description",
        "label": "Description",
        "display_order": 50,
        "input_type": "textarea",
        "form_width": 12,
        "is_builtin": True,
    },
]

DEFAULT_FIELD_MAP: Dict[str, dict[str, object]] = {
    field["name"]: field for field in DEFAULT_FIELD_DEFINITIONS
}


# Mapping between known field identifiers and Wine model attributes.
FIELD_STORAGE_MAP: Dict[str, dict[str, str]] = {
    "region": {"attribute": "region"},
    "grape": {"attribute": "grape"},
    "year": {"attribute": "year"},
    "volume_ml": {"attribute": "volume_ml"},
    "description": {"attribute": "description"},
}


def iter_fields() -> Iterable[BottleFieldDefinition]:
    """Return the field definitions ordered by display priority."""

    return BottleFieldDefinition.query.order_by(
        BottleFieldDefinition.display_order.asc(),
        BottleFieldDefinition.label.asc(),
    ).all()


def get_field_map() -> Dict[str, BottleFieldDefinition]:
    """Return a dictionary mapping field names to their definitions."""

    return {field.name: field for field in iter_fields()}


def get_display_order(field_name: str) -> int:
    """Return the display order for the provided field."""

    field = BottleFieldDefinition.query.filter_by(name=field_name).first()
    if field:
        return int(field.display_order)
    return int(DEFAULT_FIELD_MAP.get(field_name, {}).get("display_order", 0))


def sanitize_field_name(label: str) -> str:
    """Generate a machine-friendly identifier from a human label."""

    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or "champ"
