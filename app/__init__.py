"""Factory pattern pour l'application Flask Cave à Vin."""

import os

from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
import logging

from models import db, User
from config import Config


def create_app(config_class=Config):
    """Factory pour créer et configurer l'application Flask."""

    # Déterminer le chemin de base du projet (parent du dossier app)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    flask_app = Flask(__name__,
                     template_folder=template_dir,
                     static_folder=static_dir)
    flask_app.config.from_object(config_class)

    # Support proxy (Traefik, etc.) pour scheme/host corrects
    flask_app.wsgi_app = ProxyFix(
        flask_app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
    )

    # Initialiser les extensions
    db.init_app(flask_app)
    csrf = CSRFProtect(flask_app)
    
    @flask_app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        """Journalise les erreurs CSRF pour faciliter le diagnostic."""
        flask_app.logger.warning(
            "[CSRF] %s path=%s ua=%s referer=%s session_cookie=%s",
            error.description,
            request.path,
            request.headers.get("User-Agent"),
            request.headers.get("Referer"),
            "present" if request.cookies.get("session") else "missing",
        )
        return error.description, 400

    # Exempter les routes API de la protection CSRF (elles utilisent l'auth par token)
    csrf.exempt("api.list_wines")
    csrf.exempt("api.get_wine")
    csrf.exempt("api.create_wine")
    csrf.exempt("api.update_wine")
    csrf.exempt("api.delete_wine")
    csrf.exempt("api.consume_wine")
    csrf.exempt("api.list_cellars")
    csrf.exempt("api.get_cellar")
    csrf.exempt("api.create_cellar")
    csrf.exempt("api.update_cellar")
    csrf.exempt("api.delete_cellar")
    csrf.exempt("api.search_wines")
    csrf.exempt("api.get_statistics")
    csrf.exempt("api.list_categories")
    csrf.exempt("api.list_cellar_categories")
    csrf.exempt("api.list_consumptions")
    csrf.exempt("api.get_collection")
    csrf.exempt("api.list_webhooks")
    csrf.exempt("api.create_webhook")
    csrf.exempt("api.get_webhook")
    csrf.exempt("api.update_webhook")
    csrf.exempt("api.delete_webhook")
    csrf.exempt("api.test_webhook")
    csrf.exempt("api.openapi_spec")
    csrf.exempt("api.swagger_ui")
    # Routes push notifications (appelées via fetch depuis le JS)
    csrf.exempt("api.get_vapid_key")
    csrf.exempt("api.subscribe_push")
    csrf.exempt("api.unsubscribe_push")
    csrf.exempt("api.test_push")

    @flask_app.after_request
    def set_security_headers(response):
        """Ajoute des en-têtes de sécurité de base pour toutes les réponses."""

        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "connect-src 'self' https://api.openai.com",
        )
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    # Configuration du logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    flask_app.logger.setLevel(logging.INFO)

    # Configuration de Flask-Login
    login_manager = LoginManager(flask_app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Enregistrer les filtres Jinja2
    from app.utils.formatters import get_subcategory_badge_style
    flask_app.jinja_env.filters['subcategory_badge_style'] = get_subcategory_badge_style

    # Hooks before_request
    from app.utils.decorators import check_temporary_password, ensure_db
    flask_app.before_request(check_temporary_password)
    flask_app.before_request(ensure_db)

    # Enregistrer les blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.wines import wines_bp
    from app.blueprints.cellars import cellars_bp
    from app.blueprints.categories import categories_bp
    from app.blueprints.cellar_categories import cellar_categories_bp
    from app.blueprints.search import search_bp
    from app.blueprints.main import main_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.api_tokens import api_tokens_bp
    from app.blueprints.api import api_bp
    from app.blueprints.advanced_stats import advanced_stats_bp

    # Exempter tout le blueprint API du CSRF (appelé via fetch/js)
    csrf.exempt(api_bp)

    if flask_app.config.get("WTF_CSRF_EXEMPT_LOGIN"):
        csrf.exempt("auth.login")

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(wines_bp)
    flask_app.register_blueprint(cellars_bp)
    flask_app.register_blueprint(categories_bp)
    flask_app.register_blueprint(cellar_categories_bp)
    flask_app.register_blueprint(search_bp)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(api_tokens_bp)
    flask_app.register_blueprint(api_bp)
    flask_app.register_blueprint(advanced_stats_bp)

    return flask_app
