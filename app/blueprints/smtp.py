"""Blueprint pour la gestion de la configuration SMTP."""

from __future__ import annotations

from datetime import datetime, timedelta

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
from sqlalchemy import func

from app.models import SMTPConfig, EmailLog, User, db
from app.utils.decorators import admin_required
from services.email_service import test_smtp_connection, send_test_email, is_email_configured


smtp_bp = Blueprint("smtp", __name__, url_prefix="/admin/smtp")


@smtp_bp.route("/")
@login_required
@admin_required
def index():
    """Page principale de configuration SMTP."""
    configs = SMTPConfig.query.order_by(SMTPConfig.is_default.desc(), SMTPConfig.name.asc()).all()
    
    # Statistiques des emails
    total_emails = EmailLog.query.count()
    emails_sent = EmailLog.query.filter_by(status=EmailLog.STATUS_SENT).count()
    emails_failed = EmailLog.query.filter_by(status=EmailLog.STATUS_FAILED).count()
    
    # Emails des 7 derniers jours
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_emails = EmailLog.query.filter(EmailLog.created_at >= seven_days_ago).count()
    
    return render_template(
        "admin/smtp/index.html",
        configs=configs,
        total_emails=total_emails,
        emails_sent=emails_sent,
        emails_failed=emails_failed,
        recent_emails=recent_emails,
        email_configured=is_email_configured(),
    )


@smtp_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def create():
    """Créer une nouvelle configuration SMTP."""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        host = (request.form.get("host") or "").strip()
        port = request.form.get("port", type=int) or 587
        username = (request.form.get("username") or "").strip() or None
        password = (request.form.get("password") or "").strip() or None
        # Convertir "1"/"0" en booléen (pas juste vérifier si non vide)
        use_tls = request.form.get("use_tls", "0") == "1"
        use_ssl = request.form.get("use_ssl", "0") == "1"
        sender_email = (request.form.get("sender_email") or "").strip()
        sender_name = (request.form.get("sender_name") or "").strip() or None
        timeout = request.form.get("timeout", type=int) or 30
        is_default = bool(request.form.get("is_default"))
        
        # Validation
        errors = []
        if not name:
            errors.append("Le nom est obligatoire.")
        if not host:
            errors.append("L'hôte SMTP est obligatoire.")
        if not sender_email:
            errors.append("L'adresse email d'expédition est obligatoire.")
        if use_tls and use_ssl:
            errors.append("Vous ne pouvez pas activer TLS et SSL en même temps.")
        
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("admin/smtp/create.html")
        
        # Si c'est la configuration par défaut, retirer le statut des autres
        if is_default:
            SMTPConfig.query.update({SMTPConfig.is_default: False})
        
        config = SMTPConfig(
            name=name,
            host=host,
            port=port,
            username=username,
            use_tls=use_tls,
            use_ssl=use_ssl,
            sender_email=sender_email,
            sender_name=sender_name,
            timeout=timeout,
            is_default=is_default,
            is_active=True,
        )
        
        # Chiffrer le mot de passe si fourni
        if password:
            config.set_password(password)
        
        db.session.add(config)
        db.session.commit()
        
        flash(f"Configuration SMTP '{name}' créée avec succès.", "success")
        return redirect(url_for("smtp.index"))
    
    return render_template("admin/smtp/create.html")


@smtp_bp.route("/<int:config_id>")
@login_required
@admin_required
def detail(config_id: int):
    """Détails d'une configuration SMTP."""
    config = SMTPConfig.query.get_or_404(config_id)
    
    # Derniers emails envoyés avec cette config
    recent_emails = EmailLog.query.filter_by(smtp_config_id=config_id).order_by(
        EmailLog.created_at.desc()
    ).limit(20).all()
    
    return render_template(
        "admin/smtp/detail.html",
        config=config,
        recent_emails=recent_emails,
    )


@smtp_bp.route("/<int:config_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(config_id: int):
    """Modifier une configuration SMTP."""
    config = SMTPConfig.query.get_or_404(config_id)
    
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        host = (request.form.get("host") or "").strip()
        port = request.form.get("port", type=int) or 587
        username = (request.form.get("username") or "").strip() or None
        password = (request.form.get("password") or "").strip()
        # Convertir "1"/"0" en booléen (pas juste vérifier si non vide)
        use_tls = request.form.get("use_tls", "0") == "1"
        use_ssl = request.form.get("use_ssl", "0") == "1"
        sender_email = (request.form.get("sender_email") or "").strip()
        sender_name = (request.form.get("sender_name") or "").strip() or None
        timeout = request.form.get("timeout", type=int) or 30
        is_default = bool(request.form.get("is_default"))
        is_active = bool(request.form.get("is_active"))
        
        # Validation
        errors = []
        if not name:
            errors.append("Le nom est obligatoire.")
        if not host:
            errors.append("L'hôte SMTP est obligatoire.")
        if not sender_email:
            errors.append("L'adresse email d'expédition est obligatoire.")
        if use_tls and use_ssl:
            errors.append("Vous ne pouvez pas activer TLS et SSL en même temps.")
        
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("admin/smtp/edit.html", config=config)
        
        # Si c'est la configuration par défaut, retirer le statut des autres
        if is_default and not config.is_default:
            SMTPConfig.query.filter(SMTPConfig.id != config_id).update({SMTPConfig.is_default: False})
        
        config.name = name
        config.host = host
        config.port = port
        config.username = username
        config.use_tls = use_tls
        config.use_ssl = use_ssl
        config.sender_email = sender_email
        config.sender_name = sender_name
        config.timeout = timeout
        config.is_default = is_default
        config.is_active = is_active
        
        # Mettre à jour le mot de passe si fourni
        if password:
            config.set_password(password)
        
        db.session.commit()
        
        flash(f"Configuration SMTP '{name}' mise à jour.", "success")
        return redirect(url_for("smtp.detail", config_id=config_id))
    
    return render_template("admin/smtp/edit.html", config=config)


@smtp_bp.route("/<int:config_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(config_id: int):
    """Supprimer une configuration SMTP."""
    config = SMTPConfig.query.get_or_404(config_id)
    name = config.name
    
    db.session.delete(config)
    db.session.commit()
    
    flash(f"Configuration SMTP '{name}' supprimée.", "success")
    return redirect(url_for("smtp.index"))


@smtp_bp.route("/<int:config_id>/set-default", methods=["POST"])
@login_required
@admin_required
def set_default(config_id: int):
    """Définir une configuration comme configuration par défaut."""
    config = SMTPConfig.query.get_or_404(config_id)
    
    # Retirer le statut par défaut des autres configurations
    SMTPConfig.query.update({SMTPConfig.is_default: False})
    
    config.is_default = True
    db.session.commit()
    
    flash(f"'{config.name}' est maintenant la configuration par défaut.", "success")
    return redirect(url_for("smtp.index"))


@smtp_bp.route("/<int:config_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_active(config_id: int):
    """Activer/désactiver une configuration SMTP."""
    config = SMTPConfig.query.get_or_404(config_id)
    
    config.is_active = not config.is_active
    db.session.commit()
    
    status = "activée" if config.is_active else "désactivée"
    flash(f"Configuration '{config.name}' {status}.", "success")
    return redirect(url_for("smtp.index"))


@smtp_bp.route("/<int:config_id>/test", methods=["POST"])
@login_required
@admin_required
def test_connection(config_id: int):
    """Tester la connexion SMTP."""
    config = SMTPConfig.query.get_or_404(config_id)
    
    result = test_smtp_connection(config)
    
    if result["success"]:
        flash(f"Connexion au serveur SMTP '{config.host}' réussie !", "success")
    else:
        flash(f"Échec de la connexion : {result['error']}", "error")
    
    return redirect(url_for("smtp.detail", config_id=config_id))


@smtp_bp.route("/<int:config_id>/send-test", methods=["POST"])
@login_required
@admin_required
def send_test(config_id: int):
    """Envoyer un email de test."""
    config = SMTPConfig.query.get_or_404(config_id)
    
    to_email = (request.form.get("to_email") or "").strip()
    
    if not to_email:
        flash("Veuillez spécifier une adresse email de destination.", "error")
        return redirect(url_for("smtp.detail", config_id=config_id))
    
    result = send_test_email(config, to_email)
    
    if result["success"]:
        flash(f"Email de test envoyé à {to_email} avec succès !", "success")
    else:
        flash(f"Échec de l'envoi : {result['error']}", "error")
    
    return redirect(url_for("smtp.detail", config_id=config_id))


# ============================================================================
# Logs d'emails
# ============================================================================


@smtp_bp.route("/logs")
@login_required
@admin_required
def email_logs():
    """Liste des logs d'emails."""
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "").strip()
    config_id = request.args.get("config_id", type=int)
    days = request.args.get("days", 7, type=int)
    per_page = 50
    
    query = EmailLog.query
    
    if status:
        query = query.filter(EmailLog.status == status)
    
    if config_id:
        query = query.filter(EmailLog.smtp_config_id == config_id)
    
    if days > 0:
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(EmailLog.created_at >= since)
    
    logs = query.order_by(EmailLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    configs = SMTPConfig.query.order_by(SMTPConfig.name.asc()).all()
    
    return render_template(
        "admin/smtp/logs.html",
        logs=logs,
        configs=configs,
        current_status=status,
        current_config_id=config_id,
        current_days=days,
    )


@smtp_bp.route("/logs/<int:log_id>")
@login_required
@admin_required
def email_log_detail(log_id: int):
    """Détails d'un log d'email."""
    log = EmailLog.query.get_or_404(log_id)
    return render_template("admin/smtp/log_detail.html", log=log)


# ============================================================================
# API pour les statistiques
# ============================================================================


@smtp_bp.route("/api/stats")
@login_required
@admin_required
def api_stats():
    """API pour les statistiques d'emails."""
    # Statistiques par jour (30 derniers jours)
    daily_stats = []
    for i in range(29, -1, -1):
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        
        sent = EmailLog.query.filter(
            EmailLog.created_at >= day_start,
            EmailLog.created_at < day_end,
            EmailLog.status == EmailLog.STATUS_SENT
        ).count()
        
        failed = EmailLog.query.filter(
            EmailLog.created_at >= day_start,
            EmailLog.created_at < day_end,
            EmailLog.status == EmailLog.STATUS_FAILED
        ).count()
        
        daily_stats.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "label": day_start.strftime("%d/%m"),
            "sent": sent,
            "failed": failed,
        })
    
    return jsonify({
        "daily_stats": daily_stats,
    })
