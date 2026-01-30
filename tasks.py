"""Background tasks used to enrich wines with information from external services."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.models import Wine, WineInsight, db
from services.wine_info_service import EnrichmentResult, WineInfoService

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wine-info")

def schedule_wine_enrichment(wine_id: int, user_id: int = None) -> None:
    """Launch an asynchronous job that fetches contextual data for a wine.
    
    Args:
        wine_id: ID du vin à enrichir
        user_id: ID de l'utilisateur (pour utiliser sa clé API si configurée)
    """
    app = current_app._get_current_object()
    _executor.submit(_run_enrichment, app, wine_id, user_id)


def _run_enrichment(app, wine_id: int, user_id: int = None) -> None:
    with app.app_context():
        wine = Wine.query.get(wine_id)
        if not wine:
            logger.warning("Wine %s disappeared before enrichment", wine_id)
            return

        logger.info("Starting enrichment for wine %s", wine.name)

        # Utiliser l'ID utilisateur fourni ou celui du propriétaire du vin
        effective_user_id = user_id or wine.user_id
        
        # Utiliser for_user pour bénéficier de la clé API appropriée et du logging
        service = WineInfoService.for_user(effective_user_id)
        enrichment = service.fetch(wine)
        if not enrichment.has_payload():
            logger.info("No enrichment data available for wine %s", wine.name)
            return

        _store_enrichment(wine, enrichment)


def _store_enrichment(wine: Wine, enrichment: EnrichmentResult) -> None:
    insights_list = list(enrichment.insights or [])

    old_insights_count = len(wine.insights)
    added = 0

    if insights_list:
        logger.info(
            "Preparing to replace %s insights with %s new ones for wine %s",
            old_insights_count,
            len(insights_list),
            wine.name,
        )

        for old_insight in list(wine.insights):
            db.session.delete(old_insight)

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
    else:
        logger.info("No new insights to store for wine %s", wine.name)

    if enrichment.label_image_data:
        logger.info("Updating generated label image for wine %s", wine.name)
        wine.label_image_data = enrichment.label_image_data

    if not insights_list and not enrichment.label_image_data:
        logger.info("No enrichment data to persist for wine %s", wine.name)
        return

    try:
        db.session.commit()
        if insights_list:
            logger.info(
                "Replaced %s old insights with %s new insights for wine %s",
                old_insights_count,
                added,
                wine.name,
            )
        if enrichment.label_image_data:
            logger.info("Stored label image for wine %s", wine.name)
    except SQLAlchemyError:  # pragma: no cover - defensive commit
        db.session.rollback()
        logger.exception("Failed to persist enrichment for wine %s", wine.name)
