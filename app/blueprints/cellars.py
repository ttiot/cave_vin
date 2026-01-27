"""Blueprint pour la gestion des caves."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from models import Cellar, CellarCategory, CellarFloor, User, db
from services.push_notification_service import notify_cellar_created, notify_cellar_deleted


cellars_bp = Blueprint('cellars', __name__, url_prefix='/cellars')


@cellars_bp.route('/', methods=['GET'])
@login_required
def list_cellars():
    """Liste toutes les caves.
    
    Pour un sous-compte, affiche les caves du compte parent.
    """
    owner_id = current_user.owner_id
    cellars = (
        Cellar.query.filter_by(user_id=owner_id)
        .order_by(Cellar.name.asc())
        .all()
    )
    return render_template('cellars.html', cellars=cellars)


@cellars_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_cellar():
    """Ajouter une nouvelle cave.
    
    La cave est créée pour le compte propriétaire (parent si sous-compte).
    """
    categories = CellarCategory.query.order_by(CellarCategory.display_order, CellarCategory.name).all()
    owner_account = current_user.owner_account
    
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

        cellar = Cellar(
            name=name,
            category_id=category_id,
            floor_count=len(floor_capacities),
            bottles_per_floor=max(floor_capacities),
            owner=owner_account,
        )
        for index, capacity in enumerate(floor_capacities, start=1):
            cellar.levels.append(CellarFloor(level=index, capacity=capacity))
        
        db.session.add(cellar)
        db.session.commit()
        
        # Envoyer une notification push aux autres membres de la famille de comptes
        try:
            notify_cellar_created(cellar, current_user.id)
        except Exception:
            pass  # Ne pas bloquer si la notification échoue
        
        flash('Cave créée avec succès.')
        return redirect(url_for('cellars.list_cellars'))

    return render_template('add_cellar.html', floor_capacities=[''], categories=categories)


@cellars_bp.route('/<int:cellar_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_cellar(cellar_id):
    """Modifier une cave existante.
    
    Pour un sous-compte, permet de modifier les caves du compte parent.
    """
    owner_id = current_user.owner_id
    cellar = Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first_or_404()
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
        for level in list(cellar.levels):
            db.session.delete(level)
        
        # Flush pour s'assurer que les suppressions sont effectuées avant les insertions
        db.session.flush()
        
        for index, capacity in enumerate(floor_capacities, start=1):
            cellar.levels.append(CellarFloor(level=index, capacity=capacity))
        
        db.session.commit()
        flash('Cave modifiée avec succès.')
        return redirect(url_for('cellars.list_cellars'))
    
    return render_template('edit_cellar.html', cellar=cellar, categories=categories)


@cellars_bp.route('/<int:cellar_id>/set-default', methods=['POST'])
@login_required
def set_default_cellar(cellar_id):
    """Définir une cave comme cave par défaut.
    
    Pour un sous-compte, vérifie que la cave appartient au compte parent.
    """
    owner_id = current_user.owner_id
    cellar = Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first_or_404()
    
    current_user.default_cellar_id = cellar.id
    db.session.commit()
    
    flash(f'La cave « {cellar.name} » est maintenant votre cave par défaut.')
    return redirect(url_for('cellars.list_cellars'))


@cellars_bp.route('/clear-default', methods=['POST'])
@login_required
def clear_default_cellar():
    """Supprimer la cave par défaut."""
    current_user.default_cellar_id = None
    db.session.commit()
    
    flash('La cave par défaut a été supprimée.')
    return redirect(url_for('cellars.list_cellars'))
