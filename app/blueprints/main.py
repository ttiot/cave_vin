"""Blueprint principal pour les routes générales."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy.orm import selectinload

from models import AlcoholSubcategory, Cellar, Wine, WineConsumption


PRICE_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:€|euros?)", re.IGNORECASE)
YEAR_SPAN_PATTERN = re.compile(r"(\d+)\s*(?:à|-|–)\s*(\d+)\s*ans?", re.IGNORECASE)
YEAR_SINGLE_PATTERN = re.compile(r"(\d+)\s*ans?", re.IGNORECASE)

COUNTRY_COORDINATES = {
# Europe
"france": (46.2276, 2.2137),
"italie": (41.8719, 12.5674),
"espagne": (40.4637, -3.7492),
"portugal": (39.3999, -8.2245),
"allemagne": (51.1657, 10.4515),
"suisse": (46.8182, 8.2275),
"autriche": (47.5162, 14.5501),
"hongrie": (47.1625, 19.5033),
"grèce": (39.0742, 21.8243),
"roumanie": (45.9432, 24.9668),
"croatie": (45.1000, 15.2000),
"slovénie": (46.1512, 14.9955),
"bulgarie": (42.7339, 25.4858),
"république tchèque": (49.8175, 15.4730),
"arménie": (40.0691, 45.0382),
"géorgie": (42.3154, 43.3569),
"royaume-uni": (55.3781, -3.4360),


# Afrique
"afrique du sud": (-30.5595, 22.9375),
"maroc": (31.7917, -7.0926),
"algérie": (28.0339, 1.6596),
"tunisie": (33.8869, 9.5375),
"égypte": (26.8206, 30.8025),
"éthiopie": (9.1450, 40.4897),
# Amériques
"etats-unis": (37.0902, -95.7129),
"canada": (56.1304, -106.3468),
"mexique": (23.6345, -102.5528),
"argentine": (-38.4161, -63.6167),
"chili": (-35.6751, -71.5430),
"brésil": (-14.2350, -51.9253),
"uruguay": (-32.5228, -55.7658),
"pérou": (-9.1900, -75.0152),
"colombie": (4.5709, -74.2973),
"cuba": (21.5218, -77.7812),
"république dominicaine": (18.7357, -70.1627),
"jamaïque": (18.1096, -77.2975),
"guadeloupe": (16.2650, -61.5500),
"martinique": (14.6415, -61.0242),
"guyane française": (3.9339, -53.1258),
"réunion": (-21.1151, 55.5364),
"madère": (32.7607, -16.9595),
"canaries": (28.2916, -16.6291),


# Asie / Océanie
"chine": (35.8617, 104.1954),
"japon": (36.2048, 138.2529),
"inde": (20.5937, 78.9629),
"turquie": (38.9637, 35.2433),
"liban": (33.8547, 35.8623),
"israël": (31.0461, 34.8516),
"géorgie": (42.3154, 43.3569),
"arménie": (40.0691, 45.0382),
"australie": (-25.2744, 133.7751),
"nouvelle-zélande": (-40.9006, 174.8860)
}

REGION_COUNTRY_HINTS = {
    "france": [
        "bordeaux",
        "bourgogne",
        "champagne",
        "loire",
        "alsace",
        "languedoc",
        "provence",
        "côtes du rhône",
        "cote du rhone",
        "beaujolais",
        "sud-ouest",
    ],
    "italie": ["piémont", "toscane", "sicile", "veneto", "piemonte"],
    "espagne": ["rioja", "ribera", "priorat", "andalousie"],
    "portugal": ["douro", "alentejo", "dao"],
    "allemagne": ["mosel", "pfalz", "baden"],
    "etats-unis": ["napa", "sonoma", "californie", "washington"],
    "argentine": ["mendoza", "patagonie"],
    "chili": ["casablanca", "maipo"],
    "australie": ["barossa", "mclaren", "margaret river"],
    "nouvelle-zélande": ["marlborough", "central otago"],
    "afrique du sud": ["stellenbosch", "paarl"],
}


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


def _extract_guardian_window(wine: Wine) -> tuple[int, int] | None:
    """Extracts an aging recommendation window (min_years, max_years)."""

    for insight in wine.insights:
        content = insight.content or ""
        lowered = content.lower()
        if not lowered:
            continue
        if not any(
            keyword in lowered
            for keyword in [
                "garde",
                "vieillissement",
                "apogée",
                "apogee",
                "consommer",
                "boire",
            ]
        ):
            continue

        span_match = YEAR_SPAN_PATTERN.search(content)
        if span_match:
            min_years = int(span_match.group(1))
            max_years = int(span_match.group(2))
            if min_years > max_years:
                min_years, max_years = max_years, min_years
            return min_years, max_years

        single_match = YEAR_SINGLE_PATTERN.search(content)
        if single_match:
            value = int(single_match.group(1))
            return value, value

    return None


def _classify_wine_maturity(wine: Wine, current_year: int) -> str:
    """Return the maturity state for the given wine."""

    year = wine.extra_attributes.get("year") if wine.extra_attributes else None
    if not year:
        return "à maturité"

    try:
        vintage_year = int(year)
    except (TypeError, ValueError):
        return "à maturité"

    age = max(current_year - vintage_year, 0)
    window = _extract_guardian_window(wine)

    if window:
        min_years, max_years = window
        if age < min_years:
            return "trop jeune"
        if age > max_years:
            return "en déclin"
        if max_years > min_years:
            progress = (age - min_years) / (max_years - min_years)
            return "à maturité" if progress < 0.5 else "dans l'apogée"
        return "dans l'apogée"

    if age < 3:
        return "trop jeune"
    if age < 6:
        return "à maturité"
    if age < 12:
        return "dans l'apogée"
    return "en déclin"


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


def _parse_purchase_price(wine: Wine) -> float | None:
    """Read purchase price from the wine extra attributes when available."""

    extras = wine.extra_attributes or {}
    candidate_keys = [
        "purchase_price",
        "price_paid",
        "prix_achat",
        "prix_achat_unitaire",
        "prix",
    ]

    for key in candidate_keys:
        raw_value = extras.get(key)
        if raw_value is None:
            continue
        if isinstance(raw_value, (int, float)):
            value = float(raw_value)
        else:
            cleaned = str(raw_value).replace("€", "").strip()
            cleaned = cleaned.replace(",", ".")
            try:
                value = float(cleaned)
            except ValueError:
                price = _parse_price_from_text(str(raw_value))
                if price is None:
                    continue
                value = price
        if value >= 0:
            return value
    return None


def _infer_country(wine: Wine) -> str | None:
    """Infer the country of a wine from its attributes or region hints."""

    extras = wine.extra_attributes or {}
    for key in ("country", "pays", "origin", "origine"):
        value = extras.get(key)
        if value:
            return str(value)

    region = extras.get("region")
    if region:
        lowered_region = region.lower()
        for country_key, hints in REGION_COUNTRY_HINTS.items():
            if any(hint in lowered_region for hint in hints):
                return country_key
    return None


def _normalize_country_key(name: str) -> str:
    return name.strip().lower()


def _shift_month(date: datetime, offset: int) -> datetime:
    """Shift a date by a number of months, preserving the day as 1."""

    year = date.year + (date.month - 1 + offset) // 12
    month = (date.month - 1 + offset) % 12 + 1
    return datetime(year, month, 1)


def _month_key(date: datetime) -> str:
    return date.strftime("%Y-%m")


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


def _build_month_series(month_count: int = 12) -> list[datetime]:
    """Return a list of month starts for the last `month_count` months."""

    now = datetime.now()
    current_month = datetime(now.year, now.month, 1)
    start = _shift_month(current_month, -(month_count - 1))
    return [_shift_month(start, idx) for idx in range(month_count)]


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


@main_bp.route('/alcools', methods=['GET'])
@login_required
def all_alcohols():
    """Affiche l'ensemble des alcools regroupés par cave dans une vue moderne."""

    cellars = (
        Cellar.query.options(selectinload(Cellar.category))
        .order_by(Cellar.name.asc())
        .all()
    )

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

    wines_by_cellar: dict[int, list[Wine]] = {cellar.id: [] for cellar in cellars}
    unassigned_wines: list[Wine] = []

    for wine in wines:
        if wine.cellar_id and wine.cellar_id in wines_by_cellar:
            wines_by_cellar[wine.cellar_id].append(wine)
        else:
            unassigned_wines.append(wine)

    cellar_views: list[dict[str, object]] = []
    for cellar in cellars:
        cellar_wines = wines_by_cellar.get(cellar.id, [])
        total_quantity = sum(wine.quantity or 0 for wine in cellar_wines)
        unique_categories = sorted(
            {
                wine.subcategory.category.name
                if wine.subcategory and wine.subcategory.category
                else 'Non catégorisé'
                for wine in cellar_wines
            }
        )

        cellar_views.append(
            {
                'cellar': cellar,
                'wines': cellar_wines,
                'total_quantity': total_quantity,
                'reference_count': len(cellar_wines),
                'unique_categories': unique_categories,
            }
        )

    orphan_summary = None
    if unassigned_wines:
        orphan_summary = {
            'total_quantity': sum(wine.quantity or 0 for wine in unassigned_wines),
            'unique_categories': sorted(
                {
                    wine.subcategory.category.name
                    if wine.subcategory and wine.subcategory.category
                    else 'Non catégorisé'
                    for wine in unassigned_wines
                }
            ),
        }

    total_bottles = sum(wine.quantity or 0 for wine in wines)
    category_breakdown: dict[str, int] = defaultdict(int)
    for wine in wines:
        if wine.subcategory and wine.subcategory.category:
            label = f"{wine.subcategory.category.name} — {wine.subcategory.name}"
        elif wine.subcategory:
            label = wine.subcategory.name
        else:
            label = 'Non catégorisé'
        category_breakdown[label] += wine.quantity or 0

    top_categories = sorted(
        category_breakdown.items(), key=lambda item: item[1], reverse=True
    )[:6]

    overview = {
        'total_cellars': len(cellars),
        'total_references': len(wines),
        'total_bottles': total_bottles,
        'distinct_categories': len(category_breakdown),
    }

    return render_template(
        'all_alcohols.html',
        cellar_views=cellar_views,
        overview=overview,
        top_categories=top_categories,
        unassigned_wines=unassigned_wines,
        orphan_summary=orphan_summary,
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


@main_bp.route('/stats', methods=['GET'])
@login_required
def statistics():
    """Render a detailed analytics dashboard for the wine cellar."""

    wines = (
        Wine.query.options(
            selectinload(Wine.cellar),
            selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
            selectinload(Wine.insights),
            selectinload(Wine.consumptions),
        )
        .filter(Wine.quantity >= 0)
        .all()
    )

    total_current_stock = sum(wine.quantity or 0 for wine in wines)
    current_year = datetime.now().year

    maturity_counts: dict[str, int] = defaultdict(int)
    for wine in wines:
        if (wine.quantity or 0) <= 0:
            continue
        state = _classify_wine_maturity(wine, current_year)
        maturity_counts[state] += wine.quantity or 0

    category_distribution: dict[str, int] = defaultdict(int)
    subcategory_distribution: dict[str, int] = defaultdict(int)
    country_distribution: dict[str, int] = defaultdict(int)

    total_invested = 0.0
    total_purchase_units = 0
    estimated_value_total = 0.0
    total_consumed_all_time = 0
    gain_candidates: list[dict[str, object]] = []

    for wine in wines:
        quantity = wine.quantity or 0
        if quantity < 0:
            quantity = 0

        if wine.subcategory and wine.subcategory.category:
            category_name = wine.subcategory.category.name
        else:
            category_name = "Non catégorisé"
        category_distribution[category_name] += quantity

        if wine.subcategory:
            sub_label = f"{category_name} — {wine.subcategory.name}"
        else:
            sub_label = f"{category_name} — Sans sous-catégorie"
        subcategory_distribution[sub_label] += quantity

        country = _infer_country(wine)
        if country:
            country_distribution[_normalize_country_key(country)] += quantity

        purchase_price = _parse_purchase_price(wine)
        estimated_price = _estimate_wine_price(wine)

        if purchase_price is not None:
            total_invested += purchase_price * max(quantity, 0)
            total_purchase_units += max(quantity, 0)

        if estimated_price is not None:
            estimated_value_total += estimated_price * max(quantity, 0)

        if purchase_price is not None and estimated_price is not None:
            delta = (estimated_price - purchase_price) * max(quantity, 0)
            gain_candidates.append(
                {
                    "wine": wine,
                    "delta": delta,
                    "purchase": purchase_price,
                    "current": estimated_price,
                }
            )

        total_consumed_all_time += sum(
            consumption.quantity or 0 for consumption in wine.consumptions
        )

    gain_candidates.sort(key=lambda item: item["delta"], reverse=True)
    top_gains = gain_candidates[:5]

    average_purchase_price = (
        (total_invested / total_purchase_units) if total_purchase_units else None
    )

    theoretical_value = estimated_value_total if estimated_value_total > 0 else None
    plus_minus_value = (
        (theoretical_value - total_invested)
        if theoretical_value is not None and total_invested > 0
        else None
    )

    months = _build_month_series(12)
    month_labels = [month.strftime("%b %Y") for month in months]
    month_keys = [_month_key(month) for month in months]
    month_index = {key: idx for idx, key in enumerate(month_keys)}

    additions_by_month = [0 for _ in months]
    consumption_by_month = [0 for _ in months]

    if wines:
        first_month_start = months[0]
        consumptions = (
            WineConsumption.query.filter(
                WineConsumption.consumed_at >= first_month_start
            ).all()
        )
    else:
        consumptions = []

    for consumption in consumptions:
        if not consumption.consumed_at:
            continue
        key = _month_key(datetime(consumption.consumed_at.year, consumption.consumed_at.month, 1))
        idx = month_index.get(key)
        if idx is not None:
            consumption_by_month[idx] += consumption.quantity or 0

    for wine in wines:
        if not getattr(wine, "created_at", None):
            continue
        key = _month_key(datetime(wine.created_at.year, wine.created_at.month, 1))
        idx = month_index.get(key)
        if idx is None:
            continue
        consumed_total = sum(consumption.quantity or 0 for consumption in wine.consumptions)
        initial_quantity = (wine.quantity or 0) + consumed_total
        additions_by_month[idx] += initial_quantity

    stock_by_month = []
    running_stock = total_current_stock
    for idx in reversed(range(len(months))):
        stock_by_month.append(running_stock)
        running_stock -= additions_by_month[idx]
        running_stock += consumption_by_month[idx]
    stock_by_month = list(reversed(stock_by_month))

    map_markers: list[dict[str, object]] = []
    for country_key, total in country_distribution.items():
        coords = COUNTRY_COORDINATES.get(country_key)
        if not coords:
            continue
        map_markers.append(
            {
                "country": country_key.title(),
                "lat": coords[0],
                "lng": coords[1],
                "total": total,
            }
        )

    return render_template(
        'statistics.html',
        maturity_counts=dict(maturity_counts),
        category_distribution=dict(category_distribution),
        subcategory_distribution=dict(subcategory_distribution),
        map_markers=map_markers,
        total_invested=total_invested if total_invested > 0 else None,
        average_purchase_price=average_purchase_price,
        theoretical_value=theoretical_value,
        plus_minus_value=plus_minus_value,
        top_gains=top_gains,
        format_currency=_format_currency,
        months_labels=month_labels,
        additions_by_month=additions_by_month,
        consumption_by_month=consumption_by_month,
        stock_by_month=stock_by_month,
        maturity_order=["trop jeune", "à maturité", "dans l'apogée", "en déclin"],
        total_current_stock=total_current_stock,
    )
