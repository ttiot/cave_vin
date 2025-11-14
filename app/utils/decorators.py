"""Décorateurs et hooks pour l'application."""

from functools import wraps

from flask import request, redirect, url_for, current_app, abort
from flask_login import current_user
from werkzeug.security import generate_password_hash

from models import db, User
from config import Config
from app.database_init import initialize_database, apply_schema_updates


def check_temporary_password():
    """Vérifie si l'utilisateur connecté a un mot de passe temporaire.

    Redirige vers la page de changement de mot de passe si nécessaire.
    """
    if (
        current_user.is_authenticated
        and current_user.has_temporary_password
        and request.endpoint not in ["auth.change_password", "auth.logout", "static"]
    ):
        return redirect(url_for("auth.change_password"))


def ensure_db():
    """Crée les tables de la base de données et initialise l'admin au premier démarrage.

    Utilise before_request pour la compatibilité Flask>=3 (before_first_request supprimé).
    """
    if not hasattr(current_app, "_db_initialized"):
        with current_app.app_context():
            db.create_all()

            apply_schema_updates()

            initialize_database()

            # Créer l'utilisateur admin par défaut si nécessaire
            admin = User.query.filter_by(username="admin").first()
            if not admin:
                try:
                    admin_password, is_temporary = Config.get_default_admin_password()
                except RuntimeError as exc:
                    current_app.logger.error(str(exc))
                    raise

                admin = User(
                    username="admin",
                    password=generate_password_hash(admin_password),
                    has_temporary_password=is_temporary,
                    is_admin=True,
                )
                db.session.add(admin)
                db.session.commit()

                current_app.logger.info(
                    "Compte admin créé. Veuillez modifier le mot de passe via l'interface ou la commande d'administration."
                )
            elif not admin.is_admin:
                admin.is_admin = True
                db.session.commit()

        current_app._db_initialized = True


def admin_required(func):
    """Restreint l'accès aux utilisateurs administrateurs."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            login_manager = current_app.login_manager
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return func(*args, **kwargs)

    return wrapper
