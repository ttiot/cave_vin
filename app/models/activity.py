"""Activity logging and webhook models.

This module contains models for tracking user activity
and managing webhook configurations.
"""
from __future__ import annotations

from datetime import datetime

from .base import db


class ActivityLog(db.Model):
    """Log d'activité utilisateur pour l'audit."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("activity_logs", cascade="all, delete-orphan"))

    @staticmethod
    def log(user_id: int, action: str, entity_type: str = None, entity_id: int = None,
            details: dict = None, ip_address: str = None, user_agent: str = None) -> "ActivityLog":
        """Crée un log d'activité."""
        log_entry = ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(log_entry)
        return log_entry


class Webhook(db.Model):
    """Configuration de webhook pour notifications externes."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(64), nullable=True)
    events = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    failure_count = db.Column(db.Integer, default=0, nullable=False)

    user = db.relationship("User", backref=db.backref("webhooks", cascade="all, delete-orphan"))

    EVENTS = [
        "wine.created",
        "wine.updated",
        "wine.deleted",
        "wine.consumed",
        "cellar.created",
        "cellar.updated",
        "cellar.deleted",
        "stock.low",
    ]
