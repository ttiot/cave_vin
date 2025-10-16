"""Blueprint principal pour les routes générales."""

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy.orm import selectinload

from models import Wine, Cellar, WineConsumption, AlcoholSubcategory


main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """Page d'accueil affichant tous les vins disponibles organisés par cave."""
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


@main_bp.route('/consommations', methods=['GET'])
@login_required
def consumption_history():
    """Affiche l'historique des consommations."""
    consumptions = (
        WineConsumption.query.options(selectinload(WineConsumption.wine))
        .order_by(WineConsumption.consumed_at.desc())
        .all()
    )
    return render_template('consumption_history.html', consumptions=consumptions)