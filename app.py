from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import selectinload
from sqlalchemy import or_
import logging

from models import (
    db,
    User,
    Wine,
    Cellar,
    CellarFloor,
    CellarCategory,
    WineConsumption,
    AlcoholCategory,
    AlcoholSubcategory,
    WineInsight,
)
from config import Config
import requests
from migrations import run_migrations
from tasks import schedule_wine_enrichment


DEFAULT_BADGE_BG_COLOR = "#6366f1"
DEFAULT_BADGE_TEXT_COLOR = "#ffffff"


def _sanitize_color(value: str, fallback: str) -> str:
    value = (value or "").strip()
    if not value:
        return fallback

    if value.startswith('#') and len(value) in (4, 7):
        hex_part = value[1:]
        if all(c in '0123456789abcdefABCDEF' for c in hex_part):
            return value.lower()

    return fallback


def _resolve_redirect(default_endpoint: str) -> str:
    """Résout une redirection de manière sécurisée en validant l'URL."""
    target = (request.form.get('redirect') or '').strip()
    
    # Validation stricte : uniquement les chemins relatifs sans '..'
    if target and target.startswith('/') and '..' not in target:
        # Vérifier que c'est un chemin valide de l'application
        try:
            # Tenter de construire l'URL pour valider qu'elle existe
            from urllib.parse import urlparse
            parsed = urlparse(target)
            # Rejeter si contient un schéma (http://, etc.) ou un netloc (domaine)
            if parsed.scheme or parsed.netloc:
                return url_for(default_endpoint)
            return target
        except (ValueError, AttributeError):
            pass
    
    return url_for(default_endpoint)

def get_subcategory_badge_style(subcategory):
    """Retourne un style inline basé sur les couleurs configurées pour la sous-catégorie."""

    if not subcategory:
        return f"background-color: {DEFAULT_BADGE_BG_COLOR}; color: {DEFAULT_BADGE_TEXT_COLOR};"

    background = _sanitize_color(subcategory.badge_bg_color, DEFAULT_BADGE_BG_COLOR)
    text_color = _sanitize_color(subcategory.badge_text_color, DEFAULT_BADGE_TEXT_COLOR)

    return f"background-color: {background}; color: {text_color};"

def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)
    
    # Initialiser la protection CSRF
    CSRFProtect(flask_app)
    
    db.init_app(flask_app)
    
    # Enregistrer le filtre Jinja2 pour les couleurs de badges
    flask_app.jinja_env.filters['subcategory_badge_style'] = get_subcategory_badge_style
    
    # Configuration du logging pour afficher les logs INFO et DEBUG
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    flask_app.logger.setLevel(logging.INFO)

    login_manager = LoginManager(flask_app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @flask_app.before_request
    def check_temporary_password():
        # Vérifier si l'utilisateur connecté a un mot de passe temporaire
        if (current_user.is_authenticated and
            current_user.has_temporary_password and
            request.endpoint not in ['change_password', 'logout', 'static']):
            return redirect(url_for('change_password'))

    @flask_app.before_request
    def ensure_db():
        # Create DB tables lazily (first request), and seed default admin if needed
        # Using before_request for Flask>=3 compatibility (before_first_request removed)
        if not hasattr(flask_app, "_db_initialized"):
            with flask_app.app_context():
                db.create_all()
                run_migrations(flask_app)
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
                        flask_app.logger.warning("Compte admin créé avec mot de passe temporaire : %s", admin_password)
                    else:
                        print("\n🔐 Compte admin créé avec le mot de passe défini dans DEFAULT_ADMIN_PASSWORD\n")
                        flask_app.logger.info("Compte admin créé avec mot de passe depuis variable d'environnement")
            flask_app._db_initialized = True

    @flask_app.route('/login', methods=['GET', 'POST'])
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

    @flask_app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @flask_app.route('/change_password', methods=['GET', 'POST'])
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

    @flask_app.route('/')
    @login_required
    def index():
        wines = (
            Wine.query.options(
                selectinload(Wine.cellar),
                selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
                selectinload(Wine.insights),
            )
            .filter(Wine.quantity > 0)
            .order_by(Wine.cellar_id.asc(), Wine.subcategory_id.asc(), Wine.name.asc())
            .all()
        )
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()
        
        # Organiser les vins par cave
        wines_by_cellar = {}
        for wine in wines:
            cellar_name = wine.cellar.name if wine.cellar else "Sans cave"
            if cellar_name not in wines_by_cellar:
                wines_by_cellar[cellar_name] = {}
            
            # Organiser par type (sous-catégorie)
            subcategory_name = wine.subcategory.name if wine.subcategory else "Non catégorisé"
            if subcategory_name not in wines_by_cellar[cellar_name]:
                wines_by_cellar[cellar_name][subcategory_name] = []
            
            wines_by_cellar[cellar_name][subcategory_name].append(wine)
        
        return render_template('index.html', wines_by_cellar=wines_by_cellar, cellars=cellars)

    @flask_app.route('/cellars', methods=['GET'])
    @login_required
    def list_cellars():
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()
        return render_template('cellars.html', cellars=cellars)

    @flask_app.route('/cellars/add', methods=['GET', 'POST'])
    @login_required
    def add_cellar():
        categories = CellarCategory.query.order_by(CellarCategory.display_order, CellarCategory.name).all()
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            category_id = request.form.get('category_id', type=int)
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
                'category_id': category_id,
                'floor_capacities': raw_floor_capacities,
                'categories': categories,
            }

            if not name:
                flash("Le nom de la cave est obligatoire.")
                return render_template('add_cellar.html', **context)

            if not category_id:
                flash("Veuillez sélectionner une catégorie de cave.")
                return render_template('add_cellar.html', **context)

            if not floor_capacities or invalid_capacity:
                flash("Veuillez indiquer un nombre de bouteilles positif pour chaque étage.")
                return render_template('add_cellar.html', **context)

            cellar = Cellar(name=name,
                            category_id=category_id,
                            floor_count=len(floor_capacities),
                            bottles_per_floor=max(floor_capacities))
            for index, capacity in enumerate(floor_capacities, start=1):
                cellar.levels.append(CellarFloor(level=index, capacity=capacity))
            db.session.add(cellar)
            db.session.commit()
            flash('Cave créée avec succès.')
            return redirect(url_for('list_cellars'))

        return render_template('add_cellar.html', floor_capacities=[''], categories=categories)
    @flask_app.route('/cellars/<int:cellar_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_cellar(cellar_id):
        """Modifier une cave existante."""
        cellar = Cellar.query.get_or_404(cellar_id)
        categories = CellarCategory.query.order_by(CellarCategory.display_order, CellarCategory.name).all()
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            category_id = request.form.get('category_id', type=int)
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
            
            if not name:
                flash("Le nom de la cave est obligatoire.")
                return render_template('edit_cellar.html', cellar=cellar, categories=categories)
            
            if not category_id:
                flash("Veuillez sélectionner une catégorie de cave.")
                return render_template('edit_cellar.html', cellar=cellar, categories=categories)
            
            if not floor_capacities or invalid_capacity:
                flash("Veuillez indiquer un nombre de bouteilles positif pour chaque étage.")
                return render_template('edit_cellar.html', cellar=cellar, categories=categories)
            
            # Mettre à jour les informations de base
            cellar.name = name
            cellar.category_id = category_id
            cellar.floor_count = len(floor_capacities)
            cellar.bottles_per_floor = max(floor_capacities)
            
            # Supprimer les anciens niveaux et créer les nouveaux
            # Utiliser list() pour éviter les problèmes de modification pendant l'itération
            for level in list(cellar.levels):
                db.session.delete(level)
            
            # Flush pour s'assurer que les suppressions sont effectuées avant les insertions
            db.session.flush()
            
            for index, capacity in enumerate(floor_capacities, start=1):
                cellar.levels.append(CellarFloor(level=index, capacity=capacity))
            
            db.session.commit()
            flash('Cave modifiée avec succès.')
            return redirect(url_for('list_cellars'))
        
        return render_template('edit_cellar.html', cellar=cellar, categories=categories)


    @flask_app.route('/add', methods=['GET', 'POST'])
    @login_required
    def add_wine():
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()
        categories = AlcoholCategory.query.order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()

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
            quantity = request.form.get('quantity', type=int) or 1
            cellar_id = request.form.get('cellar_id', type=int)
            subcategory_id = request.form.get('subcategory_id', type=int) or None

            if not cellar_id:
                flash("Veuillez sélectionner une cave pour y ajouter le vin.")
                return render_template('add_wine.html', cellars=cellars, categories=categories, selected_cellar_id=cellar_id)

            cellar = Cellar.query.get(cellar_id)
            if not cellar:
                flash("La cave sélectionnée est introuvable.")
                return render_template('add_wine.html', cellars=cellars, categories=categories, selected_cellar_id=cellar_id)

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
                        quantity=quantity, cellar=cellar, subcategory_id=subcategory_id)
            db.session.add(wine)
            db.session.commit()
            schedule_wine_enrichment(wine.id)
            flash('Vin ajouté avec succès.')
            return redirect(url_for('index'))
        selected_cellar_id = cellars[0].id if len(cellars) == 1 else None
        return render_template('add_wine.html', cellars=cellars, categories=categories, selected_cellar_id=selected_cellar_id)

    @flask_app.route('/wines/<int:wine_id>', methods=['GET'])
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

    @flask_app.route('/wines/<int:wine_id>/refresh', methods=['POST'])
    @login_required
    def refresh_wine(wine_id):
        wine = Wine.query.get_or_404(wine_id)
        schedule_wine_enrichment(wine.id)
        flash("La récupération des informations a été relancée.")
        return redirect(_resolve_redirect('index'))

    @flask_app.route('/wines/<int:wine_id>/consume', methods=['POST'])
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

    @flask_app.route('/wines/<int:wine_id>/delete', methods=['POST'])
    @login_required
    def delete_wine(wine_id):
        wine = Wine.query.get_or_404(wine_id)
        db.session.delete(wine)
        db.session.commit()
        flash("Le vin a été supprimé de votre cave.")
        return redirect(_resolve_redirect('index'))

    @flask_app.route('/consommations', methods=['GET'])
    @login_required
    def consumption_history():
        consumptions = (
            WineConsumption.query.options(selectinload(WineConsumption.wine))
            .order_by(WineConsumption.consumed_at.desc())
            .all()
        )
        return render_template('consumption_history.html', consumptions=consumptions)

    @flask_app.route('/categories', methods=['GET'])
    @login_required
    def list_categories():
        """Liste toutes les catégories et sous-catégories d'alcool."""
        categories = AlcoholCategory.query.order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()
        return render_template('categories.html', categories=categories)

    @flask_app.route('/categories/add', methods=['GET', 'POST'])
    @login_required
    def add_category():
        """Ajouter une nouvelle catégorie."""
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            display_order = request.form.get('display_order', type=int) or 0
            
            if not name:
                flash("Le nom de la catégorie est obligatoire.")
                return render_template('add_category.html', name=name, description=description, display_order=display_order)
            
            # Vérifier si la catégorie existe déjà
            existing = AlcoholCategory.query.filter_by(name=name).first()
            if existing:
                flash("Une catégorie avec ce nom existe déjà.")
                return render_template('add_category.html', name=name, description=description, display_order=display_order)
            
            category = AlcoholCategory(name=name, description=description, display_order=display_order)
            db.session.add(category)
            db.session.commit()
            flash('Catégorie créée avec succès.')
            return redirect(url_for('list_categories'))
        
        return render_template('add_category.html')

    @flask_app.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_category(category_id):
        """Modifier une catégorie existante."""
        category = AlcoholCategory.query.get_or_404(category_id)
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            display_order = request.form.get('display_order', type=int) or 0
            
            if not name:
                flash("Le nom de la catégorie est obligatoire.")
                return render_template('edit_category.html', category=category)
            
            # Vérifier si le nom existe déjà (sauf pour cette catégorie)
            existing = AlcoholCategory.query.filter(
                AlcoholCategory.name == name,
                AlcoholCategory.id != category_id
            ).first()
            if existing:
                flash("Une autre catégorie avec ce nom existe déjà.")
                return render_template('edit_category.html', category=category)
            
            category.name = name
            category.description = description
            category.display_order = display_order
            db.session.commit()
            flash('Catégorie modifiée avec succès.')
            return redirect(url_for('list_categories'))
        
        return render_template('edit_category.html', category=category)

    @flask_app.route('/categories/<int:category_id>/delete', methods=['POST'])
    @login_required
    def delete_category(category_id):
        """Supprimer une catégorie."""
        category = AlcoholCategory.query.get_or_404(category_id)
        
        # Vérifier si des vins utilisent des sous-catégories de cette catégorie
        wines_count = db.session.query(Wine).join(AlcoholSubcategory).filter(
            AlcoholSubcategory.category_id == category_id
        ).count()
        
        if wines_count > 0:
            flash(f"Impossible de supprimer cette catégorie : {wines_count} bouteille(s) l'utilisent.")
            return redirect(url_for('list_categories'))
        
        db.session.delete(category)
        db.session.commit()
        flash('Catégorie supprimée avec succès.')
        return redirect(url_for('list_categories'))

    @flask_app.route('/categories/<int:category_id>/subcategories/add', methods=['GET', 'POST'])
    @login_required
    def add_subcategory(category_id):
        """Ajouter une sous-catégorie à une catégorie."""
        category = AlcoholCategory.query.get_or_404(category_id)
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            display_order = request.form.get('display_order', type=int) or 0
            badge_bg_color = _sanitize_color(request.form.get('badge_bg_color'), DEFAULT_BADGE_BG_COLOR)
            badge_text_color = _sanitize_color(request.form.get('badge_text_color'), DEFAULT_BADGE_TEXT_COLOR)

            if not name:
                flash("Le nom de la sous-catégorie est obligatoire.")
                return render_template(
                    'add_subcategory.html',
                    category=category,
                    name=name,
                    description=description,
                    display_order=display_order,
                    badge_bg_color=badge_bg_color,
                    badge_text_color=badge_text_color,
                )

            # Vérifier si la sous-catégorie existe déjà dans cette catégorie
            existing = AlcoholSubcategory.query.filter_by(category_id=category_id, name=name).first()
            if existing:
                flash("Une sous-catégorie avec ce nom existe déjà dans cette catégorie.")
                return render_template(
                    'add_subcategory.html',
                    category=category,
                    name=name,
                    description=description,
                    display_order=display_order,
                    badge_bg_color=badge_bg_color,
                    badge_text_color=badge_text_color,
                )

            subcategory = AlcoholSubcategory(
                name=name,
                category_id=category_id,
                description=description,
                display_order=display_order,
                badge_bg_color=badge_bg_color,
                badge_text_color=badge_text_color,
            )
            db.session.add(subcategory)
            db.session.commit()
            flash('Sous-catégorie créée avec succès.')
            return redirect(url_for('list_categories'))
        
        return render_template('add_subcategory.html', category=category)

    @flask_app.route('/subcategories/<int:subcategory_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_subcategory(subcategory_id):
        """Modifier une sous-catégorie existante."""
        subcategory = AlcoholSubcategory.query.get_or_404(subcategory_id)
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            display_order = request.form.get('display_order', type=int) or 0
            badge_bg_color = _sanitize_color(request.form.get('badge_bg_color'), DEFAULT_BADGE_BG_COLOR)
            badge_text_color = _sanitize_color(request.form.get('badge_text_color'), DEFAULT_BADGE_TEXT_COLOR)

            if not name:
                flash("Le nom de la sous-catégorie est obligatoire.")
                return render_template(
                    'edit_subcategory.html',
                    subcategory=subcategory,
                    badge_bg_color=badge_bg_color,
                    badge_text_color=badge_text_color,
                )

            # Vérifier si le nom existe déjà dans cette catégorie (sauf pour cette sous-catégorie)
            existing = AlcoholSubcategory.query.filter(
                AlcoholSubcategory.category_id == subcategory.category_id,
                AlcoholSubcategory.name == name,
                AlcoholSubcategory.id != subcategory_id
            ).first()
            if existing:
                flash("Une autre sous-catégorie avec ce nom existe déjà dans cette catégorie.")
                return render_template(
                    'edit_subcategory.html',
                    subcategory=subcategory,
                    badge_bg_color=badge_bg_color,
                    badge_text_color=badge_text_color,
                )

            subcategory.name = name
            subcategory.description = description
            subcategory.display_order = display_order
            subcategory.badge_bg_color = badge_bg_color
            subcategory.badge_text_color = badge_text_color
            db.session.commit()
            flash('Sous-catégorie modifiée avec succès.')
            return redirect(url_for('list_categories'))

        return render_template('edit_subcategory.html', subcategory=subcategory)

    @flask_app.route('/subcategories/<int:subcategory_id>/delete', methods=['POST'])
    @login_required
    def delete_subcategory(subcategory_id):
        """Supprimer une sous-catégorie."""
        subcategory = AlcoholSubcategory.query.get_or_404(subcategory_id)
        
        # Vérifier si des vins utilisent cette sous-catégorie
        wines_count = Wine.query.filter_by(subcategory_id=subcategory_id).count()
        
        if wines_count > 0:
            flash(f"Impossible de supprimer cette sous-catégorie : {wines_count} bouteille(s) l'utilisent.")
            return redirect(url_for('list_categories'))
        
        db.session.delete(subcategory)
        db.session.commit()
        flash('Sous-catégorie supprimée avec succès.')
        return redirect(url_for('list_categories'))

    @flask_app.route('/cellar-categories', methods=['GET'])
    @login_required
    def list_cellar_categories():
        """Liste toutes les catégories de cave."""
        categories = CellarCategory.query.order_by(CellarCategory.display_order, CellarCategory.name).all()
        return render_template('cellar_categories.html', categories=categories)

    @flask_app.route('/cellar-categories/add', methods=['GET', 'POST'])
    @login_required
    def add_cellar_category():
        """Ajouter une nouvelle catégorie de cave."""
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            display_order = request.form.get('display_order', type=int) or 0
            
            if not name:
                flash("Le nom de la catégorie est obligatoire.")
                return render_template('add_cellar_category.html', name=name, description=description, display_order=display_order)
            
            # Vérifier si la catégorie existe déjà
            existing = CellarCategory.query.filter_by(name=name).first()
            if existing:
                flash("Une catégorie avec ce nom existe déjà.")
                return render_template('add_cellar_category.html', name=name, description=description, display_order=display_order)
            
            category = CellarCategory(name=name, description=description, display_order=display_order)
            db.session.add(category)
            db.session.commit()
            flash('Catégorie de cave créée avec succès.')
            return redirect(url_for('list_cellar_categories'))
        
        return render_template('add_cellar_category.html')

    @flask_app.route('/cellar-categories/<int:category_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_cellar_category(category_id):
        """Modifier une catégorie de cave existante."""
        category = CellarCategory.query.get_or_404(category_id)
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            display_order = request.form.get('display_order', type=int) or 0
            
            if not name:
                flash("Le nom de la catégorie est obligatoire.")
                return render_template('edit_cellar_category.html', category=category)
            
            # Vérifier si le nom existe déjà (sauf pour cette catégorie)
            existing = CellarCategory.query.filter(
                CellarCategory.name == name,
                CellarCategory.id != category_id
            ).first()
            if existing:
                flash("Une autre catégorie avec ce nom existe déjà.")
                return render_template('edit_cellar_category.html', category=category)
            
            category.name = name
            category.description = description
            category.display_order = display_order
            db.session.commit()
            flash('Catégorie de cave modifiée avec succès.')
            return redirect(url_for('list_cellar_categories'))
        
        return render_template('edit_cellar_category.html', category=category)

    @flask_app.route('/cellar-categories/<int:category_id>/delete', methods=['POST'])
    @login_required
    def delete_cellar_category(category_id):
        """Supprimer une catégorie de cave."""
        category = CellarCategory.query.get_or_404(category_id)
        
        # Vérifier si des caves utilisent cette catégorie
        cellars_count = Cellar.query.filter_by(category_id=category_id).count()
        
        if cellars_count > 0:
            flash(f"Impossible de supprimer cette catégorie : {cellars_count} cave(s) l'utilisent.")
            return redirect(url_for('list_cellar_categories'))
        
        db.session.delete(category)
        db.session.commit()
        flash('Catégorie de cave supprimée avec succès.')
        return redirect(url_for('list_cellar_categories'))

    @flask_app.route('/wines/<int:wine_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_wine(wine_id):
        """Modifier un vin existant."""
        wine = Wine.query.get_or_404(wine_id)
        cellars = Cellar.query.order_by(Cellar.name.asc()).all()
        categories = AlcoholCategory.query.order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()
        
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            region = (request.form.get('region') or '').strip()
            grape = (request.form.get('grape') or '').strip()
            year = request.form.get('year') or None
            description = (request.form.get('description') or '').strip()
            quantity = request.form.get('quantity', type=int) or 1
            cellar_id = request.form.get('cellar_id', type=int)
            subcategory_id = request.form.get('subcategory_id', type=int) or None
            
            if not name:
                flash("Le nom du vin est obligatoire.")
                return render_template('edit_wine.html', wine=wine, cellars=cellars, categories=categories)
            
            if not cellar_id:
                flash("Veuillez sélectionner une cave.")
                return render_template('edit_wine.html', wine=wine, cellars=cellars, categories=categories)
            
            cellar = Cellar.query.get(cellar_id)
            if not cellar:
                flash("La cave sélectionnée est introuvable.")
                return render_template('edit_wine.html', wine=wine, cellars=cellars, categories=categories)
            
            wine.name = name
            wine.region = region
            wine.grape = grape
            wine.year = year
            wine.description = description
            wine.quantity = quantity
            wine.cellar_id = cellar_id
            wine.subcategory_id = subcategory_id
            
            db.session.commit()
            flash('Vin modifié avec succès.')
            return redirect(url_for('wine_detail', wine_id=wine.id))
        
        return render_template('edit_wine.html', wine=wine, cellars=cellars, categories=categories)

    @flask_app.route('/search', methods=['GET'])
    @login_required
    def search_wines():
        """Recherche multi-critères dans les vins et leurs insights."""
        # Récupérer les paramètres de recherche
        subcategory_id = request.args.get('subcategory_id', type=int)
        food_pairing = request.args.get('food_pairing', '').strip()
        
        # Récupérer toutes les catégories pour le formulaire
        categories = AlcoholCategory.query.order_by(
            AlcoholCategory.display_order,
            AlcoholCategory.name
        ).all()
        
        # Si aucun critère n'est fourni, afficher juste le formulaire
        if not subcategory_id and not food_pairing:
            return render_template(
                'search.html',
                categories=categories,
                wines=[],
                subcategory_id=None,
                food_pairing=''
            )
        
        # Construire la requête de base
        query = Wine.query.options(
            selectinload(Wine.cellar),
            selectinload(Wine.subcategory),
            selectinload(Wine.insights)
        ).filter(Wine.quantity > 0)
        
        # Filtrer par sous-catégorie si spécifié
        if subcategory_id:
            query = query.filter(Wine.subcategory_id == subcategory_id)
        
        # Filtrer par accord mets-vins si spécifié
        if food_pairing:
            # Échapper les caractères spéciaux SQL LIKE pour éviter l'injection
            # Remplacer % et _ par leur version échappée
            escaped_food_pairing = food_pairing.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            search_pattern = f"%{escaped_food_pairing}%"
            wine_ids_with_matching_insights = db.session.query(WineInsight.wine_id).filter(
                or_(
                    WineInsight.content.ilike(search_pattern, escape='\\'),
                    WineInsight.title.ilike(search_pattern, escape='\\'),
                    WineInsight.category.ilike(search_pattern, escape='\\')
                )
            ).distinct().subquery()
            
            query = query.filter(Wine.id.in_(wine_ids_with_matching_insights))
        
        # Exécuter la requête
        wines = query.order_by(Wine.name.asc()).all()
        
        return render_template(
            'search.html',
            categories=categories,
            wines=wines,
            subcategory_id=subcategory_id,
            food_pairing=food_pairing
        )

    @flask_app.route('/a-consommer', methods=['GET'])
    @login_required
    def wines_to_consume():
        """Affiche les vins à consommer prochainement selon leur potentiel de garde."""
        from datetime import datetime
        
        # Récupérer tous les vins avec leurs insights
        wines = (
            Wine.query.options(
                selectinload(Wine.cellar),
                selectinload(Wine.subcategory),
                selectinload(Wine.insights)
            )
            .filter(Wine.quantity > 0)
            .all()
        )
        
        # Analyser chaque vin pour déterminer son urgence de consommation
        wines_with_urgency = []
        current_year = datetime.now().year
        
        for wine in wines:
            if not wine.year:
                continue
                
            wine_age = current_year - wine.year
            urgency_score = 0
            garde_info = None
            recommended_years = None
            
            # Analyser les insights pour trouver des informations sur le potentiel de garde
            for insight in wine.insights:
                content_lower = insight.content.lower()
                
                # Rechercher des mentions de potentiel de garde
                if any(keyword in content_lower for keyword in ['garde', 'garder', 'conserver', 'vieillissement', 'apogée', 'boire']):
                    garde_info = insight.content
                    
                    # Extraire des années si mentionnées (ex: "5 à 10 ans", "10-15 ans")
                    import re
                    years_match = re.search(r'(\d+)\s*(?:à|-)\s*(\d+)\s*ans?', content_lower)
                    if years_match:
                        min_years = int(years_match.group(1))
                        max_years = int(years_match.group(2))
                        recommended_years = (min_years, max_years)
                        
                        # Calculer l'urgence
                        if wine_age >= max_years:
                            urgency_score = 100  # À boire immédiatement
                        elif wine_age >= min_years:
                            # Dans la fenêtre optimale
                            progress = (wine_age - min_years) / (max_years - min_years)
                            urgency_score = 50 + (progress * 50)
                        else:
                            # Pas encore prêt
                            urgency_score = (wine_age / min_years) * 30
                    
                    # Rechercher des mentions d'urgence
                    if any(keyword in content_lower for keyword in ['maintenant', 'immédiatement', 'rapidement', 'bientôt']):
                        urgency_score = max(urgency_score, 80)
                    
                    if any(keyword in content_lower for keyword in ['apogée', 'optimal', 'parfait']):
                        urgency_score = max(urgency_score, 60)
            
            # Si pas d'info spécifique, utiliser l'âge comme indicateur
            if urgency_score == 0 and wine_age > 0:
                # Heuristique simple basée sur l'âge
                if wine_age >= 15:
                    urgency_score = 70
                elif wine_age >= 10:
                    urgency_score = 50
                elif wine_age >= 5:
                    urgency_score = 30
                else:
                    urgency_score = 10
            
            if urgency_score > 0:
                wines_with_urgency.append({
                    'wine': wine,
                    'urgency_score': urgency_score,
                    'wine_age': wine_age,
                    'garde_info': garde_info,
                    'recommended_years': recommended_years
                })
        
        # Trier par score d'urgence décroissant
        wines_with_urgency.sort(key=lambda x: x['urgency_score'], reverse=True)
        
        return render_template(
            'wines_to_consume.html',
            wines_data=wines_with_urgency,
            current_year=current_year
        )

    return flask_app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
