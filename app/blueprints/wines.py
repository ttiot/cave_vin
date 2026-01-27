"""Blueprint pour la gestion des bouteilles d'alcool."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import base64
from io import BytesIO

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import selectinload
import requests
from PIL import Image

from models import (
    AlcoholCategory,
    AlcoholFieldRequirement,
    AlcoholSubcategory,
    BottleFieldDefinition,
    Cellar,
    Wine,
    WineConsumption,
    db,
)
from app.field_config import iter_fields
from app.utils.formatters import resolve_redirect
from tasks import schedule_wine_enrichment


wines_bp = Blueprint('wines', __name__, url_prefix='/wines')


@wines_bp.route('/overview')
@login_required
def overview():
    """Afficher une vue moderne de l'ensemble des alcools par cave.
    
    Pour un sous-compte, affiche les ressources du compte parent.
    """
    owner_id = current_user.owner_id

    cellars = (
        Cellar.query.options(selectinload(Cellar.category))
        .filter(Cellar.user_id == owner_id)
        .order_by(Cellar.name.asc())
        .all()
    )

    # Trier les caves pour mettre la cave par défaut en premier
    default_cellar_id = current_user.default_cellar_id
    if default_cellar_id:
        cellars = sorted(
            cellars,
            key=lambda c: (0 if c.id == default_cellar_id else 1, c.name.lower())
        )

    wines = (
        Wine.query.options(
            selectinload(Wine.subcategory),
            selectinload(Wine.cellar),
        )
        .filter(Wine.user_id == owner_id)
        .order_by(Wine.cellar_id.asc(), Wine.name.asc())
        .all()
    )

    wines_by_cellar: dict[int, list[Wine]] = defaultdict(list)
    for wine in wines:
        wines_by_cellar[wine.cellar_id].append(wine)

    cellar_panels: list[dict] = []
    for cellar in cellars:
        cellar_wines = wines_by_cellar.get(cellar.id, [])
        total_quantity = sum((wine.quantity or 0) for wine in cellar_wines)

        subcategory_labels = sorted(
            {wine.subcategory.name for wine in cellar_wines if wine.subcategory},
            key=str.lower,
        )

        region_labels = sorted(
            {
                (wine.extra_attributes or {}).get("region")
                for wine in cellar_wines
                if (wine.extra_attributes or {}).get("region")
            },
            key=str.lower,
        )

        year_values: set[int] = set()
        for wine in cellar_wines:
            year_raw = (wine.extra_attributes or {}).get("year")
            if year_raw is None:
                continue
            try:
                year = int(year_raw)
            except (TypeError, ValueError):
                continue
            year_values.add(year)

        cellar_panels.append(
            {
                "cellar": cellar,
                "wines": cellar_wines,
                "total_quantity": total_quantity,
                "subcategory_labels": subcategory_labels,
                "region_labels": region_labels,
                "vintage_range": (
                    (min(year_values), max(year_values)) if year_values else None
                ),
                "is_default": cellar.id == default_cellar_id,
            }
        )

    return render_template(
        'wines_overview.html',
        cellar_panels=cellar_panels,
        has_cellars=bool(cellars),
        total_wine_count=len(wines),
    )


def _initial_field_state(fields: list) -> dict[str, dict[str, bool]]:
    return {
        field.name: {"enabled": False, "required": False}
        for field in fields
    }


def _fetch_requirement_mappings() -> dict[str, dict]:
    requirements = (
        AlcoholFieldRequirement.query.order_by(
            AlcoholFieldRequirement.display_order.asc(),
            AlcoholFieldRequirement.field_name.asc(),
        ).all()
    )

    mappings = {"global": {}, "category": {}, "subcategory": {}}
    for requirement in requirements:
        rule = {
            "enabled": bool(requirement.is_enabled),
            "required": bool(requirement.is_required),
        }

        if requirement.subcategory_id:
            mappings["subcategory"].setdefault(requirement.subcategory_id, {})[
                requirement.field_name
            ] = rule
        elif requirement.category_id:
            mappings["category"].setdefault(requirement.category_id, {})[
                requirement.field_name
            ] = rule
        else:
            mappings["global"][requirement.field_name] = rule

    return mappings


def _resolve_field_config(
    subcategory: AlcoholSubcategory | None,
    mappings: dict[str, dict],
    fields: list,
) -> dict[str, dict[str, bool]]:
    config = _initial_field_state(fields)

    def apply_rules(rules: dict[str, dict[str, bool]]) -> None:
        for field_name, rule in rules.items():
            if field_name not in config:
                continue
            config[field_name]["enabled"] = bool(rule.get("enabled", True))
            config[field_name]["required"] = bool(rule.get("required", False))

    apply_rules(mappings.get("global", {}))

    if subcategory is not None:
        if subcategory.category_id:
            apply_rules(mappings.get("category", {}).get(subcategory.category_id, {}))
        apply_rules(mappings.get("subcategory", {}).get(subcategory.id, {}))

    return config


def _build_field_settings(
    categories: list[AlcoholCategory],
    mappings: dict[str, dict],
    fields: list,
) -> dict[str, dict[str, dict[str, bool]]]:
    settings: dict[str, dict[str, dict[str, bool]]] = {
        "default": _resolve_field_config(None, mappings, fields)
    }

    for category in categories:
        for subcategory in category.subcategories:
            settings[str(subcategory.id)] = _resolve_field_config(
                subcategory, mappings, fields
            )

    return settings


def _parse_field_value(field: BottleFieldDefinition, raw_value: str) -> object | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    field_name = field.name

    if field_name == "year":
        try:
            year = int(value)
        except ValueError as exc:  # pragma: no cover - defensive programming
            raise ValueError("L'année doit être un nombre entier.") from exc
        if year < 1000 or year > 3000:
            raise ValueError("L'année doit être comprise entre 1000 et 3000.")
        return year

    if field_name == "volume_ml":
        try:
            volume = int(value)
        except ValueError as exc:  # pragma: no cover - defensive programming
            raise ValueError("La contenance doit être un nombre entier.") from exc
        if volume <= 0:
            raise ValueError("La contenance doit être un nombre positif.")
        return volume

    if field.input_type == "number":
        try:
            return int(value)
        except ValueError as exc:  # pragma: no cover - defensive programming
            raise ValueError(
                f"Le champ {field.label} doit être un nombre entier."
            ) from exc

    if field.input_type == "decimal":
        normalized_value = value.replace(",", ".")
        try:
            decimal_value = Decimal(normalized_value)
        except InvalidOperation as exc:  # pragma: no cover - defensive programming
            raise ValueError(
                f"Le champ {field.label} doit être un nombre à virgule."
            ) from exc
        return float(decimal_value)

    return value


def _extract_field_values(
    form_data,
    field_config: dict[str, dict[str, bool]],
    ordered_fields,
) -> tuple[dict[str, object | None], list[str]]:
    values: dict[str, object | None] = {}
    errors: list[str] = []

    for field in ordered_fields:
        field_name = field.name
        config = field_config.get(field_name, {"enabled": True, "required": False})

        if not config.get("enabled", True):
            values[field_name] = None
            continue

        raw_value = form_data.get(field_name) or ""

        if not raw_value.strip():
            if config.get("required", False):
                errors.append(
                    f"Le champ {field.label} est obligatoire pour cette catégorie."
                )
            values[field_name] = None
            continue

        try:
            values[field_name] = _parse_field_value(field, raw_value)
        except ValueError as exc:
            errors.append(str(exc))
            values[field_name] = None

    return values, errors


def _split_field_targets(
    field_values: dict[str, object | None]
) -> dict[str, object]:
    """Convert field values to extras dictionary, filtering out None values."""
    
    extras: dict[str, object] = {}
    for field_name, value in field_values.items():
        if value is not None:
            extras[field_name] = value
    
    return extras


def _collect_wine_field_values(wine: Wine | None, ordered_fields) -> dict[str, object | None]:
    """Collect all field values from wine's extra_attributes."""
    values: dict[str, object | None] = {}
    extras = (wine.extra_attributes if wine and wine.extra_attributes else {}) or {}
    
    for field in ordered_fields:
        values[field.name] = extras.get(field.name)
    
    return values


@wines_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_wine():
    """Ajouter une nouvelle bouteille en respectant les contraintes de catégorie.
    
    Pour un sous-compte, la bouteille est créée pour le compte parent.
    """
    owner_id = current_user.owner_id
    owner_account = current_user.owner_account
    
    cellars = (
        Cellar.query.filter_by(user_id=owner_id)
        .order_by(Cellar.name.asc())
        .all()
    )
    categories = AlcoholCategory.query.order_by(
        AlcoholCategory.display_order, AlcoholCategory.name
    ).all()
    mappings = _fetch_requirement_mappings()
    ordered_fields = list(iter_fields())
    field_settings = _build_field_settings(categories, mappings, ordered_fields)

    if not cellars:
        flash("Créez d'abord une cave avant d'ajouter des bouteilles.")
        return redirect(url_for('cellars.add_cellar'))

    # Pré-sélectionner la cave par défaut si définie, sinon la première cave si une seule existe
    selected_cellar_id = current_user.default_cellar_id or (cellars[0].id if len(cellars) == 1 else None)
    selected_subcategory_id = None

    if request.method == 'POST':
        barcode = (request.form.get('barcode') or '').strip() or None
        name = (request.form.get('name') or '').strip()
        quantity = request.form.get('quantity', type=int)
        cellar_id = request.form.get('cellar_id', type=int)
        subcategory_id = request.form.get('subcategory_id', type=int)

        selected_cellar_id = cellar_id or selected_cellar_id
        selected_subcategory_id = subcategory_id

        errors: list[str] = []

        if quantity is None or quantity <= 0:
            errors.append("La quantité doit être supérieure ou égale à 1.")
        else:
            quantity = int(quantity)

        cellar = (
            Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first()
            if cellar_id
            else None
        )
        if not cellar:
            errors.append("Veuillez sélectionner une cave pour y ajouter la bouteille.")

        subcategory = (
            AlcoholSubcategory.query.get(subcategory_id) if subcategory_id else None
        )
        if subcategory_id and not subcategory:
            errors.append("La sous-catégorie sélectionnée est introuvable.")

        field_config = (
            field_settings.get(str(subcategory_id)) if subcategory_id is not None else None
        ) or field_settings["default"]
        field_values, field_errors = _extract_field_values(
            request.form, field_config, ordered_fields
        )
        errors.extend(field_errors)

        image_url = None
        if barcode and not name:
            try:
                response = requests.get(
                    f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json",
                    timeout=6,
                )
                if response.status_code == 200:
                    data = response.json().get('product', {}) or {}
                    name = (
                        data.get('product_name')
                        or data.get('brands')
                        or 'Bouteille sans nom'
                    )
                    image_url = data.get('image_url')
            except Exception:  # pragma: no cover - appels réseau best effort
                image_url = None

        if errors:
            for error in errors:
                flash(error)
            return render_template(
                'add_wine.html',
                cellars=cellars,
                categories=categories,
                selected_cellar_id=selected_cellar_id,
                selected_subcategory_id=selected_subcategory_id,
                field_settings=field_settings,
                ordered_fields=ordered_fields,
                form_data=request.form,
            )

        extra_values = _split_field_targets(field_values)
        wine = Wine(
            name=name or 'Bouteille sans nom',
            barcode=barcode,
            image_url=image_url,
            quantity=quantity or 1,
            cellar=cellar,
            subcategory=subcategory,
            extra_attributes=extra_values,
            owner=owner_account,
        )
        db.session.add(wine)
        db.session.commit()
        schedule_wine_enrichment(wine.id)
        flash('Bouteille ajoutée avec succès.')
        return redirect(url_for('main.index'))

    return render_template(
        'add_wine.html',
        cellars=cellars,
        categories=categories,
        selected_cellar_id=selected_cellar_id,
        selected_subcategory_id=selected_subcategory_id,
        field_settings=field_settings,
        ordered_fields=ordered_fields,
    )


@wines_bp.route('/<int:wine_id>', methods=['GET'])
@login_required
def wine_detail(wine_id):
    """Afficher les détails d'une bouteille.
    
    Pour un sous-compte, affiche les bouteilles du compte parent.
    """
    owner_id = current_user.owner_id
    wine = (
        Wine.query.options(
            selectinload(Wine.cellar),
            selectinload(Wine.insights),
            selectinload(Wine.consumptions),
        )
        .filter(Wine.id == wine_id, Wine.user_id == owner_id)
        .first_or_404()
    )
    ordered_fields = list(iter_fields())
    field_values = _collect_wine_field_values(wine, ordered_fields)
    return render_template(
        'wine_detail.html',
        wine=wine,
        ordered_fields=ordered_fields,
        field_values=field_values,
    )


@wines_bp.route('/<int:wine_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_wine(wine_id):
    """Modifier une bouteille existante.
    
    Pour un sous-compte, permet de modifier les bouteilles du compte parent.
    """
    owner_id = current_user.owner_id
    wine = (
        Wine.query.filter_by(id=wine_id, user_id=owner_id).first_or_404()
    )
    cellars = (
        Cellar.query.filter_by(user_id=owner_id)
        .order_by(Cellar.name.asc())
        .all()
    )
    categories = AlcoholCategory.query.order_by(
        AlcoholCategory.display_order, AlcoholCategory.name
    ).all()
    mappings = _fetch_requirement_mappings()
    ordered_fields = list(iter_fields())
    field_settings = _build_field_settings(categories, mappings, ordered_fields)
    selected_subcategory_id = wine.subcategory_id
    existing_field_values = _collect_wine_field_values(wine, ordered_fields)

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        quantity = request.form.get('quantity', type=int)
        cellar_id = request.form.get('cellar_id', type=int)
        subcategory_id = request.form.get('subcategory_id', type=int)
        remove_image = request.form.get('remove_image') == '1'

        selected_subcategory_id = subcategory_id

        errors: list[str] = []

        if not name:
            errors.append("Le nom de la bouteille est obligatoire.")

        if quantity is None or quantity < 0:
            errors.append("La quantité doit être un nombre positif ou nul.")
        else:
            quantity = int(quantity)

        cellar = (
            Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first()
            if cellar_id
            else None
        )
        if not cellar:
            errors.append("Veuillez sélectionner une cave existante.")

        subcategory = (
            AlcoholSubcategory.query.get(subcategory_id) if subcategory_id else None
        )
        if subcategory_id and not subcategory:
            errors.append("La sous-catégorie sélectionnée est introuvable.")

        field_config = (
            field_settings.get(str(subcategory_id)) if subcategory_id is not None else None
        ) or field_settings["default"]
        field_values, field_errors = _extract_field_values(
            request.form, field_config, ordered_fields
        )
        errors.extend(field_errors)

        if errors:
            for error in errors:
                flash(error)
            return render_template(
                'edit_wine.html',
                wine=wine,
                cellars=cellars,
                categories=categories,
                field_settings=field_settings,
                ordered_fields=ordered_fields,
                selected_subcategory_id=selected_subcategory_id,
                form_data=request.form,
                existing_field_values=existing_field_values,
            )

        extra_values = _split_field_targets(field_values)
        wine.name = name
        wine.extra_attributes = extra_values
        wine.quantity = quantity
        wine.cellar = cellar
        wine.subcategory = subcategory

        # Gestion de l'image
        if remove_image:
            wine.label_image_data = None
        
        if 'label_image' in request.files:
            file = request.files['label_image']
            if file and file.filename:
                try:
                    # Lire et traiter l'image
                    image = Image.open(file.stream)
                    
                    # Convertir en RGB si nécessaire (pour les PNG avec transparence)
                    if image.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        if image.mode == 'P':
                            image = image.convert('RGBA')
                        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')
                    
                    # Redimensionner l'image pour optimiser la taille (max 800px de largeur)
                    max_width = 800
                    if image.width > max_width:
                        ratio = max_width / image.width
                        new_height = int(image.height * ratio)
                        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Convertir en base64
                    buffer = BytesIO()
                    image.save(buffer, format='JPEG', quality=85, optimize=True)
                    image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    
                    wine.label_image_data = image_data
                except Exception as e:
                    errors.append(f"Erreur lors du traitement de l'image : {str(e)}")

        if errors:
            for error in errors:
                flash(error)
            return render_template(
                'edit_wine.html',
                wine=wine,
                cellars=cellars,
                categories=categories,
                field_settings=field_settings,
                ordered_fields=ordered_fields,
                selected_subcategory_id=selected_subcategory_id,
                form_data=request.form,
                existing_field_values=existing_field_values,
            )

        db.session.commit()
        flash('Bouteille modifiée avec succès.')
        return redirect(url_for('wines.wine_detail', wine_id=wine.id))

    return render_template(
        'edit_wine.html',
        wine=wine,
        cellars=cellars,
        categories=categories,
        field_settings=field_settings,
        ordered_fields=ordered_fields,
        selected_subcategory_id=selected_subcategory_id,
        existing_field_values=existing_field_values,
    )


@wines_bp.route('/<int:wine_id>/refresh', methods=['POST'])
@login_required
def refresh_wine(wine_id):
    """Relancer la récupération des informations d'une bouteille.
    
    Pour un sous-compte, permet de rafraîchir les bouteilles du compte parent.
    """
    owner_id = current_user.owner_id
    wine = (
        Wine.query.filter_by(id=wine_id, user_id=owner_id).first_or_404()
    )
    schedule_wine_enrichment(wine.id)
    flash("La récupération des informations a été relancée.")
    return redirect(resolve_redirect('main.index'))


@wines_bp.route('/<int:wine_id>/consume', methods=['POST'])
@login_required
def consume_wine(wine_id):
    """Marquer une bouteille comme consommée.
    
    Pour un sous-compte, permet de consommer les bouteilles du compte parent.
    La consommation est enregistrée au nom du compte propriétaire.
    """
    owner_id = current_user.owner_id
    wine = (
        Wine.query.filter_by(id=wine_id, user_id=owner_id).first_or_404()
    )
    if wine.quantity <= 0:
        flash("Cette bouteille n'est plus disponible dans la cave.")
        return redirect(resolve_redirect('main.index'))

    wine.quantity -= 1

    # Récupérer les valeurs depuis extra_attributes
    extras = wine.extra_attributes or {}

    comment = request.form.get('comment', '').strip() or None

    consumption = WineConsumption(
        wine=wine,
        user=wine.owner,
        quantity=1,
        comment=comment,
        snapshot_name=wine.name,
        snapshot_year=extras.get('year'),
        snapshot_region=extras.get('region'),
        snapshot_grape=extras.get('grape'),
        snapshot_cellar=wine.cellar.name if wine.cellar else None,
    )
    db.session.add(consumption)
    db.session.commit()

    flash("Une bouteille a été marquée comme consommée.")
    return redirect(resolve_redirect('main.index'))


@wines_bp.route('/<int:wine_id>/delete', methods=['POST'])
@login_required
def delete_wine(wine_id):
    """Supprimer une bouteille de la cave.
    
    Pour un sous-compte, permet de supprimer les bouteilles du compte parent.
    """
    owner_id = current_user.owner_id
    wine = (
        Wine.query.filter_by(id=wine_id, user_id=owner_id).first_or_404()
    )
    db.session.delete(wine)
    db.session.commit()
    flash("La bouteille a été supprimée de votre cave.")
    return redirect(resolve_redirect('main.index'))