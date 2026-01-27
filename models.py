from __future__ import annotations

import secrets
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, desc

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
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


class CellarCategory(db.Model):
    """Catégorie de cave (ex: Cave principale, Cave de vieillissement, Cave d'appoint)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    description = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    
    cellars = db.relationship(
        "Cellar",
        back_populates="category",
        order_by="Cellar.name",
    )


class Cellar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    floor_count = db.Column("floors", db.Integer, nullable=False)
    bottles_per_floor = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("cellar_category.id"), nullable=False)

    wines = db.relationship("Wine", back_populates="cellar", lazy="dynamic")
    owner = db.relationship("User", back_populates="cellars", foreign_keys=[user_id])
    category = db.relationship("CellarCategory", back_populates="cellars")
    levels = db.relationship(
        "CellarFloor",
        order_by="CellarFloor.level",
        back_populates="cellar",
        cascade="all, delete-orphan",
    )

    @property
    def floors(self):
        return self.floor_count

    @property
    def floor_capacities(self):
        if self.levels:
            return [level.capacity for level in self.levels]
        if self.floor_count and self.bottles_per_floor:
            return [self.bottles_per_floor] * self.floor_count
        return []

    @property
    def capacity(self):
        return sum(self.floor_capacities)

    @property
    def floor_breakdown(self):
        return list(enumerate(self.floor_capacities, start=1))


class CellarFloor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cellar_id = db.Column(db.Integer, db.ForeignKey("cellar.id"), nullable=False)
    level = db.Column(db.Integer, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)

    cellar = db.relationship("Cellar", back_populates="levels")

    __table_args__ = (UniqueConstraint("cellar_id", "level", name="uq_cellar_level"),)


class AlcoholCategory(db.Model):
    """Catégorie principale d'alcool (ex: Vins, Spiritueux, Bières)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    description = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)

    subcategories = db.relationship(
        "AlcoholSubcategory",
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="AlcoholSubcategory.display_order, AlcoholSubcategory.name",
    )
    field_requirements = db.relationship(
        "AlcoholFieldRequirement",
        back_populates="category",
        cascade="all, delete-orphan",
    )


class AlcoholSubcategory(db.Model):
    """Sous-catégorie d'alcool (ex: Vin rouge, Rhum ambré, IPA)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("alcohol_category.id"), nullable=False)
    description = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    badge_bg_color = db.Column(db.String(20), nullable=False, default="#6366f1")
    badge_text_color = db.Column(db.String(20), nullable=False, default="#ffffff")

    category = db.relationship("AlcoholCategory", back_populates="subcategories")
    wines = db.relationship("Wine", back_populates="subcategory")
    field_requirements = db.relationship(
        "AlcoholFieldRequirement",
        back_populates="subcategory",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_category_subcategory"),
    )


class Wine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    barcode = db.Column(db.String(20), unique=True)
    extra_attributes = db.Column(db.JSON, nullable=False, default=dict)
    image_url = db.Column(db.String(255))
    label_image_data = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=1)
    cellar_id = db.Column(db.Integer, db.ForeignKey("cellar.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    subcategory_id = db.Column(db.Integer, db.ForeignKey("alcohol_subcategory.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    cellar = db.relationship("Cellar", back_populates="wines")
    owner = db.relationship("User", back_populates="wines")
    subcategory = db.relationship("AlcoholSubcategory", back_populates="wines")
    insights = db.relationship(
        "WineInsight",
        back_populates="wine",
        cascade="all, delete-orphan",
        order_by="desc(WineInsight.weight), desc(WineInsight.created_at)",
    )
    consumptions = db.relationship(
        "WineConsumption",
        back_populates="wine",
        cascade="all, delete-orphan",
        order_by="desc(WineConsumption.consumed_at)",
    )

    def preview_insights(self, limit: int = 2) -> list[dict[str, str]]:
        """Return a lightweight representation of the first insights for popovers."""

        preview = []
        for insight in self.insights[:limit]:
            preview.append(
                {
                    "title": insight.title or insight.category or insight.source_name or "Information",
                    "content": insight.content,
                    "source": insight.source_name,
                }
            )
        return preview


class AlcoholFieldRequirement(db.Model):
    """Configure quelles informations sont attendues pour une catégorie donnée."""

    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(50), nullable=False)
    field_id = db.Column(
        db.Integer, db.ForeignKey("bottle_field_definition.id"), nullable=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("alcohol_category.id"), nullable=True
    )
    subcategory_id = db.Column(
        db.Integer, db.ForeignKey("alcohol_subcategory.id"), nullable=True
    )
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    is_required = db.Column(db.Boolean, nullable=False, default=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    category = db.relationship("AlcoholCategory", back_populates="field_requirements")
    subcategory = db.relationship(
        "AlcoholSubcategory", back_populates="field_requirements"
    )
    field = db.relationship("BottleFieldDefinition", back_populates="requirements")

    __table_args__ = (
        UniqueConstraint("field_name", "category_id", "subcategory_id"),
    )


class BottleFieldDefinition(db.Model):
    """Describe an available data point that can be attached to a bottle."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    label = db.Column(db.String(120), nullable=False)
    help_text = db.Column(db.Text)
    placeholder = db.Column(db.String(255))
    input_type = db.Column(db.String(20), nullable=False, default="text")
    form_width = db.Column(db.Integer, nullable=False, default=12)
    is_builtin = db.Column(db.Boolean, nullable=False, default=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    requirements = db.relationship(
        "AlcoholFieldRequirement",
        back_populates="field",
        cascade="all, delete-orphan",
    )

    def as_dict(self) -> dict[str, object]:
        """Return a lightweight representation for templating helpers."""

        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "help_text": self.help_text,
            "placeholder": self.placeholder,
            "input_type": self.input_type,
            "form_width": self.form_width,
            "is_builtin": self.is_builtin,
            "display_order": self.display_order,
        }


class WineInsight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wine_id = db.Column(db.Integer, db.ForeignKey("wine.id"), nullable=False, index=True)
    category = db.Column(db.String(50))
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    source_name = db.Column(db.String(120))
    source_url = db.Column(db.String(255))
    weight = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    wine = db.relationship("Wine", back_populates="insights")

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "weight": self.weight,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WineConsumption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wine_id = db.Column(db.Integer, db.ForeignKey("wine.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    comment = db.Column(db.Text)
    snapshot_name = db.Column(db.String(120), nullable=False)
    snapshot_year = db.Column(db.Integer)
    snapshot_region = db.Column(db.String(120))
    snapshot_grape = db.Column(db.String(80))
    snapshot_cellar = db.Column(db.String(120))

    wine = db.relationship("Wine", back_populates="consumptions")
    user = db.relationship("User", back_populates="consumptions")

    def describe(self) -> str:
        parts: list[str] = [self.snapshot_name]
        if self.snapshot_year:
            parts.append(str(self.snapshot_year))
        if self.snapshot_region:
            parts.append(self.snapshot_region)
        return " — ".join(parts)


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
