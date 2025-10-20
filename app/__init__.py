"""Factory pattern pour l'application Flask Cave à Vin."""

import os
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
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
    
    # Initialiser les extensions
    db.init_app(flask_app)
    CSRFProtect(flask_app)

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
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "connect-src 'self' https://api.openai.com"
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

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(wines_bp)
    flask_app.register_blueprint(cellars_bp)
    flask_app.register_blueprint(categories_bp)
    flask_app.register_blueprint(cellar_categories_bp)
    flask_app.register_blueprint(search_bp)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(admin_bp)

    return flask_app
