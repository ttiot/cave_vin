"""Blueprint dédié aux fonctionnalités d'administration."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from flask_login import login_required, current_user, login_user
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from models import User, Wine, Cellar, WineConsumption, ActivityLog, UserSettings, db
from app.utils.decorators import admin_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def manage_users():
    """Afficher la liste des utilisateurs et permettre la création de comptes."""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        is_temporary = bool(request.form.get("temporary"))
        is_admin = bool(request.form.get("is_admin"))
        parent_id_str = request.form.get("parent_id", "").strip()

        # Déterminer le compte parent (si sous-compte)
        parent_id = None
        if parent_id_str and parent_id_str != "":
            try:
                parent_id = int(parent_id_str)
                # Vérifier que le parent existe et n'est pas lui-même un sous-compte
                parent_user = User.query.get(parent_id)
                if parent_user is None:
                    flash("Le compte parent sélectionné n'existe pas.")
                    return redirect(url_for("admin.manage_users"))
                if parent_user.is_sub_account:
                    flash("Un sous-compte ne peut pas être rattaché à un autre sous-compte.")
                    return redirect(url_for("admin.manage_users"))
            except ValueError:
                flash("ID de compte parent invalide.")
                return redirect(url_for("admin.manage_users"))

        if not username:
            flash("Le nom d'utilisateur est obligatoire.")
        elif not password:
            flash("Le mot de passe est obligatoire.")
        elif User.query.filter_by(username=username).first():
            flash("Ce nom d'utilisateur est déjà utilisé.")
        else:
            # Un sous-compte ne peut pas être administrateur
            if parent_id is not None:
                is_admin = False

            user = User(
                username=username,
                password=generate_password_hash(password),
                has_temporary_password=is_temporary,
                is_admin=is_admin,
                parent_id=parent_id,
            )
            db.session.add(user)
            db.session.commit()

            if parent_id is not None:
                flash(f"Sous-compte créé avec succès et rattaché à {parent_user.username}.")
            else:
                flash("Utilisateur créé avec succès.")
            return redirect(url_for("admin.manage_users"))

    # Récupérer tous les utilisateurs, triés par compte principal puis sous-comptes
    users = User.query.order_by(User.parent_id.asc().nullsfirst(), User.username.asc()).all()
    
    # Récupérer les comptes principaux pour le formulaire de création
    main_accounts = User.query.filter_by(parent_id=None).order_by(User.username.asc()).all()
    
    return render_template(
        "admin_users.html",
        users=users,
        main_accounts=main_accounts,
        is_impersonating=bool(session.get("impersonator_id")),
    )


@admin_bp.route("/users/<int:user_id>/update-role", methods=["POST"])
@login_required
@admin_required
def update_role(user_id: int):
    """Mettre à jour le rôle administrateur d'un utilisateur."""

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Vous ne pouvez pas modifier votre propre statut administrateur depuis cette page.")
        return redirect(url_for("admin.manage_users"))

    # Un sous-compte ne peut pas être administrateur
    if user.is_sub_account:
        flash("Un sous-compte ne peut pas être administrateur.")
        return redirect(url_for("admin.manage_users"))

    target_is_admin = bool(request.form.get("is_admin"))

    if not target_is_admin:
        remaining_admins = User.query.filter(User.id != user.id, User.is_admin == True).count()  # noqa: E712
        if remaining_admins == 0:
            flash("Impossible de retirer les droits administrateur : il doit rester au moins un administrateur.")
            return redirect(url_for("admin.manage_users"))

    user.is_admin = target_is_admin
    db.session.commit()
    flash("Les droits de l'utilisateur ont été mis à jour.")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<int:user_id>/update-parent", methods=["POST"])
@login_required
@admin_required
def update_parent(user_id: int):
    """Modifier le rattachement d'un utilisateur à un compte parent."""

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Vous ne pouvez pas modifier votre propre rattachement.")
        return redirect(url_for("admin.manage_users"))

    parent_id_str = request.form.get("parent_id", "").strip()

    # Déterminer le nouveau compte parent
    new_parent_id = None
    if parent_id_str and parent_id_str != "":
        try:
            new_parent_id = int(parent_id_str)
            
            # Vérifier que le parent existe
            parent_user = User.query.get(new_parent_id)
            if parent_user is None:
                flash("Le compte parent sélectionné n'existe pas.")
                return redirect(url_for("admin.manage_users"))
            
            # Vérifier que le parent n'est pas lui-même un sous-compte
            if parent_user.is_sub_account:
                flash("Un sous-compte ne peut pas être rattaché à un autre sous-compte.")
                return redirect(url_for("admin.manage_users"))
            
            # Vérifier qu'on ne crée pas une boucle (rattacher à soi-même)
            if new_parent_id == user.id:
                flash("Un utilisateur ne peut pas être rattaché à lui-même.")
                return redirect(url_for("admin.manage_users"))
                
        except ValueError:
            flash("ID de compte parent invalide.")
            return redirect(url_for("admin.manage_users"))

    # Vérifier si l'utilisateur a des sous-comptes (ne peut pas devenir sous-compte)
    if new_parent_id is not None and user.sub_accounts.count() > 0:
        flash("Cet utilisateur a des sous-comptes et ne peut pas devenir lui-même un sous-compte.")
        return redirect(url_for("admin.manage_users"))

    # Si l'utilisateur devient un sous-compte, retirer les droits admin
    if new_parent_id is not None and user.is_admin:
        remaining_admins = User.query.filter(User.id != user.id, User.is_admin == True).count()  # noqa: E712
        if remaining_admins == 0:
            flash("Impossible de rattacher cet utilisateur : il doit rester au moins un administrateur.")
            return redirect(url_for("admin.manage_users"))
        user.is_admin = False

    user.parent_id = new_parent_id
    db.session.commit()

    if new_parent_id is not None:
        flash(f"L'utilisateur est maintenant rattaché à {parent_user.username}.")
    else:
        flash("L'utilisateur est maintenant un compte indépendant.")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<int:user_id>/impersonate", methods=["POST"])
@login_required
@admin_required
def impersonate(user_id: int):
    """Se connecter temporairement en tant qu'un autre utilisateur."""

    if session.get("impersonator_id"):
        flash("Terminez d'abord l'impersonation en cours.")
        return redirect(url_for("admin.manage_users"))

    target = User.query.get_or_404(user_id)

    if target.id == current_user.id:
        flash("Vous êtes déjà connecté en tant que cet utilisateur.")
        return redirect(url_for("admin.manage_users"))

    session["impersonator_id"] = current_user.id
    login_user(target, remember=False)
    flash(f"Vous êtes maintenant connecté en tant que {target.username}.")
    return redirect(url_for("main.index"))


@admin_bp.route("/impersonation/stop", methods=["POST"])
@login_required
def stop_impersonation():
    """Revenir à l'utilisateur administrateur initial après une impersonation."""

    impersonator_id = session.pop("impersonator_id", None)
    if not impersonator_id:
        flash("Aucune session d'impersonation en cours.")
        return redirect(url_for("main.index"))

    admin_user = User.query.get(impersonator_id)
    if not admin_user:
        flash("Impossible de restaurer l'administrateur initial.")
        return redirect(url_for("auth.logout"))

    login_user(admin_user, remember=False)
    flash("Vous êtes revenu à votre compte administrateur.")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id: int):
    """Supprimer un utilisateur et toutes ses données associées."""

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte depuis cette page.")
        return redirect(url_for("admin.manage_users"))

    if user.is_admin:
        remaining_admins = (
            User.query.filter(User.id != user.id, User.is_admin == True).count()  # noqa: E712
        )
        if remaining_admins == 0:
            flash(
                "Impossible de supprimer cet utilisateur : il doit rester au moins un administrateur."
            )
            return redirect(url_for("admin.manage_users"))

    db.session.delete(user)
    db.session.commit()
    flash("L'utilisateur et ses données ont été supprimés.")
    return redirect(url_for("admin.manage_users"))


# ============================================================================
# Logs d'activité
# ============================================================================


@admin_bp.route("/activity-logs")
@login_required
@admin_required
def activity_logs():
    """Afficher les logs d'activité de tous les utilisateurs."""
    
    # Filtres
    user_id = request.args.get("user_id", type=int)
    action = request.args.get("action", "").strip()
    entity_type = request.args.get("entity_type", "").strip()
    days = request.args.get("days", 7, type=int)
    page = request.args.get("page", 1, type=int)
    per_page = 50
    
    # Construire la requête
    query = ActivityLog.query
    
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    
    if action:
        query = query.filter(ActivityLog.action == action)
    
    if entity_type:
        query = query.filter(ActivityLog.entity_type == entity_type)
    
    if days > 0:
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(ActivityLog.created_at >= since)
    
    # Pagination
    logs = query.order_by(ActivityLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Récupérer les utilisateurs pour le filtre
    users = User.query.order_by(User.username.asc()).all()
    
    # Récupérer les actions distinctes
    actions = db.session.query(ActivityLog.action).distinct().all()
    actions = [a[0] for a in actions if a[0]]
    
    # Récupérer les types d'entités distincts
    entity_types = db.session.query(ActivityLog.entity_type).distinct().all()
    entity_types = [e[0] for e in entity_types if e[0]]
    
    return render_template(
        "admin/activity_logs.html",
        logs=logs,
        users=users,
        actions=actions,
        entity_types=entity_types,
        current_user_id=user_id,
        current_action=action,
        current_entity_type=entity_type,
        current_days=days,
    )


@admin_bp.route("/activity-logs/user/<int:user_id>")
@login_required
@admin_required
def user_activity_logs(user_id: int):
    """Afficher les logs d'activité d'un utilisateur spécifique."""
    
    user = User.query.get_or_404(user_id)
    page = request.args.get("page", 1, type=int)
    per_page = 50
    
    logs = ActivityLog.query.filter_by(user_id=user_id).order_by(
        ActivityLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template(
        "admin/user_activity_logs.html",
        user=user,
        logs=logs,
    )


# ============================================================================
# Gestion des quotas
# ============================================================================


@admin_bp.route("/users/<int:user_id>/quota", methods=["GET", "POST"])
@login_required
@admin_required
def manage_user_quota(user_id: int):
    """Gérer le quota de bouteilles d'un utilisateur."""
    
    user = User.query.get_or_404(user_id)
    
    # Récupérer ou créer les paramètres utilisateur
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    
    if request.method == "POST":
        max_bottles_str = request.form.get("max_bottles", "").strip()
        
        if max_bottles_str == "" or max_bottles_str == "0":
            settings.max_bottles = None
            flash(f"Quota illimité pour {user.username}.")
        else:
            try:
                max_bottles = int(max_bottles_str)
                if max_bottles < 0:
                    flash("Le quota doit être positif.")
                    return redirect(url_for("admin.manage_user_quota", user_id=user_id))
                settings.max_bottles = max_bottles
                flash(f"Quota de {max_bottles} bouteilles défini pour {user.username}.")
            except ValueError:
                flash("Valeur de quota invalide.")
                return redirect(url_for("admin.manage_user_quota", user_id=user_id))
        
        db.session.commit()
        return redirect(url_for("admin.manage_users"))
    
    # Calculer l'utilisation actuelle
    current_bottles = Wine.query.filter_by(user_id=user.owner_id).with_entities(
        func.sum(Wine.quantity)
    ).scalar() or 0
    
    return render_template(
        "admin/user_quota.html",
        user=user,
        settings=settings,
        current_bottles=current_bottles,
    )


@admin_bp.route("/quotas")
@login_required
@admin_required
def quotas_overview():
    """Vue d'ensemble des quotas de tous les utilisateurs."""
    
    # Récupérer tous les utilisateurs principaux (pas les sous-comptes)
    users = User.query.filter_by(parent_id=None).order_by(User.username.asc()).all()
    
    quotas_data = []
    for user in users:
        settings = UserSettings.query.filter_by(user_id=user.id).first()
        max_bottles = settings.max_bottles if settings else None
        
        # Calculer l'utilisation
        current_bottles = Wine.query.filter_by(user_id=user.id).with_entities(
            func.sum(Wine.quantity)
        ).scalar() or 0
        
        usage_percent = None
        if max_bottles and max_bottles > 0:
            usage_percent = min(100, round((current_bottles / max_bottles) * 100, 1))
        
        quotas_data.append({
            "user": user,
            "max_bottles": max_bottles,
            "current_bottles": current_bottles,
            "usage_percent": usage_percent,
        })
    
    return render_template(
        "admin/quotas_overview.html",
        quotas_data=quotas_data,
    )


# ============================================================================
# Statistiques globales admin
# ============================================================================


@admin_bp.route("/statistics")
@login_required
@admin_required
def global_statistics():
    """Statistiques globales de l'application pour les administrateurs."""
    
    # Statistiques générales
    total_users = User.query.count()
    total_main_accounts = User.query.filter_by(parent_id=None).count()
    total_sub_accounts = User.query.filter(User.parent_id.isnot(None)).count()
    
    total_wines = Wine.query.count()
    total_bottles = db.session.query(func.sum(Wine.quantity)).scalar() or 0
    total_cellars = Cellar.query.count()
    total_consumptions = WineConsumption.query.count()
    
    # Activité récente (30 derniers jours)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    recent_wines = Wine.query.filter(Wine.created_at >= thirty_days_ago).count()
    recent_consumptions = WineConsumption.query.filter(
        WineConsumption.consumed_at >= thirty_days_ago
    ).count()
    # Note: created_at peut être NULL pour les utilisateurs créés avant la migration
    recent_users = User.query.filter(
        User.created_at.isnot(None),
        User.created_at >= thirty_days_ago
    ).count()
    
    # Top utilisateurs par nombre de bouteilles
    top_users_bottles = db.session.query(
        User.id,
        User.username,
        func.sum(Wine.quantity).label("total_bottles")
    ).join(Wine, Wine.user_id == User.id).filter(
        User.parent_id.is_(None)
    ).group_by(User.id, User.username).order_by(
        func.sum(Wine.quantity).desc()
    ).limit(10).all()
    
    # Top utilisateurs par consommations
    top_users_consumptions = db.session.query(
        User.id,
        User.username,
        func.count(WineConsumption.id).label("total_consumptions")
    ).join(WineConsumption, WineConsumption.user_id == User.id).filter(
        User.parent_id.is_(None)
    ).group_by(User.id, User.username).order_by(
        func.count(WineConsumption.id).desc()
    ).limit(10).all()
    
    # Évolution mensuelle (12 derniers mois)
    monthly_stats = []
    for i in range(11, -1, -1):
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start = month_start - timedelta(days=i * 30)
        month_end = month_start + timedelta(days=30)
        
        wines_added = Wine.query.filter(
            Wine.created_at >= month_start,
            Wine.created_at < month_end
        ).count()
        
        bottles_consumed = db.session.query(func.sum(WineConsumption.quantity)).filter(
            WineConsumption.consumed_at >= month_start,
            WineConsumption.consumed_at < month_end
        ).scalar() or 0
        
        monthly_stats.append({
            "month": month_start.strftime("%Y-%m"),
            "month_label": month_start.strftime("%b %Y"),
            "wines_added": wines_added,
            "bottles_consumed": bottles_consumed,
        })
    
    # Répartition par catégorie (global)
    from models import AlcoholSubcategory
    category_distribution_rows = db.session.query(
        AlcoholSubcategory.name,
        func.sum(Wine.quantity).label("total")
    ).join(Wine, Wine.subcategory_id == AlcoholSubcategory.id).group_by(
        AlcoholSubcategory.name
    ).order_by(func.sum(Wine.quantity).desc()).limit(10).all()
    
    # Convertir les Row en listes pour la sérialisation JSON
    category_distribution = [(row[0], int(row[1])) for row in category_distribution_rows]
    
    return render_template(
        "admin/global_statistics.html",
        total_users=total_users,
        total_main_accounts=total_main_accounts,
        total_sub_accounts=total_sub_accounts,
        total_wines=total_wines,
        total_bottles=total_bottles,
        total_cellars=total_cellars,
        total_consumptions=total_consumptions,
        recent_wines=recent_wines,
        recent_consumptions=recent_consumptions,
        recent_users=recent_users,
        top_users_bottles=top_users_bottles,
        top_users_consumptions=top_users_consumptions,
        monthly_stats=monthly_stats,
        category_distribution=category_distribution,
    )


@admin_bp.route("/statistics/api")
@login_required
@admin_required
def global_statistics_api():
    """API pour les données de statistiques globales (pour les graphiques)."""
    
    # Évolution mensuelle
    monthly_stats = []
    for i in range(11, -1, -1):
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start = month_start - timedelta(days=i * 30)
        month_end = month_start + timedelta(days=30)
        
        wines_added = Wine.query.filter(
            Wine.created_at >= month_start,
            Wine.created_at < month_end
        ).count()
        
        bottles_consumed = db.session.query(func.sum(WineConsumption.quantity)).filter(
            WineConsumption.consumed_at >= month_start,
            WineConsumption.consumed_at < month_end
        ).scalar() or 0
        
        monthly_stats.append({
            "month": month_start.strftime("%Y-%m"),
            "label": month_start.strftime("%b %Y"),
            "wines_added": wines_added,
            "bottles_consumed": bottles_consumed,
        })
    
    return jsonify({
        "monthly_stats": monthly_stats,
    })
