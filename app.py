from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Wine
from config import Config
import requests

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.before_request
    def check_temporary_password():
        # Vérifier si l'utilisateur connecté a un mot de passe temporaire
        if (current_user.is_authenticated and
            current_user.has_temporary_password and
            request.endpoint not in ['change_password', 'logout', 'static']):
            return redirect(url_for('change_password'))

    @app.before_request
    def ensure_db():
        # Create DB tables lazily (first request), and seed default admin if needed
        # Using before_request for Flask>=3 compatibility (before_first_request removed)
        if not hasattr(app, "_db_initialized"):
            with app.app_context():
                db.create_all()
                if not User.query.filter_by(username="admin").first():
                    # Obtenir le mot de passe admin par défaut
                    admin_password, is_temporary = Config.get_default_admin_password()
                    
                    # Créer le compte admin
                    admin = User(username="admin", password=generate_password_hash(admin_password), has_temporary_password=is_temporary)
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
                        
                        # Log également pour les logs de l'application
                        app.logger.warning("Compte admin créé avec mot de passe temporaire : %s", admin_password)
                    else:
                        print("\n🔐 Compte admin créé avec le mot de passe défini dans DEFAULT_ADMIN_PASSWORD\n")
                        app.logger.info("Compte admin créé avec mot de passe depuis variable d'environnement")
            app._db_initialized = True

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('index'))
            flash("Identifiants incorrects.")
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/change_password', methods=['GET', 'POST'])
    @login_required
    def change_password():
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
            return redirect(url_for('index'))
        
        return render_template('change_password.html')

    @app.route('/')
    @login_required
    def index():
        wines = Wine.query.order_by(Wine.name.asc()).all()
        return render_template('index.html', wines=wines)

    @app.route('/add', methods=['GET', 'POST'])
    @login_required
    def add_wine():
        if request.method == 'POST':
            barcode = request.form.get('barcode') or None
            name = (request.form.get('name') or '').strip()
            region = (request.form.get('region') or '').strip()
            grape = (request.form.get('grape') or '').strip()
            year = request.form.get('year') or None
            description = (request.form.get('description') or '').strip()

            # Recherche auto via OpenFoodFacts si code-barres et pas de nom
            if barcode and not name:
                try:
                    r = requests.get(f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json', timeout=6)
                    if r.status_code == 200:
                        data = r.json().get('product', {}) or {}
                        name = (data.get('product_name') or data.get('brands') or 'Vin inconnu')
                        image_url = data.get('image_url')
                    else:
                        image_url = None
                except Exception:
                    image_url = None
            else:
                image_url = None

            wine = Wine(name=name or 'Vin sans nom', region=region, grape=grape, year=year,
                        barcode=barcode, description=description, image_url=image_url)
            db.session.add(wine)
            db.session.commit()
            flash('Vin ajouté avec succès.')
            return redirect(url_for('index'))
        return render_template('add_wine.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
