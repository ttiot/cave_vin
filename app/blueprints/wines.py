"""Blueprint pour la gestion des vins."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.orm import selectinload
import requests

from models import Wine, Cellar, AlcoholCategory, WineConsumption, db
from app.utils.formatters import resolve_redirect
from tasks import schedule_wine_enrichment


wines_bp = Blueprint('wines', __name__, url_prefix='/wines')


@wines_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_wine():
    """Ajouter un nouveau vin."""
    cellars = Cellar.query.order_by(Cellar.name.asc()).all()
    categories = AlcoholCategory.query.order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()

    if not cellars:
        flash("Créez d'abord une cave avant d'ajouter des bouteilles.")
        return redirect(url_for('cellars.add_cellar'))

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
        return redirect(url_for('main.index'))
    
    selected_cellar_id = cellars[0].id if len(cellars) == 1 else None
    return render_template('add_wine.html', cellars=cellars, categories=categories, selected_cellar_id=selected_cellar_id)


@wines_bp.route('/<int:wine_id>', methods=['GET'])
@login_required
def wine_detail(wine_id):
    """Afficher les détails d'un vin."""
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


@wines_bp.route('/<int:wine_id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('wines.wine_detail', wine_id=wine.id))
    
    return render_template('edit_wine.html', wine=wine, cellars=cellars, categories=categories)


@wines_bp.route('/<int:wine_id>/refresh', methods=['POST'])
@login_required
def refresh_wine(wine_id):
    """Relancer la récupération des informations d'un vin."""
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
        flash("Ce vin n'est plus disponible dans la cave.")
        return redirect(resolve_redirect('main.index'))

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
    return redirect(resolve_redirect('main.index'))


@wines_bp.route('/<int:wine_id>/delete', methods=['POST'])
@login_required
def delete_wine(wine_id):
    """Supprimer un vin de la cave."""
    wine = Wine.query.get_or_404(wine_id)
    db.session.delete(wine)
    db.session.commit()
    flash("Le vin a été supprimé de votre cave.")
    return redirect(resolve_redirect('main.index'))