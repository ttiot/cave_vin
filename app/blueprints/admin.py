"""Blueprint dédié aux fonctionnalités d'administration."""

from __future__ import annotations

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from flask_login import login_required, current_user, login_user
from werkzeug.security import generate_password_hash

from models import User, db
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

        if not username:
            flash("Le nom d'utilisateur est obligatoire.")
        elif not password:
            flash("Le mot de passe est obligatoire.")
        elif User.query.filter_by(username=username).first():
            flash("Ce nom d'utilisateur est déjà utilisé.")
        else:
            user = User(
                username=username,
                password=generate_password_hash(password),
                has_temporary_password=is_temporary,
                is_admin=is_admin,
            )
            db.session.add(user)
            db.session.commit()
            flash("Utilisateur créé avec succès.")
            return redirect(url_for("admin.manage_users"))

    users = User.query.order_by(User.username.asc()).all()
    return render_template(
        "admin_users.html",
        users=users,
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
