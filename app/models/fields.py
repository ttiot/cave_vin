"""Dynamic field definition models.

This module contains models for defining custom bottle fields
and their requirements per alcohol category.
"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint

from .base import db


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
