import os
import secrets
from datetime import timedelta

class Config:
    # Génération automatique d'une SECRET_KEY sécurisée si non définie
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///wines.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Protection CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # Limite la durée de vie des tokens CSRF à 1h
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
    OPENAI_FREE_MODEL = os.environ.get('OPENAI_FREE_MODEL', 'gpt-4o-mini')
    OPENAI_SOURCE_NAME = os.environ.get('OPENAI_SOURCE_NAME', 'OpenAI')
    _COOKIE_SECURE_DEFAULT = os.environ.get('COOKIE_SECURE', '1').lower() not in {'0', 'false', 'no', 'off'}
    _COOKIE_SAMESITE_RAW = os.environ.get('COOKIE_SAMESITE', '').strip().lower()
    if _COOKIE_SAMESITE_RAW in {'lax', 'strict', 'none'}:
        _COOKIE_SAMESITE_VALUE = _COOKIE_SAMESITE_RAW.capitalize()
    else:
        _COOKIE_SAMESITE_VALUE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    REMEMBER_COOKIE_SECURE = _COOKIE_SECURE_DEFAULT
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = _COOKIE_SAMESITE_VALUE
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST = False
    SESSION_COOKIE_SECURE = _COOKIE_SECURE_DEFAULT
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = _COOKIE_SAMESITE_VALUE
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_PROTECTION = 'strong'
    PREFERRED_URL_SCHEME = 'https'
    OPENAI_LOG_REQUESTS = False
    
    @staticmethod
    def get_default_admin_password():
        """Retourne le mot de passe admin par défaut depuis la configuration."""
        env_password = os.environ.get('DEFAULT_ADMIN_PASSWORD')
        if env_password:
            return env_password, False  # False = pas temporaire

        raise RuntimeError(
            "DEFAULT_ADMIN_PASSWORD doit être défini avant le premier démarrage"
        )
