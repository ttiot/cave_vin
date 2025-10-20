"""Blueprint pour la gestion des catégories d'alcool."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.orm import selectinload

from models import (
    AlcoholCategory,
    AlcoholSubcategory,
    AlcoholFieldRequirement,
    BottleFieldDefinition,
    Wine,
    db,
)
from app.utils.formatters import sanitize_color, DEFAULT_BADGE_BG_COLOR, DEFAULT_BADGE_TEXT_COLOR
from app.field_config import (
    DEFAULT_FIELD_DEFINITIONS,
    get_display_order,
    iter_fields,
    sanitize_field_name,
)
from app.utils.decorators import admin_required


categories_bp = Blueprint('categories', __name__, url_prefix='/categories')


@categories_bp.route('/', methods=['GET'])
@admin_required
@login_required
def list_categories():
    """Liste toutes les catégories et sous-catégories d'alcool."""
    categories = AlcoholCategory.query.order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()
    return render_template('categories.html', categories=categories)


def _blank_field_state() -> dict[str, dict[str, bool]]:
    return {
        field.name: {"enabled": False, "required": False}
        for field in iter_fields()
    }


def _build_settings_snapshot(categories: list[AlcoholCategory]) -> dict[str, dict]:
    """
    Construit un snapshot des paramètres de champs avec héritage appliqué.
    - Les catégories héritent de la config globale
    - Les sous-catégories héritent de leur catégorie (qui hérite de la globale)
    """
    # Charger tous les requirements depuis la base de données
    requirements = AlcoholFieldRequirement.query.all()
    
    # Organiser les requirements par scope
    global_reqs: dict[str, dict] = {}
    category_reqs: dict[int, dict[str, dict]] = {}
    subcategory_reqs: dict[int, dict[str, dict]] = {}
    
    for requirement in requirements:
        rule = {
            "enabled": bool(requirement.is_enabled),
            "required": bool(requirement.is_required),
        }
        
        if requirement.subcategory_id:
            if requirement.subcategory_id not in subcategory_reqs:
                subcategory_reqs[requirement.subcategory_id] = {}
            subcategory_reqs[requirement.subcategory_id][requirement.field_name] = rule
        elif requirement.category_id:
            if requirement.category_id not in category_reqs:
                category_reqs[requirement.category_id] = {}
            category_reqs[requirement.category_id][requirement.field_name] = rule
        else:
            global_reqs[requirement.field_name] = rule
    
    # Construire les settings avec héritage
    settings: dict[str, dict] = {
        "global": {},
        "category": {},
        "subcategory": {},
    }
    
    # 1. Configuration globale : partir d'un état vide et appliquer les requirements globaux
    all_fields = _blank_field_state()
    settings["global"] = {
        field_name: global_reqs.get(field_name, field_config)
        for field_name, field_config in all_fields.items()
    }
    
    # 2. Pour chaque catégorie : hériter de global puis appliquer les surcharges
    for category in categories:
        settings["category"][category.id] = {}
        for field_name in all_fields.keys():
            # Hériter de la config globale
            inherited = {**settings["global"][field_name]}
            # Appliquer la surcharge de la catégorie si elle existe
            if category.id in category_reqs and field_name in category_reqs[category.id]:
                inherited = {**category_reqs[category.id][field_name]}
            settings["category"][category.id][field_name] = inherited
        
        # 3. Pour chaque sous-catégorie : hériter de la catégorie puis appliquer les surcharges
        for subcategory in category.subcategories:
            settings["subcategory"][subcategory.id] = {}
            for field_name in all_fields.keys():
                # Hériter de la config de la catégorie parente
                inherited = {**settings["category"][category.id][field_name]}
                # Appliquer la surcharge de la sous-catégorie si elle existe
                if subcategory.id in subcategory_reqs and field_name in subcategory_reqs[subcategory.id]:
                    inherited = {**subcategory_reqs[subcategory.id][field_name]}
                settings["subcategory"][subcategory.id][field_name] = inherited

    return settings


def _input_name(scope: str, scope_id: int | None, field_name: str, attribute: str) -> str:
    scope_key = scope if scope == "global" else f"{scope}_{scope_id}"
    return f"{scope_key}__{field_name}__{attribute}"


def _upsert_requirement(
    field: BottleFieldDefinition,
    scope: str,
    scope_id: int | None,
    *,
    enabled: bool,
    required: bool,
    parent_category_id: int | None = None,
) -> None:
    filters: dict[str, int | None | str] = {
        "field_name": field.name,
        "field_id": field.id,
    }

    if scope == "category":
        filters.update({"category_id": scope_id, "subcategory_id": None})
    elif scope == "subcategory":
        filters.update({"category_id": parent_category_id, "subcategory_id": scope_id})
    else:
        filters.update({"category_id": None, "subcategory_id": None})

    requirement = AlcoholFieldRequirement.query.filter_by(**filters).first()

    if requirement is None:
        requirement = AlcoholFieldRequirement(**filters)

    requirement.is_enabled = enabled
    requirement.is_required = required and enabled
    requirement.display_order = get_display_order(field.name)
    requirement.field = field
    db.session.add(requirement)


def _next_display_order() -> int:
    last_field = (
        BottleFieldDefinition.query.order_by(
            BottleFieldDefinition.display_order.desc()
        ).first()
    )
    return (last_field.display_order if last_field else 0) + 10


def _handle_add_field(request_form, categories):
    label = (request_form.get("label") or "").strip()
    scope_ref = request_form.get("scope_ref") or "global"
    scope: str
    scope_id: int | None = None
    if ":" in scope_ref:
        scope, scope_id_raw = scope_ref.split(":", 1)
        try:
            scope_id = int(scope_id_raw)
        except ValueError:
            scope = "global"
            scope_id = None
    else:
        scope = scope_ref
    input_type = (request_form.get("input_type") or "text").strip().lower()
    if input_type not in {"text", "number", "textarea"}:
        input_type = "text"
    help_text = (request_form.get("help_text") or "").strip() or None
    placeholder = (request_form.get("placeholder") or "").strip() or None
    form_width = request_form.get("form_width", type=int) or 12
    form_width = max(1, min(form_width, 12))
    enabled = request_form.get("enabled") == "1"
    required = request_form.get("required") == "1"

    if not label:
        flash("Le libellé du champ est obligatoire pour le créer.")
        return redirect(url_for("categories.manage_field_requirements"))

    normalized_name = sanitize_field_name(label)
    existing = BottleFieldDefinition.query.filter_by(name=normalized_name).first()
    if existing:
        flash("Un champ avec ce nom existe déjà. Modifiez-le ou choisissez un autre libellé.")
        return redirect(url_for("categories.manage_field_requirements"))

    display_order = _next_display_order()

    new_field = BottleFieldDefinition(
        name=normalized_name,
        label=label,
        help_text=help_text,
        placeholder=placeholder,
        input_type=input_type,
        form_width=form_width,
        is_builtin=False,
        display_order=display_order,
    )
    db.session.add(new_field)
    db.session.flush()

    parent_category_id = None
    if scope == "category":
        parent_category_id = scope_id
    elif scope == "subcategory":
        parent_lookup = {
            sub.id: sub.category_id for category in categories for sub in category.subcategories
        }
        parent_category_id = parent_lookup.get(scope_id)

    _upsert_requirement(
        new_field,
        scope,
        scope_id,
        enabled=enabled or required,
        required=required,
        parent_category_id=parent_category_id,
    )

    db.session.commit()
    flash(f"Le champ « {label} » a été créé et associé avec succès.")
    return redirect(url_for("categories.manage_field_requirements"))


@categories_bp.route('/field-requirements', methods=['GET', 'POST'])
@admin_required
@login_required
def manage_field_requirements():
    """Permettre aux administrateurs de configurer la visibilité des champs."""

    categories = (
        AlcoholCategory.query.options(selectinload(AlcoholCategory.subcategories))
        .order_by(AlcoholCategory.display_order, AlcoholCategory.name)
        .all()
    )
    field_settings = _build_settings_snapshot(categories)
    ordered_fields = list(iter_fields())
    
    # DEBUG: Afficher les settings pour le champ 'region'
    import sys
    print("=== DEBUG field_settings pour 'region' ===", file=sys.stderr)
    print(f"Global: {field_settings['global'].get('region', 'NOT FOUND')}", file=sys.stderr)
    for cat_id, cat_settings in field_settings['category'].items():
        print(f"Category {cat_id}: {cat_settings.get('region', 'NOT FOUND')}", file=sys.stderr)
    for sub_id, sub_settings in field_settings['subcategory'].items():
        print(f"Subcategory {sub_id}: {sub_settings.get('region', 'NOT FOUND')}", file=sys.stderr)
    print("==========================================", file=sys.stderr)

    if request.method == 'POST':
        if request.form.get('action') == 'add_field':
            return _handle_add_field(request.form, categories)

        scopes: list[tuple[str, int | None]] = [('global', None)]
        subcategory_parents: dict[int, int | None] = {}

        for category in categories:
            scopes.append(('category', category.id))
            for subcategory in category.subcategories:
                subcategory_parents[subcategory.id] = category.id
                scopes.append(('subcategory', subcategory.id))

        field_map = {field.name: field for field in ordered_fields}
        for scope, scope_id in scopes:
            for field_name, field in field_map.items():
                enabled = request.form.get(_input_name(scope, scope_id, field_name, 'enabled')) == '1'
                required = request.form.get(_input_name(scope, scope_id, field_name, 'required')) == '1'
                _upsert_requirement(
                    field,
                    scope,
                    scope_id,
                    enabled=enabled,
                    required=required,
                    parent_category_id=subcategory_parents.get(scope_id) if scope == 'subcategory' else None,
                )

        db.session.commit()
        flash('Configuration des champs mise à jour avec succès.')
        return redirect(url_for('categories.manage_field_requirements'))

    return render_template(
        'field_requirements.html',
        categories=categories,
        ordered_fields=ordered_fields,
        field_settings=field_settings,
        input_name=_input_name,
        default_field_definitions=DEFAULT_FIELD_DEFINITIONS,
    )


@categories_bp.route('/fields/<int:field_id>/edit', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_field(field_id):
    """Modifier un champ existant."""
    field = BottleFieldDefinition.query.get_or_404(field_id)
    
    if request.method == 'POST':
        label = (request.form.get('label') or '').strip()
        input_type = (request.form.get('input_type') or 'text').strip().lower()
        help_text = (request.form.get('help_text') or '').strip() or None
        placeholder = (request.form.get('placeholder') or '').strip() or None
        form_width = request.form.get('form_width', type=int) or 12
        display_order = request.form.get('display_order', type=int) or field.display_order
        
        if not label:
            flash("Le libellé du champ est obligatoire.")
            return render_template('edit_field.html', field=field)
        
        if input_type not in {'text', 'number', 'textarea'}:
            input_type = 'text'
        
        form_width = max(1, min(form_width, 12))
        
        # Vérifier si le nom change et s'il existe déjà
        new_name = sanitize_field_name(label)
        if new_name != field.name:
            existing = BottleFieldDefinition.query.filter_by(name=new_name).first()
            if existing:
                flash("Un champ avec ce nom existe déjà. Choisissez un autre libellé.")
                return render_template('edit_field.html', field=field)
            
            # Si le champ n'est pas builtin, on peut changer son nom
            if not field.is_builtin:
                # Mettre à jour les extra_attributes de toutes les bouteilles
                wines = Wine.query.all()
                for wine in wines:
                    if wine.extra_attributes and field.name in wine.extra_attributes:
                        value = wine.extra_attributes.pop(field.name)
                        wine.extra_attributes[new_name] = value
                
                # Mettre à jour les requirements
                requirements = AlcoholFieldRequirement.query.filter_by(field_name=field.name).all()
                for req in requirements:
                    req.field_name = new_name
                
                field.name = new_name
        
        field.label = label
        field.input_type = input_type
        field.help_text = help_text
        field.placeholder = placeholder
        field.form_width = form_width
        field.display_order = display_order
        
        db.session.commit()
        flash(f"Le champ « {label} » a été modifié avec succès.")
        return redirect(url_for('categories.manage_field_requirements'))
    
    return render_template('edit_field.html', field=field)


@categories_bp.route('/fields/<int:field_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_field(field_id):
    """Supprimer un champ personnalisé."""
    field = BottleFieldDefinition.query.get_or_404(field_id)
    
    if field.is_builtin:
        flash("Impossible de supprimer un champ intégré.")
        return redirect(url_for('categories.manage_field_requirements'))
    
    # Supprimer le champ des extra_attributes de toutes les bouteilles
    wines = Wine.query.all()
    for wine in wines:
        if wine.extra_attributes and field.name in wine.extra_attributes:
            wine.extra_attributes.pop(field.name)
    
    # Les requirements seront supprimés automatiquement grâce au cascade
    db.session.delete(field)
    db.session.commit()
    
    flash(f"Le champ « {field.label} » a été supprimé avec succès.")
    return redirect(url_for('categories.manage_field_requirements'))


@categories_bp.route('/add', methods=['GET', 'POST'])
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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