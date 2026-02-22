"""Blueprint pour la gestion de la configuration OpenAI par l'administrateur."""

from __future__ import annotations

from datetime import datetime, timedelta, date
from decimal import Decimal
from calendar import monthrange

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_login import login_required, current_user
from sqlalchemy import func, extract, and_

from app.models import db, User, OpenAIConfig, AICallLog, OpenAIPrompt
from app.utils.decorators import admin_required


openai_admin_bp = Blueprint("openai_admin", __name__, url_prefix="/admin/openai")


# ============================================================================
# Configuration OpenAI
# ============================================================================


@openai_admin_bp.route("/config", methods=["GET", "POST"])
@login_required
@admin_required
def config():
    """Gérer la configuration OpenAI globale."""
    
    openai_config = OpenAIConfig.get_or_create()
    
    if request.method == "POST":
        action = request.form.get("action", "save")
        
        if action == "save":
            # Mettre à jour la configuration
            api_key = request.form.get("api_key", "").strip()
            base_url = request.form.get("base_url", "").strip()
            default_model = request.form.get("default_model", "").strip()
            image_model = request.form.get("image_model", "").strip()
            source_name = request.form.get("source_name", "").strip()
            monthly_budget = request.form.get("monthly_budget", "").strip()
            is_active = bool(request.form.get("is_active"))
            
            # Mettre à jour la clé API seulement si fournie
            if api_key:
                openai_config.set_api_key(api_key)
            
            openai_config.base_url = base_url or "https://api.openai.com/v1"
            openai_config.default_model = default_model or "gpt-4o-mini"
            openai_config.image_model = image_model or None
            openai_config.source_name = source_name or "OpenAI"
            openai_config.is_active = is_active
            
            if monthly_budget:
                try:
                    openai_config.monthly_budget = Decimal(monthly_budget)
                except (ValueError, TypeError):
                    flash("Budget mensuel invalide.", "error")
                    return redirect(url_for("openai_admin.config"))
            else:
                openai_config.monthly_budget = None
            
            db.session.commit()
            flash("Configuration OpenAI mise à jour avec succès.", "success")
            return redirect(url_for("openai_admin.config"))
        
        elif action == "delete_key":
            openai_config.api_key_encrypted = None
            db.session.commit()
            flash("Clé API OpenAI supprimée.", "success")
            return redirect(url_for("openai_admin.config"))
        
        elif action == "test":
            # Tester la connexion à l'API OpenAI
            result = _test_openai_connection(openai_config)
            if result["success"]:
                flash(f"Connexion réussie ! Modèle testé : {result.get('model', 'N/A')}", "success")
            else:
                flash(f"Échec de la connexion : {result.get('error', 'Erreur inconnue')}", "error")
            return redirect(url_for("openai_admin.config"))
    
    # Récupérer les statistiques du mois en cours
    now = datetime.utcnow()
    monthly_stats = AICallLog.get_monthly_stats(now.year, now.month)
    
    # Récupérer les informations de budget local
    budget_info = _get_openai_budget_info(openai_config)
    
    return render_template(
        "admin/openai/config.html",
        config=openai_config,
        monthly_stats=monthly_stats,
        budget_info=budget_info,
    )


# ============================================================================
# Logs des appels IA
# ============================================================================


@openai_admin_bp.route("/logs")
@login_required
@admin_required
def logs():
    """Afficher les logs des appels IA."""
    
    # Filtres
    user_id = request.args.get("user_id", type=int)
    call_type = request.args.get("call_type", "").strip()
    status = request.args.get("status", "").strip()
    days = request.args.get("days", 30, type=int)
    page = request.args.get("page", 1, type=int)
    per_page = 50
    
    # Construire la requête
    query = AICallLog.query
    
    if user_id:
        query = query.filter(AICallLog.user_id == user_id)
    
    if call_type:
        query = query.filter(AICallLog.call_type == call_type)
    
    if status:
        query = query.filter(AICallLog.response_status == status)
    
    if days > 0:
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(AICallLog.created_at >= since)
    
    # Pagination
    logs_paginated = query.order_by(AICallLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Récupérer les utilisateurs pour le filtre
    users = User.query.order_by(User.username.asc()).all()
    
    # Récupérer les types d'appels distincts
    call_types = db.session.query(AICallLog.call_type).distinct().all()
    call_types = [c[0] for c in call_types if c[0]]
    
    # Statistiques rapides
    now = datetime.utcnow()
    monthly_stats = AICallLog.get_monthly_stats(now.year, now.month)
    
    return render_template(
        "admin/openai/logs.html",
        logs=logs_paginated,
        users=users,
        call_types=call_types,
        current_user_id=user_id,
        current_call_type=call_type,
        current_status=status,
        current_days=days,
        monthly_stats=monthly_stats,
    )


@openai_admin_bp.route("/logs/<int:log_id>")
@login_required
@admin_required
def log_detail(log_id: int):
    """Afficher le détail d'un log d'appel IA."""
    
    log = AICallLog.query.get_or_404(log_id)
    user = User.query.get(log.user_id)
    
    return render_template(
        "admin/openai/log_detail.html",
        log=log,
        user=user,
    )


@openai_admin_bp.route("/logs/user/<int:user_id>")
@login_required
@admin_required
def user_logs(user_id: int):
    """Afficher les logs d'appels IA d'un utilisateur spécifique."""
    
    user = User.query.get_or_404(user_id)
    page = request.args.get("page", 1, type=int)
    per_page = 50
    
    logs_paginated = AICallLog.query.filter_by(user_id=user_id).order_by(
        AICallLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    # Statistiques de l'utilisateur
    now = datetime.utcnow()
    user_monthly_cost = AICallLog.get_user_monthly_cost(user_id, now.year, now.month)
    
    total_calls = AICallLog.query.filter_by(user_id=user_id).count()
    total_cost = db.session.query(
        func.sum(AICallLog.estimated_cost_usd)
    ).filter(AICallLog.user_id == user_id).scalar() or Decimal("0")
    
    return render_template(
        "admin/openai/user_logs.html",
        user=user,
        logs=logs_paginated,
        user_monthly_cost=user_monthly_cost,
        total_calls=total_calls,
        total_cost=total_cost,
    )


# ============================================================================
# Statistiques
# ============================================================================


@openai_admin_bp.route("/statistics")
@login_required
@admin_required
def statistics():
    """Statistiques détaillées des appels IA."""
    
    now = datetime.utcnow()
    
    # Statistiques du mois en cours
    current_month_stats = AICallLog.get_monthly_stats(now.year, now.month)
    
    # Statistiques des 12 derniers mois
    monthly_history = []
    for i in range(11, -1, -1):
        month_date = now - timedelta(days=i * 30)
        stats = AICallLog.get_monthly_stats(month_date.year, month_date.month)
        stats["month_label"] = month_date.strftime("%b %Y")
        monthly_history.append(stats)
    
    # Top utilisateurs par coût
    top_users_by_cost = db.session.query(
        AICallLog.user_id,
        func.count(AICallLog.id).label("total_calls"),
        func.sum(AICallLog.estimated_cost_usd).label("total_cost"),
    ).group_by(AICallLog.user_id).order_by(
        func.sum(AICallLog.estimated_cost_usd).desc()
    ).limit(10).all()
    
    # Enrichir avec les noms d'utilisateurs
    top_users = []
    for row in top_users_by_cost:
        user = User.query.get(row.user_id)
        top_users.append({
            "user": user,
            "total_calls": row.total_calls,
            "total_cost": float(row.total_cost) if row.total_cost else 0,
        })
    
    # Configuration actuelle
    openai_config = OpenAIConfig.get_active()
    
    return render_template(
        "admin/openai/statistics.html",
        current_month_stats=current_month_stats,
        monthly_history=monthly_history,
        top_users=top_users,
        config=openai_config,
    )


@openai_admin_bp.route("/statistics/api")
@login_required
@admin_required
def statistics_api():
    """API pour les données de statistiques (pour les graphiques)."""
    
    now = datetime.utcnow()
    
    # Statistiques des 12 derniers mois
    monthly_history = []
    for i in range(11, -1, -1):
        month_date = now - timedelta(days=i * 30)
        stats = AICallLog.get_monthly_stats(month_date.year, month_date.month)
        stats["month_label"] = month_date.strftime("%b %Y")
        monthly_history.append(stats)
    
    return jsonify({
        "monthly_history": monthly_history,
    })


# ============================================================================
# Gestion des prompts
# ============================================================================


@openai_admin_bp.route("/prompts")
@login_required
@admin_required
def prompts():
    """Afficher et gérer les prompts configurables."""
    
    # Initialiser les prompts par défaut s'ils n'existent pas
    OpenAIPrompt.initialize_defaults()
    
    # Récupérer tous les prompts
    all_prompts = OpenAIPrompt.query.order_by(OpenAIPrompt.prompt_key).all()
    
    return render_template(
        "admin/openai/prompts.html",
        prompts=all_prompts,
    )


@openai_admin_bp.route("/prompts/<prompt_key>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_prompt(prompt_key: str):
    """Éditer un prompt spécifique."""
    
    prompt = OpenAIPrompt.query.filter_by(prompt_key=prompt_key).first_or_404()
    
    if request.method == "POST":
        action = request.form.get("action", "save")
        
        if action == "save":
            # Mettre à jour le prompt
            prompt.display_name = request.form.get("display_name", "").strip() or prompt.display_name
            prompt.description = request.form.get("description", "").strip() or None
            prompt.system_prompt = request.form.get("system_prompt", "").strip()
            prompt.user_prompt = request.form.get("user_prompt", "").strip()
            prompt.is_active = bool(request.form.get("is_active"))
            
            # Mettre à jour les paramètres si fournis
            # Copier le dict pour que SQLAlchemy détecte la mutation
            params = dict(prompt.parameters or {})

            max_output_tokens = request.form.get("max_output_tokens", "").strip()
            if max_output_tokens:
                try:
                    tokens = int(max_output_tokens)
                    params["max_output_tokens"] = tokens
                except (ValueError, TypeError):
                    flash("Nombre de tokens invalide.", "error")
                    return redirect(url_for("openai_admin.edit_prompt", prompt_key=prompt_key))

            # Paramètres de recherche web
            params["enable_web_search"] = bool(request.form.get("enable_web_search"))

            web_search_context_size = request.form.get("web_search_context_size", "medium").strip()
            if web_search_context_size in ("low", "medium", "high"):
                params["web_search_context_size"] = web_search_context_size
            else:
                params["web_search_context_size"] = "medium"

            # Réassigner pour que SQLAlchemy détecte le changement
            prompt.parameters = params
            
            # Mettre à jour le schéma JSON de réponse
            response_schema_str = request.form.get("response_schema", "").strip()
            if response_schema_str:
                try:
                    import json
                    response_schema = json.loads(response_schema_str)
                    # Vérification basique que c'est un objet
                    if not isinstance(response_schema, dict):
                        raise ValueError("Le schéma doit être un objet JSON")
                    prompt.response_schema = response_schema
                except (json.JSONDecodeError, ValueError) as e:
                    flash(f"Schéma JSON invalide : {str(e)}", "error")
                    return redirect(url_for("openai_admin.edit_prompt", prompt_key=prompt_key))
            else:
                # Si vide, on met à None (désactive le schéma structuré)
                prompt.response_schema = None
            
            db.session.commit()
            flash(f"Prompt '{prompt.display_name}' mis à jour avec succès.", "success")
            return redirect(url_for("openai_admin.prompts"))
        
        elif action == "reset":
            # Réinitialiser le prompt aux valeurs par défaut
            try:
                OpenAIPrompt.reset_to_default(prompt_key)
                flash(f"Prompt '{prompt.display_name}' réinitialisé aux valeurs par défaut.", "success")
            except ValueError as e:
                flash(str(e), "error")
            return redirect(url_for("openai_admin.edit_prompt", prompt_key=prompt_key))
    
    # Récupérer les valeurs par défaut pour comparaison
    default_values = OpenAIPrompt.DEFAULT_PROMPTS.get(prompt_key, {})
    
    return render_template(
        "admin/openai/prompt_edit.html",
        prompt=prompt,
        default_values=default_values,
    )


@openai_admin_bp.route("/prompts/<prompt_key>/reset", methods=["POST"])
@login_required
@admin_required
def reset_prompt(prompt_key: str):
    """Réinitialiser un prompt aux valeurs par défaut."""
    
    try:
        prompt = OpenAIPrompt.reset_to_default(prompt_key)
        flash(f"Prompt '{prompt.display_name}' réinitialisé aux valeurs par défaut.", "success")
    except ValueError as e:
        flash(str(e), "error")
    
    return redirect(url_for("openai_admin.prompts"))


@openai_admin_bp.route("/prompts/api/<prompt_key>")
@login_required
@admin_required
def get_prompt_api(prompt_key: str):
    """API pour récupérer un prompt."""
    
    prompt = OpenAIPrompt.query.filter_by(prompt_key=prompt_key).first()
    if not prompt:
        return jsonify({"error": "Prompt non trouvé"}), 404
    
    return jsonify(prompt.to_dict(include_schema=True))


@openai_admin_bp.route("/prompts/api/<prompt_key>/default")
@login_required
@admin_required
def get_prompt_default_api(prompt_key: str):
    """API pour récupérer les valeurs par défaut d'un prompt."""
    
    if prompt_key not in OpenAIPrompt.DEFAULT_PROMPTS:
        return jsonify({"error": "Prompt inconnu"}), 404
    
    return jsonify(OpenAIPrompt.DEFAULT_PROMPTS[prompt_key])


# ============================================================================
# Facturation utilisateur
# ============================================================================


@openai_admin_bp.route("/billing/user/<int:user_id>")
@login_required
@admin_required
def user_billing(user_id: int):
    """Afficher la facturation détaillée d'un utilisateur avec filtres de dates."""
    
    user = User.query.get_or_404(user_id)
    
    # Récupérer les paramètres de date
    now = datetime.utcnow()
    
    # Par défaut : mois en cours
    default_start = date(now.year, now.month, 1)
    _, last_day = monthrange(now.year, now.month)
    default_end = date(now.year, now.month, last_day)
    
    # Récupérer les dates depuis les paramètres
    start_date_str = request.args.get("start_date", "")
    end_date_str = request.args.get("end_date", "")
    
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        else:
            start_date = default_start
    except ValueError:
        start_date = default_start
    
    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        else:
            end_date = default_end
    except ValueError:
        end_date = default_end
    
    # Convertir en datetime pour les requêtes
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Récupérer les logs pour la période
    logs_query = AICallLog.query.filter(
        AICallLog.user_id == user_id,
        AICallLog.created_at >= start_datetime,
        AICallLog.created_at <= end_datetime,
    ).order_by(AICallLog.created_at.desc())
    
    logs = logs_query.all()
    
    # Calculer les statistiques pour la période
    stats = db.session.query(
        func.count(AICallLog.id).label("total_calls"),
        func.sum(AICallLog.input_tokens).label("total_input_tokens"),
        func.sum(AICallLog.output_tokens).label("total_output_tokens"),
        func.sum(AICallLog.estimated_cost_usd).label("total_cost"),
        func.avg(AICallLog.duration_ms).label("avg_duration"),
    ).filter(
        AICallLog.user_id == user_id,
        AICallLog.created_at >= start_datetime,
        AICallLog.created_at <= end_datetime,
    ).first()
    
    # Statistiques par type de service
    stats_by_type = db.session.query(
        AICallLog.call_type,
        func.count(AICallLog.id).label("count"),
        func.sum(AICallLog.estimated_cost_usd).label("cost"),
        func.sum(AICallLog.duration_ms).label("total_duration"),
    ).filter(
        AICallLog.user_id == user_id,
        AICallLog.created_at >= start_datetime,
        AICallLog.created_at <= end_datetime,
    ).group_by(AICallLog.call_type).all()
    
    # Préparer les données de facturation
    billing_data = {
        "period_start": start_date,
        "period_end": end_date,
        "total_calls": stats.total_calls or 0,
        "total_input_tokens": stats.total_input_tokens or 0,
        "total_output_tokens": stats.total_output_tokens or 0,
        "total_cost": float(stats.total_cost) if stats.total_cost else 0,
        "avg_duration_ms": float(stats.avg_duration) if stats.avg_duration else 0,
        "by_service": [
            {
                "service": s.call_type,
                "count": s.count,
                "cost": float(s.cost) if s.cost else 0,
                "total_duration_ms": s.total_duration or 0,
            }
            for s in stats_by_type
        ],
    }
    
    return render_template(
        "admin/openai/user_billing.html",
        user=user,
        logs=logs,
        billing=billing_data,
        start_date=start_date,
        end_date=end_date,
        timedelta=timedelta,
    )


@openai_admin_bp.route("/billing/user/<int:user_id>/export")
@login_required
@admin_required
def export_user_billing(user_id: int):
    """Exporter la facturation d'un utilisateur en JSON."""
    
    user = User.query.get_or_404(user_id)
    
    # Récupérer les paramètres de date
    now = datetime.utcnow()
    default_start = date(now.year, now.month, 1)
    _, last_day = monthrange(now.year, now.month)
    default_end = date(now.year, now.month, last_day)
    
    start_date_str = request.args.get("start_date", "")
    end_date_str = request.args.get("end_date", "")
    
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else default_start
    except ValueError:
        start_date = default_start
    
    try:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else default_end
    except ValueError:
        end_date = default_end
    
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Récupérer les logs
    logs = AICallLog.query.filter(
        AICallLog.user_id == user_id,
        AICallLog.created_at >= start_datetime,
        AICallLog.created_at <= end_datetime,
    ).order_by(AICallLog.created_at.asc()).all()
    
    # Calculer les totaux
    total_cost = sum(float(log.estimated_cost_usd) if log.estimated_cost_usd else 0 for log in logs)
    
    # Préparer les données d'export
    export_data = {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "summary": {
            "total_calls": len(logs),
            "total_cost_usd": round(total_cost, 6),
        },
        "calls": [
            {
                "id": log.id,
                "datetime": log.created_at.isoformat(),
                "service": log.call_type,
                "model": log.model,
                "duration_ms": log.duration_ms,
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
                "cost_usd": float(log.estimated_cost_usd) if log.estimated_cost_usd else 0,
                "status": log.response_status,
            }
            for log in logs
        ],
    }
    
    return jsonify(export_data)


# ============================================================================
# Helpers
# ============================================================================


def _test_openai_connection(config: OpenAIConfig) -> dict:
    """Teste la connexion à l'API OpenAI."""
    
    api_key = config.get_api_key()
    if not api_key:
        return {"success": False, "error": "Clé API non configurée"}
    
    base_url = config.base_url or "https://api.openai.com/v1"
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )
        
        # Tester avec une requête simple
        response = client.models.list()
        models = [m.id for m in response.data[:5]]
        
        return {
            "success": True,
            "model": config.default_model,
            "available_models": models,
        }
    
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _get_openai_budget_info(config: OpenAIConfig) -> dict:
    """Récupère les informations de budget calculées localement."""
    
    # Informations calculées localement
    now = datetime.utcnow()
    monthly_cost = AICallLog.get_global_monthly_cost(now.year, now.month)
    
    result = {
        "available": True,
        "monthly_usage": float(monthly_cost),
        "monthly_budget": float(config.monthly_budget) if config.monthly_budget else None,
        "budget_remaining": None,
        "budget_percent_used": None,
    }
    
    if config.monthly_budget:
        remaining = float(config.monthly_budget) - float(monthly_cost)
        result["budget_remaining"] = max(0, remaining)
        result["budget_percent_used"] = min(100, (float(monthly_cost) / float(config.monthly_budget)) * 100)
    
    return result
