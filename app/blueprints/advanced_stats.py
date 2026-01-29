"""Blueprint pour les statistiques avancées et rapports."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from flask import Blueprint, render_template, request, jsonify, Response
from flask_login import login_required, current_user
from sqlalchemy.orm import selectinload
from sqlalchemy import func, extract

from app.models import (
    AlcoholSubcategory,
    Wine,
    WineConsumption,
    db,
)


advanced_stats_bp = Blueprint("advanced_stats", __name__, url_prefix="/stats")


# ============================================================================
# Helpers
# ============================================================================


SEASON_MONTHS = {
    "Printemps": [3, 4, 5],
    "Été": [6, 7, 8],
    "Automne": [9, 10, 11],
    "Hiver": [12, 1, 2],
}


def _get_season(month: int) -> str:
    """Retourne la saison pour un mois donné."""
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    return "Inconnu"


def _format_currency(value: float) -> str:
    """Formate une valeur décimale en euros selon une présentation française."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _parse_price_from_extras(wine: Wine) -> float | None:
    """Extrait le prix d'achat depuis les attributs extra."""
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
            return float(raw_value)
        cleaned = str(raw_value).replace("€", "").strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            continue
    return None


# ============================================================================
# Routes
# ============================================================================


@advanced_stats_bp.route("/trends")
@login_required
def consumption_trends():
    """Analyse des tendances de consommation par saison."""
    owner_id = current_user.owner_id
    
    # Récupérer les consommations des 2 dernières années
    two_years_ago = datetime.now() - timedelta(days=730)
    
    consumptions = (
        WineConsumption.query
        .options(selectinload(WineConsumption.wine).selectinload(Wine.subcategory))
        .filter(
            WineConsumption.user_id == owner_id,
            WineConsumption.consumed_at >= two_years_ago,
        )
        .order_by(WineConsumption.consumed_at.desc())
        .all()
    )
    
    # Analyse par saison
    season_data: dict[str, dict[str, Any]] = {
        season: {"count": 0, "categories": defaultdict(int), "months": defaultdict(int)}
        for season in SEASON_MONTHS.keys()
    }
    
    # Analyse par mois
    monthly_data: dict[str, int] = defaultdict(int)
    
    # Analyse par jour de la semaine
    weekday_data: dict[int, int] = defaultdict(int)
    weekday_names = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    
    # Analyse par catégorie
    category_trends: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    for consumption in consumptions:
        if not consumption.consumed_at:
            continue
            
        month = consumption.consumed_at.month
        year = consumption.consumed_at.year
        season = _get_season(month)
        quantity = consumption.quantity or 1
        
        # Par saison
        season_data[season]["count"] += quantity
        season_data[season]["months"][month] += quantity
        
        # Par mois (format YYYY-MM)
        month_key = consumption.consumed_at.strftime("%Y-%m")
        monthly_data[month_key] += quantity
        
        # Par jour de la semaine
        weekday = consumption.consumed_at.weekday()
        weekday_data[weekday] += quantity
        
        # Par catégorie et saison
        if consumption.wine and consumption.wine.subcategory:
            cat_name = consumption.wine.subcategory.category.name if consumption.wine.subcategory.category else "Autre"
            category_trends[cat_name][season] += quantity
            season_data[season]["categories"][cat_name] += quantity
    
    # Préparer les données pour les graphiques
    season_labels = list(SEASON_MONTHS.keys())
    season_values = [season_data[s]["count"] for s in season_labels]
    
    # Top catégories par saison
    top_categories_by_season = {}
    for season in season_labels:
        cats = season_data[season]["categories"]
        if cats:
            sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
            top_categories_by_season[season] = sorted_cats
    
    # Données mensuelles triées
    sorted_months = sorted(monthly_data.keys())[-12:]  # 12 derniers mois
    monthly_labels = sorted_months
    monthly_values = [monthly_data[m] for m in sorted_months]
    
    # Données par jour de la semaine
    weekday_labels = weekday_names
    weekday_values = [weekday_data[i] for i in range(7)]
    
    # Calcul des moyennes
    total_consumption = sum(c.quantity or 1 for c in consumptions)
    avg_per_month = total_consumption / max(len(monthly_data), 1)
    avg_per_week = total_consumption / max(len(consumptions) / 4, 1) if consumptions else 0
    
    # Tendance (comparaison avec période précédente)
    now = datetime.now()
    six_months_ago = now - timedelta(days=180)
    one_year_ago = now - timedelta(days=365)
    
    recent_count = sum(
        c.quantity or 1 for c in consumptions
        if c.consumed_at and c.consumed_at >= six_months_ago
    )
    previous_count = sum(
        c.quantity or 1 for c in consumptions
        if c.consumed_at and one_year_ago <= c.consumed_at < six_months_ago
    )
    
    if previous_count > 0:
        trend_percent = ((recent_count - previous_count) / previous_count) * 100
    else:
        trend_percent = 0
    
    return render_template(
        "advanced_stats/trends.html",
        season_labels=season_labels,
        season_values=season_values,
        season_data=season_data,
        top_categories_by_season=top_categories_by_season,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
        weekday_labels=weekday_labels,
        weekday_values=weekday_values,
        total_consumption=total_consumption,
        avg_per_month=round(avg_per_month, 1),
        trend_percent=round(trend_percent, 1),
        category_trends=dict(category_trends),
    )


@advanced_stats_bp.route("/predictions")
@login_required
def stock_predictions():
    """Prédiction de consommation et estimation d'épuisement du stock."""
    owner_id = current_user.owner_id
    
    # Récupérer les vins en stock
    wines = (
        Wine.query
        .options(
            selectinload(Wine.cellar),
            selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
            selectinload(Wine.consumptions),
        )
        .filter(Wine.user_id == owner_id, Wine.quantity > 0)
        .all()
    )
    
    # Récupérer l'historique de consommation
    one_year_ago = datetime.now() - timedelta(days=365)
    consumptions = (
        WineConsumption.query
        .filter(
            WineConsumption.user_id == owner_id,
            WineConsumption.consumed_at >= one_year_ago,
        )
        .all()
    )
    
    # Calculer le taux de consommation moyen
    total_consumed_year = sum(c.quantity or 1 for c in consumptions)
    months_with_data = min(12, max(1, len(set(
        c.consumed_at.strftime("%Y-%m") for c in consumptions if c.consumed_at
    ))))
    
    avg_consumption_per_month = total_consumed_year / months_with_data if months_with_data > 0 else 0
    
    # Stock actuel
    total_stock = sum(w.quantity or 0 for w in wines)
    
    # Estimation d'épuisement
    if avg_consumption_per_month > 0:
        months_until_empty = total_stock / avg_consumption_per_month
        estimated_empty_date = datetime.now() + timedelta(days=months_until_empty * 30)
    else:
        months_until_empty = None
        estimated_empty_date = None
    
    # Analyse par catégorie
    category_predictions: dict[str, dict[str, Any]] = {}
    
    # Grouper les vins par catégorie
    wines_by_category: dict[str, list[Wine]] = defaultdict(list)
    for wine in wines:
        if wine.subcategory and wine.subcategory.category:
            cat_name = wine.subcategory.category.name
        else:
            cat_name = "Non catégorisé"
        wines_by_category[cat_name].append(wine)
    
    # Grouper les consommations par catégorie
    consumption_by_category: dict[str, int] = defaultdict(int)
    for consumption in consumptions:
        if consumption.wine and consumption.wine.subcategory and consumption.wine.subcategory.category:
            cat_name = consumption.wine.subcategory.category.name
        else:
            cat_name = "Non catégorisé"
        consumption_by_category[cat_name] += consumption.quantity or 1
    
    for cat_name, cat_wines in wines_by_category.items():
        cat_stock = sum(w.quantity or 0 for w in cat_wines)
        cat_consumed = consumption_by_category.get(cat_name, 0)
        cat_avg = cat_consumed / months_with_data if months_with_data > 0 else 0
        
        if cat_avg > 0:
            cat_months = cat_stock / cat_avg
            cat_empty_date = datetime.now() + timedelta(days=cat_months * 30)
        else:
            cat_months = None
            cat_empty_date = None
        
        category_predictions[cat_name] = {
            "stock": cat_stock,
            "consumed_year": cat_consumed,
            "avg_per_month": round(cat_avg, 1),
            "months_until_empty": round(cat_months, 1) if cat_months else None,
            "estimated_empty_date": cat_empty_date,
            "status": _get_stock_status(cat_months) if cat_months else "stable",
        }
    
    # Alertes de stock bas
    low_stock_alerts = []
    for cat_name, pred in category_predictions.items():
        if pred["months_until_empty"] and pred["months_until_empty"] < 3:
            low_stock_alerts.append({
                "category": cat_name,
                "months_left": pred["months_until_empty"],
                "stock": pred["stock"],
            })
    
    low_stock_alerts.sort(key=lambda x: x["months_left"])
    
    # Projection sur 12 mois
    projection_months = []
    projection_stock = []
    current_stock = total_stock
    
    for i in range(13):
        month_date = datetime.now() + timedelta(days=i * 30)
        projection_months.append(month_date.strftime("%b %Y"))
        projection_stock.append(max(0, round(current_stock)))
        current_stock -= avg_consumption_per_month
    
    return render_template(
        "advanced_stats/predictions.html",
        total_stock=total_stock,
        avg_consumption_per_month=round(avg_consumption_per_month, 1),
        months_until_empty=round(months_until_empty, 1) if months_until_empty else None,
        estimated_empty_date=estimated_empty_date,
        category_predictions=category_predictions,
        low_stock_alerts=low_stock_alerts,
        projection_months=projection_months,
        projection_stock=projection_stock,
        total_consumed_year=total_consumed_year,
    )


def _get_stock_status(months: float | None) -> str:
    """Retourne le statut du stock basé sur les mois restants."""
    if months is None:
        return "stable"
    if months < 1:
        return "critical"
    if months < 3:
        return "warning"
    if months < 6:
        return "attention"
    return "stable"


@advanced_stats_bp.route("/annual-report")
@login_required
def annual_report():
    """Rapport annuel synthétique."""
    owner_id = current_user.owner_id
    year = request.args.get("year", datetime.now().year, type=int)
    
    # Dates de l'année
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)
    
    # Vins ajoutés cette année
    wines_added = (
        Wine.query
        .options(
            selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
            selectinload(Wine.cellar),
        )
        .filter(
            Wine.user_id == owner_id,
            Wine.created_at >= year_start,
            Wine.created_at <= year_end,
        )
        .all()
    )
    
    # Consommations de l'année
    consumptions = (
        WineConsumption.query
        .options(selectinload(WineConsumption.wine))
        .filter(
            WineConsumption.user_id == owner_id,
            WineConsumption.consumed_at >= year_start,
            WineConsumption.consumed_at <= year_end,
        )
        .all()
    )
    
    # Stock actuel
    current_wines = (
        Wine.query
        .options(selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category))
        .filter(Wine.user_id == owner_id, Wine.quantity > 0)
        .all()
    )
    
    # Statistiques d'ajouts
    total_added = len(wines_added)
    total_added_quantity = sum(w.quantity or 1 for w in wines_added)
    
    # Valeur des ajouts
    total_invested = 0.0
    for wine in wines_added:
        price = _parse_price_from_extras(wine)
        if price:
            total_invested += price * (wine.quantity or 1)
    
    # Statistiques de consommation
    total_consumed = sum(c.quantity or 1 for c in consumptions)
    
    # Répartition par mois
    monthly_added: dict[int, int] = defaultdict(int)
    monthly_consumed: dict[int, int] = defaultdict(int)
    monthly_invested: dict[int, float] = defaultdict(float)
    
    for wine in wines_added:
        if wine.created_at:
            month = wine.created_at.month
            monthly_added[month] += wine.quantity or 1
            price = _parse_price_from_extras(wine)
            if price:
                monthly_invested[month] += price * (wine.quantity or 1)
    
    for consumption in consumptions:
        if consumption.consumed_at:
            month = consumption.consumed_at.month
            monthly_consumed[month] += consumption.quantity or 1
    
    # Préparer les données mensuelles
    month_labels = [calendar.month_abbr[i] for i in range(1, 13)]
    added_by_month = [monthly_added.get(i, 0) for i in range(1, 13)]
    consumed_by_month = [monthly_consumed.get(i, 0) for i in range(1, 13)]
    invested_by_month = [round(monthly_invested.get(i, 0), 2) for i in range(1, 13)]
    
    # Top catégories ajoutées
    category_added: dict[str, int] = defaultdict(int)
    for wine in wines_added:
        if wine.subcategory and wine.subcategory.category:
            cat_name = wine.subcategory.category.name
        else:
            cat_name = "Non catégorisé"
        category_added[cat_name] += wine.quantity or 1
    
    top_categories_added = sorted(category_added.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Top catégories consommées
    category_consumed: dict[str, int] = defaultdict(int)
    for consumption in consumptions:
        if consumption.wine and consumption.wine.subcategory and consumption.wine.subcategory.category:
            cat_name = consumption.wine.subcategory.category.name
        else:
            cat_name = "Non catégorisé"
        category_consumed[cat_name] += consumption.quantity or 1
    
    top_categories_consumed = sorted(category_consumed.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Valeur actuelle du stock
    current_stock_value = 0.0
    current_stock_count = sum(w.quantity or 0 for w in current_wines)
    for wine in current_wines:
        price = _parse_price_from_extras(wine)
        if price:
            current_stock_value += price * (wine.quantity or 0)
    
    # Années disponibles pour le sélecteur
    oldest_wine = Wine.query.filter(Wine.user_id == owner_id).order_by(Wine.created_at.asc()).first()
    oldest_consumption = WineConsumption.query.filter(WineConsumption.user_id == owner_id).order_by(WineConsumption.consumed_at.asc()).first()
    
    min_year = datetime.now().year
    if oldest_wine and oldest_wine.created_at:
        min_year = min(min_year, oldest_wine.created_at.year)
    if oldest_consumption and oldest_consumption.consumed_at:
        min_year = min(min_year, oldest_consumption.consumed_at.year)
    
    available_years = list(range(min_year, datetime.now().year + 1))
    
    # Bilan net
    net_change = total_added_quantity - total_consumed
    
    return render_template(
        "advanced_stats/annual_report.html",
        year=year,
        available_years=available_years,
        total_added=total_added,
        total_added_quantity=total_added_quantity,
        total_consumed=total_consumed,
        total_invested=total_invested,
        net_change=net_change,
        month_labels=month_labels,
        added_by_month=added_by_month,
        consumed_by_month=consumed_by_month,
        invested_by_month=invested_by_month,
        top_categories_added=top_categories_added,
        top_categories_consumed=top_categories_consumed,
        current_stock_count=current_stock_count,
        current_stock_value=current_stock_value,
        format_currency=_format_currency,
    )


@advanced_stats_bp.route("/annual-report/export")
@login_required
def export_annual_report():
    """Exporte le rapport annuel en CSV."""
    owner_id = current_user.owner_id
    year = request.args.get("year", datetime.now().year, type=int)
    
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)
    
    # Données
    wines_added = Wine.query.filter(
        Wine.user_id == owner_id,
        Wine.created_at >= year_start,
        Wine.created_at <= year_end,
    ).all()
    
    consumptions = WineConsumption.query.filter(
        WineConsumption.user_id == owner_id,
        WineConsumption.consumed_at >= year_start,
        WineConsumption.consumed_at <= year_end,
    ).all()
    
    # Générer le CSV
    lines = [
        f"Rapport annuel {year}",
        "",
        "=== AJOUTS ===",
        "Date,Nom,Quantité,Prix unitaire",
    ]
    
    for wine in wines_added:
        price = _parse_price_from_extras(wine) or ""
        date = wine.created_at.strftime("%Y-%m-%d") if wine.created_at else ""
        lines.append(f'{date},"{wine.name}",{wine.quantity or 1},{price}')
    
    lines.extend([
        "",
        "=== CONSOMMATIONS ===",
        "Date,Nom,Quantité,Commentaire",
    ])
    
    for consumption in consumptions:
        date = consumption.consumed_at.strftime("%Y-%m-%d") if consumption.consumed_at else ""
        comment = (consumption.comment or "").replace('"', '""')
        lines.append(f'{date},"{consumption.snapshot_name}",{consumption.quantity or 1},"{comment}"')
    
    csv_content = "\n".join(lines)
    
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rapport_annuel_{year}.csv"},
    )


@advanced_stats_bp.route("/calendar-export")
@login_required
def export_guard_calendar():
    """Exporte un calendrier iCal avec les dates de garde optimales."""
    owner_id = current_user.owner_id
    
    wines = (
        Wine.query
        .options(selectinload(Wine.insights))
        .filter(Wine.user_id == owner_id, Wine.quantity > 0)
        .all()
    )
    
    # Générer le fichier iCal
    ical_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Cave à Vin//Calendrier de Garde//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Cave à Vin - Dates de garde",
    ]
    
    import re
    YEAR_SPAN_PATTERN = re.compile(r"(\d+)\s*(?:à|-|–)\s*(\d+)\s*ans?", re.IGNORECASE)
    
    current_year = datetime.now().year
    
    for wine in wines:
        year = wine.extra_attributes.get("year") if wine.extra_attributes else None
        if not year:
            continue
        
        try:
            vintage_year = int(year)
        except (TypeError, ValueError):
            continue
        
        # Chercher les recommandations de garde dans les insights
        min_years = None
        max_years = None
        
        for insight in wine.insights:
            content = insight.content or ""
            if not any(kw in content.lower() for kw in ["garde", "vieillissement", "apogée", "boire"]):
                continue
            
            match = YEAR_SPAN_PATTERN.search(content)
            if match:
                min_years = int(match.group(1))
                max_years = int(match.group(2))
                break
        
        if min_years is None:
            continue
        
        # Créer les événements
        optimal_start = vintage_year + min_years
        optimal_end = vintage_year + max_years
        
        if optimal_start <= current_year + 10:  # Ne pas créer d'événements trop lointains
            # Événement de début de période optimale
            if optimal_start >= current_year:
                start_date = datetime(optimal_start, 1, 1)
                uid = f"wine-{wine.id}-start@cave-vin"
                ical_lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTART;VALUE=DATE:{start_date.strftime('%Y%m%d')}",
                    f"SUMMARY:🍷 {wine.name} - Début période optimale",
                    f"DESCRIPTION:Le vin {wine.name} ({vintage_year}) entre dans sa période de consommation optimale.",
                    "END:VEVENT",
                ])
            
            # Événement de fin de période optimale
            if optimal_end >= current_year and optimal_end <= current_year + 10:
                end_date = datetime(optimal_end, 12, 31)
                uid = f"wine-{wine.id}-end@cave-vin"
                ical_lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTART;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
                    f"SUMMARY:⚠️ {wine.name} - Fin période optimale",
                    f"DESCRIPTION:Le vin {wine.name} ({vintage_year}) arrive en fin de période de consommation optimale. Pensez à le déguster !",
                    "END:VEVENT",
                ])
    
    ical_lines.append("END:VCALENDAR")
    ical_content = "\r\n".join(ical_lines)
    
    return Response(
        ical_content,
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=cave_vin_garde.ics"},
    )
