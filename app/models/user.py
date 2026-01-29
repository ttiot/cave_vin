"""User and settings models.

This module contains models for user accounts,
their settings, and push notification subscriptions.
"""
from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin

from .base import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password = db.Column(db.String(200), nullable=False)
    has_temporary_password = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    default_cellar_id = db.Column(db.Integer, db.ForeignKey("cellar.id", ondelete="SET NULL"), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    # Relation vers le compte parent (si sous-compte)
    parent = db.relationship(
        "User",
        remote_side=[id],
        backref=db.backref("sub_accounts", lazy="dynamic", cascade="all, delete-orphan"),
        foreign_keys=[parent_id],
    )

    cellars = db.relationship(
        "Cellar",
        back_populates="owner",
        cascade="all, delete-orphan",
        foreign_keys="Cellar.user_id",
    )
    default_cellar = db.relationship(
        "Cellar",
        foreign_keys=[default_cellar_id],
        post_update=True,
    )
    wines = db.relationship(
        "Wine",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    consumptions = db.relationship(
        "WineConsumption",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def is_sub_account(self) -> bool:
        """Retourne True si ce compte est un sous-compte."""
        return self.parent_id is not None

    @property
    def owner_id(self) -> int:
        """Retourne l'ID du propriétaire effectif des ressources.
        
        Pour un sous-compte, c'est l'ID du compte parent.
        Pour un compte principal, c'est son propre ID.
        """
        return self.parent_id if self.parent_id is not None else self.id

    @property
    def owner_account(self) -> "User":
        """Retourne le compte propriétaire des ressources.
        
        Pour un sous-compte, c'est le compte parent.
        Pour un compte principal, c'est lui-même.
        """
        return self.parent if self.parent is not None else self


class UserSettings(db.Model):
    """Paramètres utilisateur (thème, quotas, préférences)."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    theme = db.Column(db.String(20), default="light", nullable=False)
    max_bottles = db.Column(db.Integer, nullable=True)
    push_notifications_enabled = db.Column(db.Boolean, default=False, nullable=False)
    push_subscription = db.Column(db.JSON, nullable=True)
    tutorial_completed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("settings", uselist=False, cascade="all, delete-orphan"))


class PushSubscription(db.Model):
    """Abonnement aux notifications push pour un utilisateur."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    endpoint = db.Column(db.String(500), nullable=False, unique=True)
    p256dh_key = db.Column(db.String(200), nullable=False)
    auth_key = db.Column(db.String(100), nullable=False)
    user_agent = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("push_subscriptions", cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        """Retourne la subscription au format Web Push."""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh_key,
                "auth": self.auth_key,
            }
        }

    @staticmethod
    def from_subscription_info(user_id: int, subscription: dict, user_agent: str = None) -> "PushSubscription":
        """Crée une instance depuis les données de subscription du navigateur."""
        keys = subscription.get("keys", {})
        return PushSubscription(
            user_id=user_id,
            endpoint=subscription.get("endpoint"),
            p256dh_key=keys.get("p256dh"),
            auth_key=keys.get("auth"),
            user_agent=user_agent,
        )
