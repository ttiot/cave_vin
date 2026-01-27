"""Décorateurs et hooks pour l'application."""

from __future__ import annotations

import hashlib
import time
from functools import wraps
from typing import Callable, TypeVar

from flask import request, redirect, url_for, current_app, abort, jsonify, g
from flask_login import current_user
from werkzeug.security import generate_password_hash

from models import db, User, APIToken, APITokenUsage
from config import Config
from app.database_init import initialize_database, apply_schema_updates

F = TypeVar("F", bound=Callable)


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


def get_token_from_request() -> str | None:
    """Extrait le token API de la requête.
    
    Cherche dans l'en-tête Authorization (Bearer token) ou le paramètre api_key.
    """
    # Vérifier l'en-tête Authorization
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Vérifier le paramètre de requête
    return request.args.get("api_key") or request.form.get("api_key")


def validate_api_token(token_string: str) -> tuple[APIToken | None, str | None]:
    """Valide un token API et retourne le token ou un message d'erreur."""
    if not token_string:
        return None, "Token manquant"
    
    # Hasher le token pour comparaison
    token_hash = hashlib.sha256(token_string.encode()).hexdigest()
    
    # Rechercher le token
    token = APIToken.query.filter_by(token_hash=token_hash).first()
    
    if not token:
        return None, "Token invalide"
    
    if not token.is_active:
        return None, "Token révoqué"
    
    if token.is_expired:
        return None, "Token expiré"
    
    if token.is_rate_limited():
        return None, "Limite de requêtes dépassée"
    
    return token, None


def log_api_usage(token: APIToken, status_code: int, response_time_ms: int | None = None) -> None:
    """Enregistre l'utilisation d'un token API."""
    usage = APITokenUsage(
        token_id=token.id,
        endpoint=request.endpoint or request.path,
        method=request.method,
        status_code=status_code,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:255],
        response_time_ms=response_time_ms,
    )
    db.session.add(usage)
    
    # Mettre à jour last_used_at
    from datetime import datetime
    token.last_used_at = datetime.utcnow()
    
    db.session.commit()


def api_token_required(func: F) -> F:
    """Décorateur pour protéger une route API avec authentification par token.
    
    En cas de succès, le token et l'utilisateur sont disponibles via g.api_token et g.api_user.
    En cas d'échec, retourne une erreur JSON appropriée (401, 403, ou 429).
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        token_string = get_token_from_request()
        token, error = validate_api_token(token_string)
        
        if error:
            status_code = 401
            if error == "Limite de requêtes dépassée":
                status_code = 429
            elif error in ("Token révoqué", "Token expiré"):
                status_code = 403
            
            # Logger l'échec si on a trouvé un token (même invalide)
            if token:
                log_api_usage(token, status_code)
            
            return jsonify({"error": error}), status_code
        
        # Stocker le token et l'utilisateur dans g pour accès dans la vue
        g.api_token = token
        g.api_user = token.owner
        
        # Exécuter la fonction
        try:
            response = func(*args, **kwargs)
            
            # Calculer le temps de réponse
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Déterminer le code de statut
            if isinstance(response, tuple):
                status_code = response[1] if len(response) > 1 else 200
            else:
                status_code = 200
            
            # Logger l'utilisation
            log_api_usage(token, status_code, response_time_ms)
            
            return response
        except Exception as e:
            # Logger l'erreur
            log_api_usage(token, 500)
            raise

    return wrapper


def api_token_optional(func: F) -> F:
    """Décorateur pour une route API qui accepte optionnellement un token.
    
    Si un token est fourni, il est validé et disponible via g.api_token.
    Si aucun token n'est fourni, la requête continue normalement.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        token_string = get_token_from_request()
        
        if token_string:
            token, error = validate_api_token(token_string)
            
            if error:
                status_code = 401
                if error == "Limite de requêtes dépassée":
                    status_code = 429
                elif error in ("Token révoqué", "Token expiré"):
                    status_code = 403
                return jsonify({"error": error}), status_code
            
            g.api_token = token
            g.api_user = token.owner
        else:
            g.api_token = None
            g.api_user = None
        
        return func(*args, **kwargs)

    return wrapper
