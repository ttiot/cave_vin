"""Blueprint pour les conseils et recommandations de vins."""

from __future__ import annotations

from flask import Blueprint, render_template, request, flash, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import selectinload

from app.models import Wine, AlcoholSubcategory, db
from services.wine_pairing_service import WinePairingService

pairing_bp = Blueprint("pairing", __name__, url_prefix="/conseils")


def _wine_to_dict(wine: Wine) -> dict:
    """Convertit un objet Wine en dictionnaire pour l'IA."""
    extra = wine.extra_attributes or {}
    return {
        "id": wine.id,
        "name": wine.name,
        "quantity": wine.quantity,
        "cellar_name": wine.cellar.name if wine.cellar else None,
        "subcategory_name": wine.subcategory.name if wine.subcategory else None,
        "category_name": (
            wine.subcategory.category.name
            if wine.subcategory and wine.subcategory.category
            else None
        ),
        "extra_attributes": extra,
    }


@pairing_bp.route("/", methods=["GET", "POST"])
@login_required
def wine_pairing():
    """Page de conseils de vins pour les accords mets-vins."""
    owner_id = current_user.owner_id
    result = None
    dish = ""
    error = None

    if request.method == "POST":
        dish = request.form.get("dish", "").strip()
        
        if not dish:
            flash("Veuillez indiquer un plat pour obtenir des conseils.", "warning")
        else:
            # Récupérer tous les vins en stock de l'utilisateur
            wines = Wine.query.options(
                selectinload(Wine.cellar),
                selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
            ).filter(
                Wine.user_id == owner_id,
                Wine.quantity > 0
            ).all()

            if not wines:
                flash("Vous n'avez aucun vin en stock. Ajoutez des bouteilles pour obtenir des conseils.", "warning")
            else:
                # Convertir les vins en format JSON pour l'IA
                wines_data = [_wine_to_dict(w) for w in wines]

                # Initialiser le service et obtenir les recommandations
                try:
                    service = WinePairingService.from_app(current_app)
                    result = service.get_recommendations(dish, wines_data)
                    
                    if result is None:
                        error = "Le service de recommandation n'est pas disponible. Vérifiez la configuration OpenAI."
                        flash(error, "danger")
                except Exception as e:
                    current_app.logger.error("Erreur lors de la génération des recommandations: %s", e)
                    error = "Une erreur est survenue lors de la génération des recommandations."
                    flash(error, "danger")

    return render_template(
        "wine_pairing.html",
        dish=dish,
        result=result,
        error=error,
    )


@pairing_bp.route("/api", methods=["POST"])
@login_required
def wine_pairing_api():
    """API endpoint pour obtenir des recommandations de vins (AJAX)."""
    owner_id = current_user.owner_id
    data = request.get_json() or {}
    dish = data.get("dish", "").strip()

    if not dish:
        return jsonify({"error": "Le plat est requis"}), 400

    # Récupérer tous les vins en stock de l'utilisateur
    wines = Wine.query.options(
        selectinload(Wine.cellar),
        selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
    ).filter(
        Wine.user_id == owner_id,
        Wine.quantity > 0
    ).all()

    if not wines:
        return jsonify({"error": "Aucun vin en stock"}), 404

    # Convertir les vins en format JSON pour l'IA
    wines_data = [_wine_to_dict(w) for w in wines]

    # Initialiser le service et obtenir les recommandations
    try:
        service = WinePairingService.from_app(current_app)
        result = service.get_recommendations(dish, wines_data)
        
        if result is None:
            return jsonify({"error": "Service de recommandation non disponible"}), 503

        return jsonify({
            "dish": result.dish,
            "explanation": result.explanation,
            "priority_wines": [
                {
                    "wine_id": w.wine_id,
                    "wine_name": w.wine_name,
                    "reason": w.reason,
                    "score": w.score,
                    "cellar_name": w.cellar_name,
                    "year": w.year,
                    "region": w.region,
                    "grape": w.grape,
                    "subcategory": w.subcategory,
                    "garde_info": w.garde_info,
                }
                for w in result.priority_wines
            ],
            "best_wines": [
                {
                    "wine_id": w.wine_id,
                    "wine_name": w.wine_name,
                    "reason": w.reason,
                    "score": w.score,
                    "cellar_name": w.cellar_name,
                    "year": w.year,
                    "region": w.region,
                    "grape": w.grape,
                    "subcategory": w.subcategory,
                    "garde_info": w.garde_info,
                }
                for w in result.best_wines
            ],
            "generated_at": result.generated_at.isoformat(),
        })

    except Exception as e:
        current_app.logger.error("Erreur API recommandations: %s", e)
        return jsonify({"error": "Erreur lors de la génération des recommandations"}), 500
