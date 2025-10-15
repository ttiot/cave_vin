import os
import secrets
import string

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_secret_key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///wines.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
    OPENAI_FREE_MODEL = os.environ.get('OPENAI_FREE_MODEL', 'gpt-4o-mini')
    OPENAI_SOURCE_NAME = os.environ.get('OPENAI_SOURCE_NAME', 'OpenAI')
    
    @staticmethod
    def get_default_admin_password():
        """
        Retourne le mot de passe admin par défaut :
        - Variable d'environnement DEFAULT_ADMIN_PASSWORD si elle existe
        - Sinon génère un mot de passe temporaire aléatoire
        """
        env_password = os.environ.get('DEFAULT_ADMIN_PASSWORD')
        if env_password:
            return env_password, False  # False = pas temporaire
        
        # Génération d'un mot de passe temporaire aléatoire
        alphabet = string.ascii_letters + string.digits
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
        return temp_password, True  # True = temporaire
