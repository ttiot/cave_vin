"""Blueprint pour la recherche et les recommandations."""

from datetime import datetime
import re

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from models import Wine, AlcoholCategory, WineInsight, db


search_bp = Blueprint('search', __name__, url_prefix='/search')


@search_bp.route('/', methods=['GET'])
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


@search_bp.route('/a-consommer', methods=['GET'])
@login_required
def wines_to_consume():
    """Affiche les vins à consommer prochainement selon leur potentiel de garde."""
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
        year = wine.extra_attributes.get('year')
        if not year:
            continue
            
        wine_age = current_year - year
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