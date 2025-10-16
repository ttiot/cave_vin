"""Blueprint pour la gestion des catégories d'alcool."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from models import AlcoholCategory, AlcoholSubcategory, Wine, db
from app.utils.formatters import sanitize_color, DEFAULT_BADGE_BG_COLOR, DEFAULT_BADGE_TEXT_COLOR


categories_bp = Blueprint('categories', __name__, url_prefix='/categories')


@categories_bp.route('/', methods=['GET'])
@login_required
def list_categories():
    """Liste toutes les catégories et sous-catégories d'alcool."""
    categories = AlcoholCategory.query.order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()
    return render_template('categories.html', categories=categories)


@categories_bp.route('/add', methods=['GET', 'POST'])
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
        return redirect(url_for('categories.list_categories'))
    
    return render_template('add_category.html')


@categories_bp.route('/<int:category_id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('categories.list_categories'))
    
    return render_template('edit_category.html', category=category)


@categories_bp.route('/<int:category_id>/delete', methods=['POST'])
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
        return redirect(url_for('categories.list_categories'))
    
    db.session.delete(category)
    db.session.commit()
    flash('Catégorie supprimée avec succès.')
    return redirect(url_for('categories.list_categories'))


@categories_bp.route('/<int:category_id>/subcategories/add', methods=['GET', 'POST'])
@login_required
def add_subcategory(category_id):
    """Ajouter une sous-catégorie à une catégorie."""
    category = AlcoholCategory.query.get_or_404(category_id)
    
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        display_order = request.form.get('display_order', type=int) or 0
        badge_bg_color = sanitize_color(request.form.get('badge_bg_color'), DEFAULT_BADGE_BG_COLOR)
        badge_text_color = sanitize_color(request.form.get('badge_text_color'), DEFAULT_BADGE_TEXT_COLOR)

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
        return redirect(url_for('categories.list_categories'))
    
    return render_template('add_subcategory.html', category=category)


@categories_bp.route('/subcategories/<int:subcategory_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_subcategory(subcategory_id):
    """Modifier une sous-catégorie existante."""
    subcategory = AlcoholSubcategory.query.get_or_404(subcategory_id)
    
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        display_order = request.form.get('display_order', type=int) or 0
        badge_bg_color = sanitize_color(request.form.get('badge_bg_color'), DEFAULT_BADGE_BG_COLOR)
        badge_text_color = sanitize_color(request.form.get('badge_text_color'), DEFAULT_BADGE_TEXT_COLOR)

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
        return redirect(url_for('categories.list_categories'))

    return render_template('edit_subcategory.html', subcategory=subcategory)


@categories_bp.route('/subcategories/<int:subcategory_id>/delete', methods=['POST'])
@login_required
def delete_subcategory(subcategory_id):
    """Supprimer une sous-catégorie."""
    subcategory = AlcoholSubcategory.query.get_or_404(subcategory_id)
    
    # Vérifier si des vins utilisent cette sous-catégorie
    wines_count = Wine.query.filter_by(subcategory_id=subcategory_id).count()
    
    if wines_count > 0:
        flash(f"Impossible de supprimer cette sous-catégorie : {wines_count} bouteille(s) l'utilisent.")
        return redirect(url_for('categories.list_categories'))
    
    db.session.delete(subcategory)
    db.session.commit()
    flash('Sous-catégorie supprimée avec succès.')
    return redirect(url_for('categories.list_categories'))