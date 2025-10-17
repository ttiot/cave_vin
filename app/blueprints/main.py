"""Blueprint principal pour les routes générales."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy.orm import selectinload

from models import AlcoholSubcategory, Cellar, Wine, WineConsumption


PRICE_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:€|euros?)", re.IGNORECASE)


main_bp = Blueprint('main', __name__)


def _parse_price_from_text(text: str) -> float | None:
    """Extrait une estimation de prix depuis un texte libre."""

    matches = PRICE_PATTERN.findall(text)
    values: list[float] = []
    for raw_value in matches:
        normalized = raw_value.replace(',', '.')
        try:
            values.append(float(normalized))
        except ValueError:
            continue

    if not values:
        return None

    if len(values) > 1 and any(sep in text for sep in ('-', 'à')):
        return sum(values) / len(values)

    return values[0]


def _estimate_wine_price(wine: Wine) -> float | None:
    """Retourne l'estimation de prix d'un vin à partir de ses insights."""

    for insight in wine.insights:
        content = insight.content or ''
        lowered_content = content.lower()
        if '€' not in content and 'eur' not in lowered_content:
            continue

        price = _parse_price_from_text(content)
        if price is not None:
            return price

    return None


def _format_currency(value: float) -> str:
    """Formate une valeur décimale en euros selon une présentation française."""

    return f"{value:,.2f}".replace(',', ' ').replace('.', ',')


def _compute_wines_to_consume_preview(wines: Iterable[Wine], limit: int = 3) -> tuple[list[dict], int]:
    """Calcule les vins à consommer en priorité avec leur score d'urgence."""

    current_year = datetime.now().year
    wines_with_urgency: list[dict] = []

    for wine in wines:
        year = wine.extra_attributes.get('year')
        if not year:
            continue

        wine_age = current_year - year
        urgency_score = 0
        garde_info = None
        recommended_years = None

        for insight in wine.insights:
            content_lower = (insight.content or '').lower()

            if any(keyword in content_lower for keyword in ['garde', 'garder', 'conserver', 'vieillissement', 'apogée', 'boire']):
                garde_info = insight.content

                years_match = re.search(r'(\d+)\s*(?:à|-)\s*(\d+)\s*ans?', content_lower)
                if years_match:
                    min_years = int(years_match.group(1))
                    max_years = int(years_match.group(2))
                    recommended_years = (min_years, max_years)

                    if wine_age >= max_years:
                        urgency_score = 100
                    elif wine_age >= min_years:
                        progress = (wine_age - min_years) / (max_years - min_years)
                        urgency_score = 50 + (progress * 50)
                    else:
                        urgency_score = (wine_age / min_years) * 30

                if any(keyword in content_lower for keyword in ['maintenant', 'immédiatement', 'rapidement', 'bientôt']):
                    urgency_score = max(urgency_score, 80)

                if any(keyword in content_lower for keyword in ['apogée', 'optimal', 'parfait']):
                    urgency_score = max(urgency_score, 60)

        if urgency_score == 0 and wine_age > 0:
            if wine_age >= 15:
                urgency_score = 70
            elif wine_age >= 10:
                urgency_score = 50
            elif wine_age >= 5:
                urgency_score = 30
            else:
                urgency_score = 10

        if urgency_score > 0:
            wines_with_urgency.append(
                {
                    'wine': wine,
                    'urgency_score': urgency_score,
                    'wine_age': wine_age,
                    'garde_info': garde_info,
                    'recommended_years': recommended_years,
                }
            )

    wines_with_urgency.sort(key=lambda x: x['urgency_score'], reverse=True)

    return wines_with_urgency[:limit], current_year


@main_bp.route('/')
@login_required
def index():
    """Page d'accueil avec vue synthétique de la cave."""

    wines = (
        Wine.query.options(
            selectinload(Wine.cellar),
            selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
            selectinload(Wine.insights),
        )
        .filter(Wine.quantity > 0)
        .order_by(Wine.name.asc())
        .all()
    )
    cellars = Cellar.query.order_by(Cellar.name.asc()).all()

    total_bottles = sum(wine.quantity or 0 for wine in wines)

    estimated_value = 0.0
    for wine in wines:
        price = _estimate_wine_price(wine)
        if price is not None and wine.quantity:
            estimated_value += price * wine.quantity

    estimated_value = round(estimated_value, 2) if estimated_value > 0 else None
    estimated_value_display = _format_currency(estimated_value) if estimated_value is not None else None

    wines_to_consume_preview, current_year = _compute_wines_to_consume_preview(wines)

    recent_wines = (
        Wine.query.options(
            selectinload(Wine.cellar),
            selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
        )
        .filter(Wine.quantity > 0)
        .order_by(Wine.id.desc())
        .limit(4)
        .all()
    )

    return render_template(
        'index.html',
        cellars=cellars,
        total_bottles=total_bottles,
        estimated_value=estimated_value,
        estimated_value_display=estimated_value_display,
        wines_to_consume_preview=wines_to_consume_preview,
        recent_wines=recent_wines,
        current_year=current_year,
    )


@main_bp.route('/consommations', methods=['GET'])
@login_required
def consumption_history():
    """Affiche l'historique des consommations."""
    consumptions = (
        WineConsumption.query.options(selectinload(WineConsumption.wine))
        .order_by(WineConsumption.consumed_at.desc())
        .all()
    )
    return render_template('consumption_history.html', consumptions=consumptions)
