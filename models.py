from __future__ import annotations

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    has_temporary_password = db.Column(db.Boolean, default=False, nullable=False)


class Cellar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cellar_type = db.Column(db.String(50), nullable=False)
    floor_count = db.Column("floors", db.Integer, nullable=False)
    bottles_per_floor = db.Column(db.Integer, nullable=False)

    wines = db.relationship("Wine", back_populates="cellar", lazy="dynamic")
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


class Wine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    region = db.Column(db.String(120))
    grape = db.Column(db.String(80))
    year = db.Column(db.Integer)
    barcode = db.Column(db.String(20), unique=True)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    quantity = db.Column(db.Integer, default=1)
    cellar_id = db.Column(db.Integer, db.ForeignKey("cellar.id"), nullable=False)

    cellar = db.relationship("Cellar", back_populates="wines")
    insights = db.relationship(
        "WineInsight",
        back_populates="wine",
        cascade="all, delete-orphan",
        order_by="WineInsight.weight.desc(), WineInsight.created_at.desc()",
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
