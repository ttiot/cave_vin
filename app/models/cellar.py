"""Cellar management models.

This module contains models for managing wine cellars,
their categories, and floor configurations.
"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint

from .base import db


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
