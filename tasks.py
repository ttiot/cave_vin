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
    # Convertir l'itérable en liste pour pouvoir le parcourir plusieurs fois
    insights_list = list(insights)
    
    if not insights_list:
        logger.info("No new insights to store for wine %s", wine.name)
        return
    
    # Supprimer tous les anciens insights avant d'ajouter les nouveaux
    # Cela garantit qu'on remplace complètement les données
    old_insights_count = len(wine.insights)
    if old_insights_count > 0:
        logger.info("Removing %s old insights for wine %s", old_insights_count, wine.name)
        for old_insight in list(wine.insights):
            db.session.delete(old_insight)
    
    # Ajouter les nouveaux insights
    added = 0
    for data in insights_list:
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
        added += 1

    try:
        db.session.commit()
        logger.info("Replaced %s old insights with %s new insights for wine %s",
                   old_insights_count, added, wine.name)
    except SQLAlchemyError:  # pragma: no cover - defensive commit
        db.session.rollback()
        logger.exception("Failed to persist insights for wine %s", wine.name)
