"""API token authentication models.

This module contains models for managing API tokens
and tracking their usage.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from .base import db


class APIToken(db.Model):
    """Token d'authentification API généré par l'utilisateur."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    token_prefix = db.Column(db.String(8), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    rate_limit = db.Column(db.Integer, default=100, nullable=False)  # Requêtes par heure
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User", backref=db.backref("api_tokens", cascade="all, delete-orphan"))
    usage_logs = db.relationship(
        "APITokenUsage",
        back_populates="token",
        cascade="all, delete-orphan",
        order_by="desc(APITokenUsage.timestamp)",
    )

    @staticmethod
    def generate_token() -> tuple[str, str]:
        """Génère un nouveau token et retourne (token_clair, token_hash).
        
        Le token clair est préfixé par 'cv_' pour faciliter l'identification.
        """
        raw_token = secrets.token_hex(32)
        full_token = f"cv_{raw_token}"
        token_hash = secrets.token_hex(32)
        return full_token, token_hash

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash un token pour comparaison sécurisée."""
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()

    @property
    def is_expired(self) -> bool:
        """Vérifie si le token a expiré."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Vérifie si le token est valide (actif et non expiré)."""
        return self.is_active and not self.is_expired

    def get_usage_count(self, hours: int = 1) -> int:
        """Retourne le nombre d'utilisations dans les dernières heures."""
        from sqlalchemy import func
        cutoff = datetime.utcnow() - __import__('datetime').timedelta(hours=hours)
        return APITokenUsage.query.filter(
            APITokenUsage.token_id == self.id,
            APITokenUsage.timestamp >= cutoff
        ).count()

    def is_rate_limited(self) -> bool:
        """Vérifie si le token a dépassé sa limite de requêtes."""
        return self.get_usage_count(hours=1) >= self.rate_limit


class APITokenUsage(db.Model):
    """Log d'utilisation d'un token API."""

    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey("api_token.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    endpoint = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    response_time_ms = db.Column(db.Integer, nullable=True)

    token = db.relationship("APIToken", back_populates="usage_logs")
