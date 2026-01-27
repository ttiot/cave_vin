"""Blueprint pour la gestion des tokens API."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)
from flask_login import login_required, current_user

from models import APIToken, APITokenUsage, User, db
from app.utils.decorators import admin_required


api_tokens_bp = Blueprint("api_tokens", __name__, url_prefix="/api-tokens")


@api_tokens_bp.route("/")
@login_required
def list_tokens():
    """Afficher la liste des tokens de l'utilisateur courant."""
    tokens = APIToken.query.filter_by(user_id=current_user.id).order_by(
        APIToken.created_at.desc()
    ).all()
    return render_template("api_tokens/list.html", tokens=tokens)


@api_tokens_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_token():
    """Créer un nouveau token API."""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        expires_days = request.form.get("expires_days", type=int)

        if not name:
            flash("Le nom du token est obligatoire.")
            return render_template("api_tokens/create.html")

        # Générer le token
        raw_token = secrets.token_hex(32)
        full_token = f"cv_{raw_token}"
        token_hash = hashlib.sha256(full_token.encode()).hexdigest()
        token_prefix = full_token[:11]  # "cv_" + 8 premiers caractères

        # Calculer la date d'expiration si spécifiée
        expires_at = None
        if expires_days and expires_days > 0:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)

        token = APIToken(
            user_id=current_user.id,
            name=name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            expires_at=expires_at,
        )
        db.session.add(token)
        db.session.commit()

        # Afficher le token une seule fois
        flash("Token créé avec succès. Copiez-le maintenant, il ne sera plus affiché.")
        return render_template(
            "api_tokens/created.html",
            token=token,
            full_token=full_token,
        )

    return render_template("api_tokens/create.html")


@api_tokens_bp.route("/<int:token_id>/revoke", methods=["POST"])
@login_required
def revoke_token(token_id: int):
    """Révoquer un token API."""
    token = APIToken.query.get_or_404(token_id)

    # Vérifier que l'utilisateur est propriétaire ou admin
    if token.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    token.is_active = False
    db.session.commit()
    flash("Le token a été révoqué.")
    
    if current_user.is_admin and token.user_id != current_user.id:
        return redirect(url_for("api_tokens.admin_list"))
    return redirect(url_for("api_tokens.list_tokens"))


@api_tokens_bp.route("/<int:token_id>/activate", methods=["POST"])
@login_required
def activate_token(token_id: int):
    """Réactiver un token API révoqué."""
    token = APIToken.query.get_or_404(token_id)

    # Vérifier que l'utilisateur est propriétaire ou admin
    if token.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    token.is_active = True
    db.session.commit()
    flash("Le token a été réactivé.")
    
    if current_user.is_admin and token.user_id != current_user.id:
        return redirect(url_for("api_tokens.admin_list"))
    return redirect(url_for("api_tokens.list_tokens"))


@api_tokens_bp.route("/<int:token_id>/delete", methods=["POST"])
@login_required
def delete_token(token_id: int):
    """Supprimer définitivement un token API."""
    token = APIToken.query.get_or_404(token_id)

    # Vérifier que l'utilisateur est propriétaire ou admin
    if token.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    db.session.delete(token)
    db.session.commit()
    flash("Le token a été supprimé définitivement.")
    
    if current_user.is_admin and token.user_id != current_user.id:
        return redirect(url_for("api_tokens.admin_list"))
    return redirect(url_for("api_tokens.list_tokens"))


# ============================================================================
# Routes d'administration
# ============================================================================


@api_tokens_bp.route("/admin")
@login_required
@admin_required
def admin_list():
    """Afficher tous les tokens (vue admin)."""
    tokens = APIToken.query.join(User).order_by(
        User.username.asc(),
        APIToken.created_at.desc()
    ).all()
    return render_template("api_tokens/admin_list.html", tokens=tokens)


@api_tokens_bp.route("/admin/<int:token_id>")
@login_required
@admin_required
def admin_token_detail(token_id: int):
    """Afficher les détails d'utilisation d'un token (vue admin)."""
    token = APIToken.query.get_or_404(token_id)
    
    # Récupérer les statistiques d'utilisation
    page = request.args.get("page", 1, type=int)
    per_page = 50
    
    usage_pagination = APITokenUsage.query.filter_by(token_id=token_id).order_by(
        APITokenUsage.timestamp.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    # Statistiques agrégées
    from sqlalchemy import func
    
    # Utilisation par heure (dernières 24h)
    last_24h = datetime.utcnow() - timedelta(hours=24)
    hourly_usage = db.session.query(
        func.strftime('%Y-%m-%d %H:00', APITokenUsage.timestamp).label('hour'),
        func.count(APITokenUsage.id).label('count')
    ).filter(
        APITokenUsage.token_id == token_id,
        APITokenUsage.timestamp >= last_24h
    ).group_by('hour').order_by('hour').all()
    
    # Utilisation par endpoint
    endpoint_usage = db.session.query(
        APITokenUsage.endpoint,
        APITokenUsage.method,
        func.count(APITokenUsage.id).label('count'),
        func.avg(APITokenUsage.response_time_ms).label('avg_response_time')
    ).filter(
        APITokenUsage.token_id == token_id
    ).group_by(
        APITokenUsage.endpoint,
        APITokenUsage.method
    ).order_by(func.count(APITokenUsage.id).desc()).limit(20).all()
    
    # Codes de statut
    status_codes = db.session.query(
        APITokenUsage.status_code,
        func.count(APITokenUsage.id).label('count')
    ).filter(
        APITokenUsage.token_id == token_id
    ).group_by(APITokenUsage.status_code).all()
    
    return render_template(
        "api_tokens/admin_detail.html",
        token=token,
        usage_pagination=usage_pagination,
        hourly_usage=hourly_usage,
        endpoint_usage=endpoint_usage,
        status_codes=status_codes,
    )


@api_tokens_bp.route("/admin/<int:token_id>/update-rate-limit", methods=["POST"])
@login_required
@admin_required
def update_rate_limit(token_id: int):
    """Mettre à jour la limite de requêtes d'un token."""
    token = APIToken.query.get_or_404(token_id)
    
    rate_limit = request.form.get("rate_limit", type=int)
    if rate_limit is None or rate_limit < 1:
        flash("La limite de requêtes doit être un nombre positif.")
        return redirect(url_for("api_tokens.admin_token_detail", token_id=token_id))
    
    token.rate_limit = rate_limit
    db.session.commit()
    flash(f"La limite de requêtes a été mise à jour à {rate_limit} req/heure.")
    return redirect(url_for("api_tokens.admin_token_detail", token_id=token_id))
