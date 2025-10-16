"""Décorateurs et hooks pour l'application."""

from flask import request, redirect, url_for, current_app
from flask_login import current_user
from werkzeug.security import generate_password_hash

from models import db, User
from config import Config


def check_temporary_password():
    """Vérifie si l'utilisateur connecté a un mot de passe temporaire.
    
    Redirige vers la page de changement de mot de passe si nécessaire.
    """
    if (current_user.is_authenticated and
        current_user.has_temporary_password and
        request.endpoint not in ['auth.change_password', 'auth.logout', 'static']):
        return redirect(url_for('auth.change_password'))


def ensure_db():
    """Crée les tables de la base de données et initialise l'admin au premier démarrage.
    
    Utilise before_request pour la compatibilité Flask>=3 (before_first_request supprimé).
    """
    if not hasattr(current_app, "_db_initialized"):
        with current_app.app_context():
            db.create_all()
            
            # Exécuter les migrations
            from migrations import run_migrations
            run_migrations(current_app)
            
            # Créer l'utilisateur admin par défaut si nécessaire
            if not User.query.filter_by(username="admin").first():
                admin_password, is_temporary = Config.get_default_admin_password()
                
                admin = User(
                    username="admin",
                    password=generate_password_hash(admin_password),
                    has_temporary_password=is_temporary
                )
                db.session.add(admin)
                db.session.commit()
                
                # Afficher un message d'information
                if is_temporary:
                    print("\n" + "="*60)
                    print("🔐 COMPTE ADMIN CRÉÉ AVEC MOT DE PASSE TEMPORAIRE")
                    print("="*60)
                    print("Nom d'utilisateur : admin")
                    print(f"Mot de passe temporaire : {admin_password}")
                    print("\n⚠️  IMPORTANT : Ce mot de passe doit être changé dès la première connexion !")
                    print("="*60 + "\n")
                    
                    current_app.logger.warning("Compte admin créé avec mot de passe temporaire : %s", admin_password)
                else:
                    print("\n🔐 Compte admin créé avec le mot de passe défini dans DEFAULT_ADMIN_PASSWORD\n")
                    current_app.logger.info("Compte admin créé avec mot de passe depuis variable d'environnement")
        
        current_app._db_initialized = True