"""Tâches planifiées pour les rapports et notifications automatiques.

Ce module contient les fonctions métier exécutées par le scheduler.
Ces fonctions sont conçues pour être appelées depuis un process séparé
(scheduler.py) et non depuis les workers Gunicorn.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from flask import render_template
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from app.models import User

logger = logging.getLogger(__name__)


def get_wines_to_consume(user_id: int, limit: int = 10) -> list[dict]:
    """Récupère les vins à consommer pour un utilisateur.
    
    Utilise une logique basée sur :
    1. Le champ 'apogee' dans extra_attributes (si renseigné)
    2. Les insights de garde générés par l'IA
    3. L'âge du vin comme heuristique par défaut
    
    Args:
        user_id: ID de l'utilisateur (ou du compte propriétaire)
        limit: Nombre maximum de vins à retourner
    
    Returns:
        Liste de dictionnaires avec les informations des vins à consommer,
        triés par score d'urgence décroissant
    """
    from app.models import Wine, User
    
    user = User.query.get(user_id)
    if not user:
        return []
    
    # Utiliser l'owner_id pour les sous-comptes
    owner_id = user.owner_id
    current_year = datetime.now().year
    
    wines_to_consume = []
    
    # Récupérer tous les vins de l'utilisateur avec une quantité > 0
    # Inclure les insights pour l'analyse
    wines = Wine.query.options(
        selectinload(Wine.insights),
        selectinload(Wine.cellar),
        selectinload(Wine.subcategory),
    ).filter(
        Wine.user_id == owner_id,
        Wine.quantity > 0
    ).all()
    
    for wine in wines:
        extra = wine.extra_attributes or {}
        year = extra.get('year')
        
        # Calculer l'âge du vin si possible
        wine_age = None
        if year:
            try:
                wine_age = current_year - int(year)
            except (ValueError, TypeError):
                pass
        
        urgency_score = 0
        garde_info = None
        recommended_years = None
        
        # Méthode 1: Vérifier le champ apogee explicite
        apogee_year = extra.get('apogee')
        if apogee_year:
            try:
                apogee = int(apogee_year)
                if apogee < current_year:
                    # Dépassé l'apogée - urgent
                    years_past = current_year - apogee
                    urgency_score = min(100, 80 + years_past * 5)
                elif apogee == current_year:
                    # À l'apogée cette année - optimal
                    urgency_score = 70
                elif apogee <= current_year + 2:
                    # Apogée dans les 2 prochaines années
                    urgency_score = 50
            except (ValueError, TypeError):
                pass
        
        # Méthode 2: Analyser les insights de garde (si pas déjà un score élevé)
        if urgency_score < 50:
            for insight in wine.insights:
                content = insight.content or ""
                content_lower = content.lower()
                
                # Chercher des informations de garde
                if any(keyword in content_lower for keyword in [
                    'garde', 'garder', 'conserver', 'vieillissement',
                    'apogée', 'apogee', 'boire', 'consommer'
                ]):
                    garde_info = content
                    
                    # Extraire une fenêtre de garde (ex: "3 à 5 ans")
                    years_match = re.search(r'(\d+)\s*(?:à|-)\s*(\d+)\s*ans?', content_lower)
                    if years_match and wine_age is not None:
                        min_years = int(years_match.group(1))
                        max_years = int(years_match.group(2))
                        recommended_years = (min_years, max_years)
                        
                        if wine_age >= max_years:
                            # Dépassé la fenêtre de garde
                            urgency_score = max(urgency_score, 100)
                        elif wine_age >= min_years:
                            # Dans la fenêtre de garde
                            progress = (wine_age - min_years) / (max_years - min_years)
                            urgency_score = max(urgency_score, 50 + int(progress * 50))
                        else:
                            # Pas encore dans la fenêtre
                            urgency_score = max(urgency_score, int((wine_age / min_years) * 30))
                    
                    # Mots-clés d'urgence
                    if any(kw in content_lower for kw in ['maintenant', 'immédiatement', 'rapidement', 'bientôt']):
                        urgency_score = max(urgency_score, 80)
                    
                    # Mots-clés d'apogée
                    if any(kw in content_lower for kw in ['apogée', 'optimal', 'parfait']):
                        urgency_score = max(urgency_score, 60)
        
        # Méthode 3: Heuristique basée sur l'âge (si toujours pas de score)
        if urgency_score == 0 and wine_age is not None and wine_age > 0:
            if wine_age >= 15:
                urgency_score = 70
            elif wine_age >= 10:
                urgency_score = 50
            elif wine_age >= 5:
                urgency_score = 30
        
        # Ajouter le vin s'il a un score d'urgence significatif
        if urgency_score >= 30:
            # Déterminer le niveau d'urgence textuel
            if urgency_score >= 80:
                urgency = "urgent"
            elif urgency_score >= 50:
                urgency = "optimal"
            else:
                urgency = "bientôt"
            
            wines_to_consume.append({
                "id": wine.id,
                "name": wine.name,
                "year": year,
                "region": extra.get('region'),
                "apogee": apogee_year,
                "quantity": wine.quantity,
                "cellar_name": wine.cellar.name if wine.cellar else None,
                "urgency": urgency,
                "urgency_score": urgency_score,
                "subcategory": wine.subcategory.name if wine.subcategory else None,
                "garde_info": garde_info,
            })
    
    # Trier par score d'urgence décroissant
    wines_to_consume.sort(key=lambda w: w["urgency_score"], reverse=True)
    
    return wines_to_consume[:limit]


def get_recent_activity(user_id: int, days: int = 7) -> dict:
    """Récupère l'activité récente (entrées/sorties) pour un utilisateur.
    
    Args:
        user_id: ID de l'utilisateur (ou du compte propriétaire)
        days: Nombre de jours à regarder en arrière
    
    Returns:
        Dictionnaire avec les entrées et sorties récentes
    """
    from app.models import Wine, WineConsumption, User
    
    user = User.query.get(user_id)
    if not user:
        return {"entries": [], "consumptions": [], "summary": {}}
    
    owner_id = user.owner_id
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Entrées récentes (vins ajoutés)
    recent_wines = Wine.query.filter(
        Wine.user_id == owner_id,
        Wine.created_at >= cutoff_date
    ).order_by(Wine.created_at.desc()).all()
    
    entries = []
    for wine in recent_wines:
        extra = wine.extra_attributes or {}
        entries.append({
            "id": wine.id,
            "name": wine.name,
            "year": extra.get('year'),
            "region": extra.get('region'),
            "quantity": wine.quantity,
            "cellar_name": wine.cellar.name if wine.cellar else None,
            "added_at": wine.created_at,
            "subcategory": wine.subcategory.name if wine.subcategory else None,
        })
    
    # Sorties récentes (consommations)
    recent_consumptions = WineConsumption.query.filter(
        WineConsumption.user_id == owner_id,
        WineConsumption.consumed_at >= cutoff_date
    ).order_by(WineConsumption.consumed_at.desc()).all()
    
    consumptions = []
    for consumption in recent_consumptions:
        consumptions.append({
            "id": consumption.id,
            "wine_id": consumption.wine_id,
            "name": consumption.snapshot_name,
            "year": consumption.snapshot_year,
            "region": consumption.snapshot_region,
            "cellar_name": consumption.snapshot_cellar,
            "quantity": consumption.quantity,
            "consumed_at": consumption.consumed_at,
            "comment": consumption.comment,
        })
    
    # Résumé
    total_entries = sum(e["quantity"] for e in entries)
    total_consumptions = sum(c["quantity"] for c in consumptions)
    
    return {
        "entries": entries,
        "consumptions": consumptions,
        "summary": {
            "total_entries": total_entries,
            "total_consumptions": total_consumptions,
            "net_change": total_entries - total_consumptions,
            "period_days": days,
        }
    }


def get_cellar_statistics(user_id: int) -> dict:
    """Récupère les statistiques globales des caves pour un utilisateur.
    
    Args:
        user_id: ID de l'utilisateur (ou du compte propriétaire)
    
    Returns:
        Dictionnaire avec les statistiques des caves
    """
    from app.models import Wine, Cellar, User
    from sqlalchemy import func
    
    user = User.query.get(user_id)
    if not user:
        return {}
    
    owner_id = user.owner_id
    
    # Total des bouteilles
    total_bottles = Wine.query.filter(
        Wine.user_id == owner_id
    ).with_entities(func.sum(Wine.quantity)).scalar() or 0
    
    # Nombre de références (vins distincts avec quantité > 0)
    total_references = Wine.query.filter(
        Wine.user_id == owner_id,
        Wine.quantity > 0
    ).count()
    
    # Statistiques par cave
    cellars = Cellar.query.filter(Cellar.user_id == owner_id).all()
    cellar_stats = []
    for cellar in cellars:
        bottles_in_cellar = Wine.query.filter(
            Wine.cellar_id == cellar.id
        ).with_entities(func.sum(Wine.quantity)).scalar() or 0
        
        cellar_stats.append({
            "id": cellar.id,
            "name": cellar.name,
            "capacity": cellar.capacity,
            "bottles": bottles_in_cellar,
            "fill_rate": round(bottles_in_cellar / cellar.capacity * 100, 1) if cellar.capacity > 0 else 0,
        })
    
    return {
        "total_bottles": total_bottles,
        "total_references": total_references,
        "cellars": cellar_stats,
    }


def build_weekly_report_data(user_id: int) -> dict:
    """Construit les données complètes pour le rapport hebdomadaire.
    
    Args:
        user_id: ID de l'utilisateur
    
    Returns:
        Dictionnaire avec toutes les données du rapport
    """
    from app.models import User
    
    user = User.query.get(user_id)
    if not user:
        return {}
    
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "wines_to_consume": get_wines_to_consume(user_id),
        "recent_activity": get_recent_activity(user_id, days=7),
        "statistics": get_cellar_statistics(user_id),
        "generated_at": datetime.utcnow(),
        "report_period": {
            "start": datetime.utcnow() - timedelta(days=7),
            "end": datetime.utcnow(),
        }
    }


def render_weekly_report_html(report_data: dict) -> str:
    """Génère le HTML du rapport hebdomadaire.
    
    Args:
        report_data: Données du rapport (depuis build_weekly_report_data)
    
    Returns:
        HTML du rapport
    """
    return render_template("emails/weekly_report.html", **report_data)


def render_weekly_report_text(report_data: dict) -> str:
    """Génère la version texte du rapport hebdomadaire.
    
    Args:
        report_data: Données du rapport (depuis build_weekly_report_data)
    
    Returns:
        Texte du rapport
    """
    lines = []
    user = report_data.get("user", {})
    stats = report_data.get("statistics", {})
    activity = report_data.get("recent_activity", {})
    wines_to_consume = report_data.get("wines_to_consume", [])
    
    lines.append(f"🍷 Rapport hebdomadaire - Cave à Vin")
    lines.append(f"Bonjour {user.get('username', 'Utilisateur')} !")
    lines.append("")
    
    # Statistiques globales
    lines.append("📊 VOS CAVES EN UN COUP D'ŒIL")
    lines.append(f"  • Total bouteilles : {stats.get('total_bottles', 0)}")
    lines.append(f"  • Références : {stats.get('total_references', 0)}")
    lines.append("")
    
    # Activité récente
    summary = activity.get("summary", {})
    lines.append("📈 ACTIVITÉ DE LA SEMAINE")
    lines.append(f"  • Entrées : +{summary.get('total_entries', 0)} bouteilles")
    lines.append(f"  • Sorties : -{summary.get('total_consumptions', 0)} bouteilles")
    lines.append(f"  • Variation nette : {summary.get('net_change', 0):+d} bouteilles")
    lines.append("")
    
    # Vins à consommer en priorité
    if wines_to_consume:
        lines.append("🍾 À CONSOMMER EN PRIORITÉ")
        lines.append("  (Basé sur les informations de garde et l'âge du millésime)")
        lines.append("")
        
        for wine in wines_to_consume[:5]:
            year_str = f" — {wine.get('year')}" if wine.get('year') else ""
            urgency_score = wine.get('urgency_score', 0)
            lines.append(f"  • {wine['name']}{year_str}")
            lines.append(f"    Urgence: {urgency_score}%")
            if wine.get('cellar_name'):
                lines.append(f"    Cave: {wine['cellar_name']}")
            if wine.get('subcategory'):
                lines.append(f"    Type: {wine['subcategory']}")
            lines.append("")
        
        # Résumé
        urgent_count = len([w for w in wines_to_consume if w["urgency"] == "urgent"])
        optimal_count = len([w for w in wines_to_consume if w["urgency"] == "optimal"])
        if urgent_count > 0 or optimal_count > 0:
            summary_parts = []
            if urgent_count > 0:
                summary_parts.append(f"{urgent_count} vin{'s' if urgent_count > 1 else ''} urgent{'s' if urgent_count > 1 else ''}")
            if optimal_count > 0:
                summary_parts.append(f"{optimal_count} à l'apogée")
            lines.append(f"  Résumé: {' • '.join(summary_parts)}")
            lines.append("")
    else:
        lines.append("🍾 À CONSOMMER EN PRIORITÉ")
        lines.append("  Aucun vin ne nécessite une attention particulière pour le moment.")
        lines.append("")
    
    lines.append("---")
    lines.append("Cet email a été envoyé automatiquement par Cave à Vin.")
    
    return "\n".join(lines)


def send_weekly_report_to_user(user_id: int) -> dict:
    """Envoie le rapport hebdomadaire à un utilisateur.
    
    Args:
        user_id: ID de l'utilisateur
    
    Returns:
        Résultat de l'envoi (success, error)
    """
    from app.models import User
    from services.email_service import send_email_to_user
    
    user = User.query.get(user_id)
    if not user:
        return {"success": False, "error": "Utilisateur non trouvé"}
    
    if not user.email:
        return {"success": False, "error": "Utilisateur sans email"}
    
    # Construire le rapport
    report_data = build_weekly_report_data(user_id)
    
    # Générer le contenu
    html_content = render_weekly_report_html(report_data)
    text_content = render_weekly_report_text(report_data)
    
    # Envoyer l'email
    result = send_email_to_user(
        user=user,
        subject="🍷 Votre rapport hebdomadaire - Cave à Vin",
        body_html=html_content,
        body_text=text_content,
        template_name="weekly_report",
    )
    
    if result["success"]:
        logger.info(f"Rapport hebdomadaire envoyé à {user.email}")
    else:
        logger.error(f"Échec envoi rapport à {user.email}: {result.get('error')}")
    
    return result


def send_weekly_reports_to_all_users() -> dict:
    """Envoie le rapport hebdomadaire à tous les utilisateurs avec email.
    
    Cette fonction est appelée par le scheduler chaque semaine.
    
    Returns:
        Résumé des envois (sent, failed, errors)
    """
    from app.models import User
    from services.email_service import is_email_configured
    
    if not is_email_configured():
        logger.warning("SMTP non configuré, rapports hebdomadaires non envoyés")
        return {"sent": 0, "failed": 0, "errors": ["SMTP non configuré"]}
    
    # Récupérer tous les utilisateurs principaux avec email
    # (pas les sous-comptes, ils partagent les données du parent)
    users = User.query.filter(
        User.email.isnot(None),
        User.parent_id.is_(None)  # Exclure les sous-comptes
    ).all()
    
    result = {"sent": 0, "failed": 0, "errors": []}
    
    for user in users:
        try:
            send_result = send_weekly_report_to_user(user.id)
            if send_result["success"]:
                result["sent"] += 1
            else:
                result["failed"] += 1
                result["errors"].append(f"{user.email}: {send_result.get('error')}")
        except Exception as e:
            result["failed"] += 1
            result["errors"].append(f"{user.email}: {str(e)}")
            logger.exception(f"Erreur lors de l'envoi du rapport à {user.email}")
    
    logger.info(
        f"Rapports hebdomadaires envoyés: {result['sent']} succès, {result['failed']} échecs"
    )
    
    return result


def cleanup_old_email_logs(days: int = 90) -> int:
    """Nettoie les anciens logs d'emails.
    
    Args:
        days: Nombre de jours à conserver
    
    Returns:
        Nombre de logs supprimés
    """
    from app.models import EmailLog, db
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    deleted = EmailLog.query.filter(
        EmailLog.created_at < cutoff_date
    ).delete()
    
    db.session.commit()
    
    logger.info(f"Nettoyage: {deleted} logs d'emails supprimés (> {days} jours)")
    
    return deleted


def cleanup_old_activity_logs(days: int = 180) -> int:
    """Nettoie les anciens logs d'activité.
    
    Args:
        days: Nombre de jours à conserver
    
    Returns:
        Nombre de logs supprimés
    """
    from app.models import ActivityLog, db
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    deleted = ActivityLog.query.filter(
        ActivityLog.created_at < cutoff_date
    ).delete()
    
    db.session.commit()
    
    logger.info(f"Nettoyage: {deleted} logs d'activité supprimés (> {days} jours)")
    
    return deleted


def cleanup_old_api_usage_logs(days: int = 30) -> int:
    """Nettoie les anciens logs d'utilisation API.
    
    Args:
        days: Nombre de jours à conserver
    
    Returns:
        Nombre de logs supprimés
    """
    from app.models import APITokenUsage, db
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    deleted = APITokenUsage.query.filter(
        APITokenUsage.timestamp < cutoff_date
    ).delete()
    
    db.session.commit()
    
    logger.info(f"Nettoyage: {deleted} logs API supprimés (> {days} jours)")
    
    return deleted


def run_all_cleanup_tasks() -> dict:
    """Exécute toutes les tâches de nettoyage.
    
    Cette fonction est appelée par le scheduler périodiquement.
    
    Returns:
        Résumé des nettoyages effectués
    """
    result = {
        "email_logs": cleanup_old_email_logs(days=90),
        "activity_logs": cleanup_old_activity_logs(days=180),
        "api_usage_logs": cleanup_old_api_usage_logs(days=30),
    }
    
    logger.info(f"Nettoyage terminé: {result}")
    
    return result
