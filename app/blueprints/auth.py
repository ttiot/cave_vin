"""Blueprint pour l'authentification."""

from collections import defaultdict
from time import time

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    session,
)
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse

from werkzeug.security import check_password_hash, generate_password_hash

from models import User, db


auth_bp = Blueprint('auth', __name__)

_login_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion."""
    next_url = request.args.get('next')

    if request.method == 'POST':
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        now = time()
        attempts = _login_attempts[client_ip]
        _login_attempts[client_ip] = [ts for ts in attempts if now - ts < WINDOW_SECONDS]

        if len(_login_attempts[client_ip]) >= MAX_ATTEMPTS:
            current_app.logger.warning("Trop de tentatives de connexion pour %s", client_ip)
            flash("Trop de tentatives. Réessayez dans quelques minutes.")
            return render_template('login.html', next_url=next_url), 429

        username = request.form['username']
        password = request.form['password']
        next_url = request.form.get('next') or next_url
        remember_me = bool(request.form.get('remember_me'))
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=remember_me)
            session.pop('impersonator_id', None)
            _login_attempts.pop(client_ip, None)

            if not next_url or urlparse(next_url).netloc != '':
                next_url = url_for('main.index')

            return redirect(next_url)

        flash("Identifiants incorrects.")
        _login_attempts[client_ip].append(now)

    return render_template('login.html', next_url=next_url)


@auth_bp.route('/logout')
@login_required
def logout():
    """Déconnexion de l'utilisateur."""
    logout_user()
    session.pop('impersonator_id', None)
    return redirect(url_for('auth.login'))


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Page de changement de mot de passe."""
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Vérifier le mot de passe actuel
        if not check_password_hash(current_user.password, current_password):
            flash("Mot de passe actuel incorrect.")
            return render_template('change_password.html')
        
        # Vérifier que les nouveaux mots de passe correspondent
        if new_password != confirm_password:
            flash("Les nouveaux mots de passe ne correspondent pas.")
            return render_template('change_password.html')
        
        # Vérifier la longueur du nouveau mot de passe
        if len(new_password) < 6:
            flash("Le nouveau mot de passe doit contenir au moins 6 caractères.")
            return render_template('change_password.html')
        
        # Mettre à jour le mot de passe
        current_user.password = generate_password_hash(new_password)
        current_user.has_temporary_password = False
        db.session.commit()
        
        flash("Mot de passe changé avec succès.")
        return redirect(url_for('main.index'))
    
    return render_template('change_password.html')
