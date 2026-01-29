"""Compatibility facade for models.

This module re-exports all models from app.models for backward compatibility.
New code should prefer importing from app.models directly:

    from app.models import db, User, Wine

Legacy imports continue to work:

    from models import db, User, Wine
"""
from __future__ import annotations

from app.models import (
    db,
    User, UserSettings, PushSubscription,
    APIToken, APITokenUsage,
    ActivityLog, Webhook,
    CellarCategory, Cellar, CellarFloor,
    AlcoholCategory, AlcoholSubcategory,
    Wine, WineInsight, WineConsumption,
    BottleFieldDefinition, AlcoholFieldRequirement,
    SMTPConfig, EmailLog,
)

__all__ = [
    "db",
    "User", "UserSettings", "PushSubscription",
    "APIToken", "APITokenUsage",
    "ActivityLog", "Webhook",
    "CellarCategory", "Cellar", "CellarFloor",
    "AlcoholCategory", "AlcoholSubcategory",
    "Wine", "WineInsight", "WineConsumption",
    "BottleFieldDefinition", "AlcoholFieldRequirement",
    "SMTPConfig", "EmailLog",
]
