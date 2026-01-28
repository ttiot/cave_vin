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
    SESSION_PROTECTION = os.environ.get('SESSION_PROTECTION', 'strong')
    PREFERRED_URL_SCHEME = 'https'
    OPENAI_LOG_REQUESTS = False
    
    # Configuration SMTP pour l'envoi d'emails
    # Clé de chiffrement pour les mots de passe SMTP (Fernet key)
    # Générer avec: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SMTP_ENCRYPTION_KEY = os.environ.get('SMTP_ENCRYPTION_KEY')
    
    # Configuration du Scheduler (tâches planifiées)
    # Ces variables sont lues par app/scheduler.py
    #
    # SCHEDULER_WEEKLY_REPORT_ENABLED: Active/désactive le rapport hebdomadaire (1/0)
    # SCHEDULER_WEEKLY_REPORT_DAY: Jour d'envoi (mon, tue, wed, thu, fri, sat, sun)
    # SCHEDULER_WEEKLY_REPORT_HOUR: Heure d'envoi (0-23)
    # SCHEDULER_WEEKLY_REPORT_MINUTE: Minute d'envoi (0-59)
    #
    # SCHEDULER_CLEANUP_ENABLED: Active/désactive le nettoyage automatique (1/0)
    # SCHEDULER_CLEANUP_DAY: Jour de nettoyage (mon, tue, wed, thu, fri, sat, sun)
    # SCHEDULER_CLEANUP_HOUR: Heure de nettoyage (0-23)
    # SCHEDULER_CLEANUP_MINUTE: Minute de nettoyage (0-59)
    #
    # Exemple de configuration:
    #   SCHEDULER_WEEKLY_REPORT_ENABLED=1
    #   SCHEDULER_WEEKLY_REPORT_DAY=mon
    #   SCHEDULER_WEEKLY_REPORT_HOUR=8
    #   SCHEDULER_WEEKLY_REPORT_MINUTE=0
    
    @staticmethod
    def get_default_admin_password():
        """Retourne le mot de passe admin par défaut depuis la configuration."""
        env_password = os.environ.get('DEFAULT_ADMIN_PASSWORD')
        if env_password:
            return env_password, False  # False = pas temporaire

        raise RuntimeError(
            "DEFAULT_ADMIN_PASSWORD doit être défini avant le premier démarrage"
        )
