"""Blueprint pour la gestion des catégories de caves."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from models import CellarCategory, Cellar, db
from app.utils.decorators import admin_required


cellar_categories_bp = Blueprint('cellar_categories', __name__, url_prefix='/cellar-categories')


@cellar_categories_bp.route('/', methods=['GET'])
@admin_required
@login_required
def list_cellar_categories():
    """Liste toutes les catégories de cave."""
    categories = CellarCategory.query.order_by(CellarCategory.display_order, CellarCategory.name).all()
    return render_template('cellar_categories.html', categories=categories)


@cellar_categories_bp.route('/add', methods=['GET', 'POST'])
@admin_required
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
        return redirect(url_for('cellar_categories.list_cellar_categories'))
    
    return render_template('add_cellar_category.html')


@cellar_categories_bp.route('/<int:category_id>/edit', methods=['GET', 'POST'])
@admin_required
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
        return redirect(url_for('cellar_categories.list_cellar_categories'))
    
    return render_template('edit_cellar_category.html', category=category)


@cellar_categories_bp.route('/<int:category_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_cellar_category(category_id):
    """Supprimer une catégorie de cave."""
    category = CellarCategory.query.get_or_404(category_id)
    
    # Vérifier si des caves utilisent cette catégorie
    cellars_count = Cellar.query.filter_by(category_id=category_id).count()
    
    if cellars_count > 0:
        flash(f"Impossible de supprimer cette catégorie : {cellars_count} cave(s) l'utilisent.")
        return redirect(url_for('cellar_categories.list_cellar_categories'))
    
    db.session.delete(category)
    db.session.commit()
    flash('Catégorie de cave supprimée avec succès.')
    return redirect(url_for('cellar_categories.list_cellar_categories'))