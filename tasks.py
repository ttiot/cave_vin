"""Background tasks used to enrich wines with information from external services."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from models import Wine, WineInsight, db
from services.wine_info_service import InsightData, WineInfoService

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wine-info")

def schedule_wine_enrichment(wine_id: int) -> None:
    """Launch an asynchronous job that fetches contextual data for a wine."""

    app = current_app._get_current_object()
    _executor.submit(_run_enrichment, app, wine_id)


def _run_enrichment(app, wine_id: int) -> None:
    with app.app_context():
        wine = Wine.query.get(wine_id)
        if not wine:
            logger.warning("Wine %s disappeared before enrichment", wine_id)
            return

        logger.info("Starting enrichment for wine %s", wine.name)

        service = WineInfoService.from_app(app)
        insights = service.fetch(wine)
        if not insights:
            logger.info("No insights available for wine %s", wine.name)
            return

        _store_insights(wine, insights)


def _store_insights(wine: Wine, insights: Iterable[InsightData]) -> None:
    existing_keys = {
        (
            insight.category,
            insight.title,
            insight.content,
            insight.source_url,
        )
        for insight in wine.insights
    }

    added = 0
    for data in insights:
        key = (data.category, data.title, data.content, data.source_url)
        if key in existing_keys:
            continue

        model = WineInsight(
            wine=wine,
            category=data.category,
            title=data.title,
            content=data.content,
            source_name=data.source_name,
            source_url=data.source_url,
            weight=data.weight,
        )
        db.session.add(model)
        existing_keys.add(key)
        added += 1

    if not added:
        logger.info("All insights already stored for wine %s", wine.name)
        return

    try:
        db.session.commit()
        logger.info("Stored %s new insights for wine %s", added, wine.name)
    except SQLAlchemyError:  # pragma: no cover - defensive commit
        db.session.rollback()
        logger.exception("Failed to persist insights for wine %s", wine.name)
