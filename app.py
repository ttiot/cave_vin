from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import selectinload
import logging

from models import db, User, Wine, Cellar, CellarFloor, WineConsumption
from config import Config
import requests
from migrations import run_migrations
from tasks import schedule_wine_enrichment


def _resolve_redirect(default_endpoint: str) -> str:
    target = (request.form.get('redirect') or '').strip()
    if target.startswith('/'):
        return target
    return url_for(default_endpoint)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    # Configuration du logging pour afficher les logs INFO et DEBUG
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    app.logger.setLevel(logging.INFO)

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
                run_migrations(app)
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
        wines = (
            Wine.query.options(
                selectinload(Wine.cellar),
                selectinload(Wine.insights),
            )
            .filter(Wine.quantity > 0)
            .order_by(Wine.name.asc())
            .all()
        )
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()
        return render_template('index.html', wines=wines, cellars=cellars)

    @app.route('/cellars', methods=['GET'])
    @login_required
    def list_cellars():
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()
        return render_template('cellars.html', cellars=cellars)

    @app.route('/cellars/add', methods=['GET', 'POST'])
    @login_required
    def add_cellar():
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            cellar_type = request.form.get('cellar_type')
            raw_floor_capacities = [value.strip() for value in request.form.getlist('floor_capacities')]
            floor_capacities = []
            invalid_capacity = False
            for raw_capacity in raw_floor_capacities:
                if not raw_capacity:
                    invalid_capacity = True
                    break
                try:
                    capacity_value = int(raw_capacity)
                except (TypeError, ValueError):
                    invalid_capacity = True
                    break
                if capacity_value <= 0:
                    invalid_capacity = True
                    break
                floor_capacities.append(capacity_value)

            context = {
                'name': name,
                'cellar_type': cellar_type,
                'floor_capacities': raw_floor_capacities,
            }

            if not name:
                flash("Le nom de la cave est obligatoire.")
                return render_template('add_cellar.html', **context)

            if cellar_type not in {'naturelle', 'electrique'}:
                flash("Veuillez sélectionner un type de cave valide.")
                return render_template('add_cellar.html', **context)

            if not floor_capacities or invalid_capacity:
                flash("Veuillez indiquer un nombre de bouteilles positif pour chaque étage.")
                return render_template('add_cellar.html', **context)

            cellar = Cellar(name=name,
                            cellar_type=cellar_type,
                            floor_count=len(floor_capacities),
                            bottles_per_floor=max(floor_capacities))
            for index, capacity in enumerate(floor_capacities, start=1):
                cellar.levels.append(CellarFloor(level=index, capacity=capacity))
            db.session.add(cellar)
            db.session.commit()
            flash('Cave créée avec succès.')
            return redirect(url_for('list_cellars'))

        return render_template('add_cellar.html', floor_capacities=[''])

    @app.route('/add', methods=['GET', 'POST'])
    @login_required
    def add_wine():
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()

        if not cellars:
            flash("Créez d'abord une cave avant d'ajouter des bouteilles.")
            return redirect(url_for('add_cellar'))

        if request.method == 'POST':
            barcode = request.form.get('barcode') or None
            name = (request.form.get('name') or '').strip()
            region = (request.form.get('region') or '').strip()
            grape = (request.form.get('grape') or '').strip()
            year = request.form.get('year') or None
            description = (request.form.get('description') or '').strip()
            cellar_id = request.form.get('cellar_id', type=int)

            if not cellar_id:
                flash("Veuillez sélectionner une cave pour y ajouter le vin.")
                return render_template('add_wine.html', cellars=cellars, selected_cellar_id=cellar_id)

            cellar = Cellar.query.get(cellar_id)
            if not cellar:
                flash("La cave sélectionnée est introuvable.")
                return render_template('add_wine.html', cellars=cellars, selected_cellar_id=cellar_id)

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
                        barcode=barcode, description=description, image_url=image_url,
                        cellar=cellar)
            db.session.add(wine)
            db.session.commit()
            schedule_wine_enrichment(wine.id)
            flash('Vin ajouté avec succès.')
            return redirect(url_for('index'))
        selected_cellar_id = cellars[0].id if len(cellars) == 1 else None
        return render_template('add_wine.html', cellars=cellars, selected_cellar_id=selected_cellar_id)

    @app.route('/wines/<int:wine_id>', methods=['GET'])
    @login_required
    def wine_detail(wine_id):
        wine = (
            Wine.query.options(
                selectinload(Wine.cellar),
                selectinload(Wine.insights),
                selectinload(Wine.consumptions),
            )
            .filter_by(id=wine_id)
            .first_or_404()
        )
        return render_template('wine_detail.html', wine=wine)

    @app.route('/wines/<int:wine_id>/refresh', methods=['POST'])
    @login_required
    def refresh_wine(wine_id):
        wine = Wine.query.get_or_404(wine_id)
        schedule_wine_enrichment(wine.id)
        flash("La récupération des informations a été relancée.")
        return redirect(_resolve_redirect('index'))

    @app.route('/wines/<int:wine_id>/consume', methods=['POST'])
    @login_required
    def consume_wine(wine_id):
        wine = Wine.query.get_or_404(wine_id)
        if wine.quantity <= 0:
            flash("Ce vin n'est plus disponible dans la cave.")
            return redirect(_resolve_redirect('index'))

        wine.quantity -= 1
        consumption = WineConsumption(
            wine=wine,
            quantity=1,
            snapshot_name=wine.name,
            snapshot_year=wine.year,
            snapshot_region=wine.region,
            snapshot_grape=wine.grape,
            snapshot_cellar=wine.cellar.name if wine.cellar else None,
        )
        db.session.add(consumption)
        db.session.commit()

        flash("Une bouteille a été marquée comme consommée.")
        return redirect(_resolve_redirect('index'))

    @app.route('/wines/<int:wine_id>/delete', methods=['POST'])
    @login_required
    def delete_wine(wine_id):
        wine = Wine.query.get_or_404(wine_id)
        db.session.delete(wine)
        db.session.commit()
        flash("Le vin a été supprimé de votre cave.")
        return redirect(_resolve_redirect('index'))

    @app.route('/consommations', methods=['GET'])
    @login_required
    def consumption_history():
        consumptions = (
            WineConsumption.query.options(selectinload(WineConsumption.wine))
            .order_by(WineConsumption.consumed_at.desc())
            .all()
        )
        return render_template('consumption_history.html', consumptions=consumptions)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
