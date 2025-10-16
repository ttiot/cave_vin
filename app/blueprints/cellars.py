"""Blueprint pour la gestion des caves."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from models import Cellar, CellarCategory, CellarFloor, db


cellars_bp = Blueprint('cellars', __name__, url_prefix='/cellars')


@cellars_bp.route('/', methods=['GET'])
@login_required
def list_cellars():
    """Liste toutes les caves."""
    cellars = Cellar.query.order_by(Cellar.name.asc()).all()
    return render_template('cellars.html', cellars=cellars)


@cellars_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_cellar():
    """Ajouter une nouvelle cave."""
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

        cellar = Cellar(
            name=name,
            category_id=category_id,
            floor_count=len(floor_capacities),
            bottles_per_floor=max(floor_capacities)
        )
        for index, capacity in enumerate(floor_capacities, start=1):
            cellar.levels.append(CellarFloor(level=index, capacity=capacity))
        
        db.session.add(cellar)
        db.session.commit()
        flash('Cave créée avec succès.')
        return redirect(url_for('cellars.list_cellars'))

    return render_template('add_cellar.html', floor_capacities=[''], categories=categories)


@cellars_bp.route('/<int:cellar_id>/edit', methods=['GET', 'POST'])
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