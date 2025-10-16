"""Field metadata shared across the application."""

from __future__ import annotations

from typing import Iterable, Tuple

FIELD_DEFINITIONS: dict[str, dict[str, object]] = {
    "region": {
        "label": "Région",
        "display_order": 10,
    },
    "grape": {
        "label": "Cépage",
        "display_order": 20,
    },
    "year": {
        "label": "Année",
        "display_order": 30,
    },
    "volume_ml": {
        "label": "Contenance (mL)",
        "display_order": 40,
        "help_text": "Indiquez la contenance en millilitres (ex\xa0: 750).",
    },
    "description": {
        "label": "Description",
        "display_order": 50,
    },
}


def iter_fields() -> Iterable[Tuple[str, dict[str, object]]]:
    """Return the field definitions ordered by display priority."""

    return sorted(
        FIELD_DEFINITIONS.items(),
        key=lambda item: int(item[1].get("display_order", 0)),
    )


def get_display_order(field_name: str) -> int:
    """Return the configured display order for a field."""

    definition = FIELD_DEFINITIONS.get(field_name, {})
    return int(definition.get("display_order", 0))
