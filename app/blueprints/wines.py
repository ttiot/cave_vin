"""Blueprint pour la gestion des bouteilles d'alcool."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.orm import selectinload
import requests

from models import (
    AlcoholCategory,
    AlcoholFieldRequirement,
    AlcoholSubcategory,
    Cellar,
    Wine,
    WineConsumption,
    db,
)
from app.field_config import iter_fields
from app.utils.formatters import resolve_redirect
from tasks import schedule_wine_enrichment


wines_bp = Blueprint('wines', __name__, url_prefix='/wines')


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


def _parse_field_value(field_name: str, raw_value: str) -> object | None:
    value = (raw_value or "").strip()
    if not value:
        return None

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
            values[field_name] = _parse_field_value(field_name, raw_value)
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
    """Ajouter une nouvelle bouteille en respectant les contraintes de catégorie."""
    cellars = Cellar.query.order_by(Cellar.name.asc()).all()
    categories = AlcoholCategory.query.order_by(
        AlcoholCategory.display_order, AlcoholCategory.name
    ).all()
    mappings = _fetch_requirement_mappings()
    ordered_fields = list(iter_fields())
    field_settings = _build_field_settings(categories, mappings, ordered_fields)

    if not cellars:
        flash("Créez d'abord une cave avant d'ajouter des bouteilles.")
        return redirect(url_for('cellars.add_cellar'))

    selected_cellar_id = cellars[0].id if len(cellars) == 1 else None
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

        cellar = Cellar.query.get(cellar_id) if cellar_id else None
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
    """Afficher les détails d'une bouteille."""
    wine = (
        Wine.query.options(
            selectinload(Wine.cellar),
            selectinload(Wine.insights),
            selectinload(Wine.consumptions),
        )
        .filter_by(id=wine_id)
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
    """Modifier une bouteille existante."""
    wine = Wine.query.get_or_404(wine_id)
    cellars = Cellar.query.order_by(Cellar.name.asc()).all()
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

        selected_subcategory_id = subcategory_id

        errors: list[str] = []

        if not name:
            errors.append("Le nom de la bouteille est obligatoire.")

        if quantity is None or quantity < 0:
            errors.append("La quantité doit être un nombre positif ou nul.")
        else:
            quantity = int(quantity)

        cellar = Cellar.query.get(cellar_id) if cellar_id else None
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
    """Relancer la récupération des informations d'une bouteille."""
    wine = Wine.query.get_or_404(wine_id)
    schedule_wine_enrichment(wine.id)
    flash("La récupération des informations a été relancée.")
    return redirect(resolve_redirect('main.index'))


@wines_bp.route('/<int:wine_id>/consume', methods=['POST'])
@login_required
def consume_wine(wine_id):
    """Marquer une bouteille comme consommée."""
    wine = Wine.query.get_or_404(wine_id)
    if wine.quantity <= 0:
        flash("Cette bouteille n'est plus disponible dans la cave.")
        return redirect(resolve_redirect('main.index'))

    wine.quantity -= 1
    
    # Récupérer les valeurs depuis extra_attributes
    extras = wine.extra_attributes or {}
    
    consumption = WineConsumption(
        wine=wine,
        quantity=1,
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
    """Supprimer une bouteille de la cave."""
    wine = Wine.query.get_or_404(wine_id)
    db.session.delete(wine)
    db.session.commit()
    flash("La bouteille a été supprimée de votre cave.")
    return redirect(resolve_redirect('main.index'))