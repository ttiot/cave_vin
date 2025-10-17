from __future__ import annotations

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
    category_id = db.Column(db.Integer, db.ForeignKey("cellar_category.id"), nullable=False)

    wines = db.relationship("Wine", back_populates="cellar", lazy="dynamic")
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
    quantity = db.Column(db.Integer, default=1)
    cellar_id = db.Column(db.Integer, db.ForeignKey("cellar.id"), nullable=False)
    subcategory_id = db.Column(db.Integer, db.ForeignKey("alcohol_subcategory.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    cellar = db.relationship("Cellar", back_populates="wines")
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
    consumed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    snapshot_name = db.Column(db.String(120), nullable=False)
    snapshot_year = db.Column(db.Integer)
    snapshot_region = db.Column(db.String(120))
    snapshot_grape = db.Column(db.String(80))
    snapshot_cellar = db.Column(db.String(120))

    wine = db.relationship("Wine", back_populates="consumptions")

    def describe(self) -> str:
        parts: list[str] = [self.snapshot_name]
        if self.snapshot_year:
            parts.append(str(self.snapshot_year))
        if self.snapshot_region:
            parts.append(self.snapshot_region)
        return " — ".join(parts)
