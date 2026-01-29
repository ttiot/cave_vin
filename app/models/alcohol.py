"""Alcohol category models.

This module contains models for managing alcohol categories
and subcategories (e.g., Wines, Spirits, Beers).
"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint

from .base import db


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
