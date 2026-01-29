"""SMTP configuration and email logging models.

This module contains models for managing SMTP configurations
and tracking email sending history.
"""
from __future__ import annotations

from datetime import datetime

from .base import db


class SMTPConfig(db.Model):
    """Configuration SMTP pour l'envoi d'emails."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, default="Configuration principale")
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=587)
    username = db.Column(db.String(255), nullable=True)
    password_encrypted = db.Column(db.Text, nullable=True)
    use_tls = db.Column(db.Boolean, default=True, nullable=False)
    use_ssl = db.Column(db.Boolean, default=False, nullable=False)
    sender_email = db.Column(db.String(255), nullable=False)
    sender_name = db.Column(db.String(100), nullable=True)
    timeout = db.Column(db.Integer, default=30, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_test_at = db.Column(db.DateTime, nullable=True)
    last_test_success = db.Column(db.Boolean, nullable=True)
    last_test_error = db.Column(db.Text, nullable=True)

    def set_password(self, password: str) -> None:
        """Chiffre et stocke le mot de passe SMTP.
        
        Utilise Fernet pour le chiffrement symétrique.
        La clé de chiffrement doit être définie dans la configuration de l'application.
        """
        if not password:
            self.password_encrypted = None
            return
        
        from cryptography.fernet import Fernet
        from flask import current_app
        
        key = current_app.config.get("SMTP_ENCRYPTION_KEY")
        if not key:
            # Générer une clé si elle n'existe pas (à stocker dans la config)
            key = Fernet.generate_key()
            current_app.logger.warning(
                "SMTP_ENCRYPTION_KEY non définie. Utilisez cette clé dans votre configuration: %s",
                key.decode()
            )
        
        if isinstance(key, str):
            key = key.encode()
        
        f = Fernet(key)
        self.password_encrypted = f.encrypt(password.encode()).decode()

    def get_password(self) -> str | None:
        """Déchiffre et retourne le mot de passe SMTP."""
        if not self.password_encrypted:
            return None
        
        from cryptography.fernet import Fernet
        from flask import current_app
        
        key = current_app.config.get("SMTP_ENCRYPTION_KEY")
        if not key:
            return None
        
        if isinstance(key, str):
            key = key.encode()
        
        try:
            f = Fernet(key)
            return f.decrypt(self.password_encrypted.encode()).decode()
        except Exception:
            return None

    @staticmethod
    def get_default() -> "SMTPConfig | None":
        """Retourne la configuration SMTP par défaut active."""
        return SMTPConfig.query.filter_by(is_default=True, is_active=True).first()

    @staticmethod
    def get_active() -> "SMTPConfig | None":
        """Retourne une configuration SMTP active (par défaut ou première disponible)."""
        config = SMTPConfig.get_default()
        if config:
            return config
        return SMTPConfig.query.filter_by(is_active=True).first()

    def to_dict(self, include_password: bool = False) -> dict:
        """Retourne un dictionnaire représentant la configuration."""
        data = {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "use_tls": self.use_tls,
            "use_ssl": self.use_ssl,
            "sender_email": self.sender_email,
            "sender_name": self.sender_name,
            "timeout": self.timeout,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "last_test_at": self.last_test_at.isoformat() if self.last_test_at else None,
            "last_test_success": self.last_test_success,
        }
        if include_password:
            data["has_password"] = bool(self.password_encrypted)
        return data


class EmailLog(db.Model):
    """Log des emails envoyés."""

    id = db.Column(db.Integer, primary_key=True)
    smtp_config_id = db.Column(db.Integer, db.ForeignKey("smtp_config.id"), nullable=True)
    recipient_email = db.Column(db.String(255), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    subject = db.Column(db.String(500), nullable=False)
    template_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, sent, failed
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    smtp_config = db.relationship("SMTPConfig", backref=db.backref("email_logs", lazy="dynamic"))
    recipient_user = db.relationship("User", backref=db.backref("received_emails", lazy="dynamic"))

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    @staticmethod
    def log_email(
        recipient_email: str,
        subject: str,
        smtp_config_id: int = None,
        recipient_user_id: int = None,
        template_name: str = None,
    ) -> "EmailLog":
        """Crée un log d'email."""
        log = EmailLog(
            smtp_config_id=smtp_config_id,
            recipient_email=recipient_email,
            recipient_user_id=recipient_user_id,
            subject=subject,
            template_name=template_name,
            status=EmailLog.STATUS_PENDING,
        )
        db.session.add(log)
        return log

    def mark_sent(self) -> None:
        """Marque l'email comme envoyé."""
        self.status = self.STATUS_SENT
        self.sent_at = datetime.utcnow()
        self.error_message = None

    def mark_failed(self, error: str) -> None:
        """Marque l'email comme échoué."""
        self.status = self.STATUS_FAILED
        self.error_message = error
