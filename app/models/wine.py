"""Wine and consumption models.

This module contains models for managing wines,
their insights, and consumption history.
"""
from __future__ import annotations

from datetime import datetime

from .base import db


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
