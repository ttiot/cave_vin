"""Blueprint pour l'authentification."""

from collections import defaultdict
from time import time
from datetime import datetime, date, timedelta
from calendar import monthrange

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    session,
    jsonify,
)
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from sqlalchemy import func

from werkzeug.security import check_password_hash, generate_password_hash

from openai import OpenAI, OpenAIError

from app.models import User, AICallLog, db


auth_bp = Blueprint('auth', __name__)

_login_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion."""
    next_url = request.args.get('next')

    if request.method == 'POST':
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        now = time()
        attempts = _login_attempts[client_ip]
        _login_attempts[client_ip] = [ts for ts in attempts if now - ts < WINDOW_SECONDS]

        if len(_login_attempts[client_ip]) >= MAX_ATTEMPTS:
            current_app.logger.warning("Trop de tentatives de connexion pour %s", client_ip)
            flash("Trop de tentatives. Réessayez dans quelques minutes.")
            return render_template('login.html', next_url=next_url), 429

        username = request.form['username']
        password = request.form['password']
        next_url = request.form.get('next') or next_url
        remember_me = bool(request.form.get('remember_me'))
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=remember_me)
            session.pop('impersonator_id', None)
            _login_attempts.pop(client_ip, None)

            if not next_url or urlparse(next_url).netloc != '':
                next_url = url_for('main.index')

            return redirect(next_url)

        flash("Identifiants incorrects.")
        _login_attempts[client_ip].append(now)

    return render_template('login.html', next_url=next_url)


@auth_bp.route('/logout')
@login_required
def logout():
    """Déconnexion de l'utilisateur."""
    logout_user()
    session.pop('impersonator_id', None)
    return redirect(url_for('auth.login'))


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Page de changement de mot de passe."""
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Vérifier le mot de passe actuel
        if not check_password_hash(current_user.password, current_password):
            flash("Mot de passe actuel incorrect.")
            return render_template('change_password.html')
        
        # Vérifier que les nouveaux mots de passe correspondent
        if new_password != confirm_password:
            flash("Les nouveaux mots de passe ne correspondent pas.")
            return render_template('change_password.html')
        
        # Vérifier la longueur du nouveau mot de passe
        if len(new_password) < 6:
            flash("Le nouveau mot de passe doit contenir au moins 6 caractères.")
            return render_template('change_password.html')
        
        # Mettre à jour le mot de passe
        current_user.password = generate_password_hash(new_password)
        current_user.has_temporary_password = False
        db.session.commit()
        
        flash("Mot de passe changé avec succès.")
        return redirect(url_for('main.index'))
    
    return render_template('change_password.html')


@auth_bp.route('/settings/openai', methods=['GET', 'POST'])
@login_required
def openai_settings():
    """Page de gestion de la clé OpenAI personnelle de l'utilisateur."""
    user = current_user
    
    # Récupérer les statistiques d'utilisation de l'utilisateur
    from sqlalchemy import func
    from datetime import datetime
    
    # Stats du mois en cours
    current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_stats = db.session.query(
        func.count(AICallLog.id).label('total_calls'),
        func.sum(AICallLog.input_tokens).label('total_input_tokens'),
        func.sum(AICallLog.output_tokens).label('total_output_tokens'),
        func.sum(AICallLog.estimated_cost_usd).label('total_cost'),
    ).filter(
        AICallLog.user_id == user.id,
        AICallLog.created_at >= current_month_start,
    ).first()
    
    # Derniers appels
    recent_calls = AICallLog.query.filter_by(user_id=user.id).order_by(
        AICallLog.created_at.desc()
    ).limit(10).all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save':
            api_key = request.form.get('api_key', '').strip()
            
            if api_key:
                # Valider la clé en testant la connexion
                try:
                    test_client = OpenAI(api_key=api_key)
                    # Test simple pour vérifier la clé
                    test_client.models.list()
                    
                    # Sauvegarder la clé
                    user.set_openai_api_key(api_key)
                    db.session.commit()
                    flash("Clé API OpenAI enregistrée avec succès.", "success")
                except OpenAIError as e:
                    flash(f"Clé API invalide : {e}", "danger")
                except Exception as e:
                    current_app.logger.error("Erreur lors du test de la clé OpenAI: %s", e)
                    flash("Erreur lors de la validation de la clé API.", "danger")
            else:
                flash("Veuillez entrer une clé API.", "warning")
                
        elif action == 'delete':
            user.openai_api_key_encrypted = None
            db.session.commit()
            flash("Clé API OpenAI supprimée. La clé globale sera utilisée.", "info")
    
    return render_template(
        'settings/openai.html',
        has_custom_key=user.has_custom_openai_key(),
        monthly_stats=monthly_stats,
        recent_calls=recent_calls,
    )


@auth_bp.route('/settings/openai/test', methods=['POST'])
@login_required
def test_openai_key():
    """Teste la clé OpenAI personnelle de l'utilisateur."""
    user = current_user
    
    if not user.has_custom_openai_key():
        flash("Aucune clé API personnelle configurée.", "warning")
        return redirect(url_for('auth.openai_settings'))
    
    api_key = user.get_openai_api_key()
    if not api_key:
        flash("Impossible de récupérer la clé API.", "danger")
        return redirect(url_for('auth.openai_settings'))
    
    try:
        test_client = OpenAI(api_key=api_key)
        models = test_client.models.list()
        model_count = len(list(models))
        flash(f"Connexion réussie ! {model_count} modèles disponibles.", "success")
    except OpenAIError as e:
        flash(f"Erreur de connexion : {e}", "danger")
    except Exception as e:
        current_app.logger.error("Erreur lors du test de la clé OpenAI: %s", e)
        flash("Erreur inattendue lors du test.", "danger")
    
    return redirect(url_for('auth.openai_settings'))


@auth_bp.route('/settings/consumption')
@login_required
def my_consumption():
    """Page de consultation de la consommation IA de l'utilisateur."""
    user = current_user
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
    logs = AICallLog.query.filter(
        AICallLog.user_id == user.id,
        AICallLog.created_at >= start_datetime,
        AICallLog.created_at <= end_datetime,
    ).order_by(AICallLog.created_at.desc()).all()
    
    # Calculer les statistiques pour la période
    stats = db.session.query(
        func.count(AICallLog.id).label("total_calls"),
        func.sum(AICallLog.input_tokens).label("total_input_tokens"),
        func.sum(AICallLog.output_tokens).label("total_output_tokens"),
        func.sum(AICallLog.estimated_cost_usd).label("total_cost"),
        func.avg(AICallLog.duration_ms).label("avg_duration"),
    ).filter(
        AICallLog.user_id == user.id,
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
        AICallLog.user_id == user.id,
        AICallLog.created_at >= start_datetime,
        AICallLog.created_at <= end_datetime,
    ).group_by(AICallLog.call_type).all()
    
    # Préparer les données de consommation
    consumption_data = {
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
        'settings/consumption.html',
        logs=logs,
        consumption=consumption_data,
        start_date=start_date,
        end_date=end_date,
        timedelta=timedelta,
    )


@auth_bp.route('/settings/consumption/export')
@login_required
def export_my_consumption():
    """Exporter la consommation de l'utilisateur en JSON."""
    user = current_user
    now = datetime.utcnow()
    
    # Par défaut : mois en cours
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
        AICallLog.user_id == user.id,
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
