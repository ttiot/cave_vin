"""Models package - centralized entry point for all database models.

This package provides a modular structure for SQLAlchemy models,
organized by domain. All models are re-exported here for convenient access.

Usage:
    from app.models import db, User, Wine, Cellar
"""
from __future__ import annotations

from .base import db
from .user import User, UserSettings, PushSubscription
from .auth_tokens import APIToken, APITokenUsage
from .activity import ActivityLog, Webhook
from .cellar import CellarCategory, Cellar, CellarFloor
from .alcohol import AlcoholCategory, AlcoholSubcategory
from .wine import Wine, WineInsight, WineConsumption
from .fields import BottleFieldDefinition, AlcoholFieldRequirement
from .smtp import SMTPConfig, EmailLog

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
