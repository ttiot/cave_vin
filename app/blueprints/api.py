"""Blueprint API REST pour l'accès programmatique aux données."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request, g
from sqlalchemy.orm import selectinload

from models import (
    AlcoholCategory,
    AlcoholSubcategory,
    Cellar,
    CellarCategory,
    Wine,
    WineConsumption,
    WineInsight,
    db,
)
from app.utils.decorators import api_token_required


api_bp = Blueprint("api", __name__, url_prefix="/api")


# ============================================================================
# Helpers
# ============================================================================


def _wine_to_dict(wine: Wine, include_insights: bool = False) -> dict[str, Any]:
    """Convertit un objet Wine en dictionnaire JSON-serializable."""
    data = {
        "id": wine.id,
        "name": wine.name,
        "barcode": wine.barcode,
        "quantity": wine.quantity,
        "image_url": wine.image_url,
        "cellar_id": wine.cellar_id,
        "cellar_name": wine.cellar.name if wine.cellar else None,
        "subcategory_id": wine.subcategory_id,
        "subcategory_name": wine.subcategory.name if wine.subcategory else None,
        "category_name": (
            wine.subcategory.category.name
            if wine.subcategory and wine.subcategory.category
            else None
        ),
        "extra_attributes": wine.extra_attributes or {},
        "created_at": wine.created_at.isoformat() if wine.created_at else None,
        "updated_at": wine.updated_at.isoformat() if wine.updated_at else None,
    }
    
    if include_insights:
        data["insights"] = [
            {
                "id": insight.id,
                "category": insight.category,
                "title": insight.title,
                "content": insight.content,
                "source_name": insight.source_name,
                "source_url": insight.source_url,
            }
            for insight in wine.insights
        ]
    
    return data


def _cellar_to_dict(cellar: Cellar) -> dict[str, Any]:
    """Convertit un objet Cellar en dictionnaire JSON-serializable."""
    return {
        "id": cellar.id,
        "name": cellar.name,
        "category_id": cellar.category_id,
        "category_name": cellar.category.name if cellar.category else None,
        "floor_count": cellar.floor_count,
        "capacity": cellar.capacity,
        "floor_capacities": cellar.floor_capacities,
    }


def _consumption_to_dict(consumption: WineConsumption) -> dict[str, Any]:
    """Convertit un objet WineConsumption en dictionnaire JSON-serializable."""
    return {
        "id": consumption.id,
        "wine_id": consumption.wine_id,
        "consumed_at": consumption.consumed_at.isoformat() if consumption.consumed_at else None,
        "quantity": consumption.quantity,
        "comment": consumption.comment,
        "snapshot_name": consumption.snapshot_name,
        "snapshot_year": consumption.snapshot_year,
        "snapshot_region": consumption.snapshot_region,
        "snapshot_grape": consumption.snapshot_grape,
        "snapshot_cellar": consumption.snapshot_cellar,
    }


# ============================================================================
# Wines endpoints
# ============================================================================


@api_bp.route("/wines", methods=["GET"])
@api_token_required
def list_wines():
    """Liste toutes les bouteilles de l'utilisateur.
    
    Pour un sous-compte, retourne les bouteilles du compte parent.
    
    Query params:
        - cellar_id: Filtrer par cave
        - subcategory_id: Filtrer par sous-catégorie
        - in_stock: Si "true", ne retourne que les bouteilles en stock (quantity > 0)
        - include_insights: Si "true", inclut les insights
        - limit: Nombre max de résultats (défaut: 100)
        - offset: Décalage pour pagination (défaut: 0)
    """
    user = g.api_user
    owner_id = user.owner_id
    
    query = Wine.query.options(
        selectinload(Wine.cellar),
        selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
    ).filter(Wine.user_id == owner_id)
    
    # Filtres
    cellar_id = request.args.get("cellar_id", type=int)
    if cellar_id:
        query = query.filter(Wine.cellar_id == cellar_id)
    
    subcategory_id = request.args.get("subcategory_id", type=int)
    if subcategory_id:
        query = query.filter(Wine.subcategory_id == subcategory_id)
    
    in_stock = request.args.get("in_stock", "").lower() == "true"
    if in_stock:
        query = query.filter(Wine.quantity > 0)
    
    # Pagination
    limit = min(request.args.get("limit", 100, type=int), 500)
    offset = request.args.get("offset", 0, type=int)
    
    total = query.count()
    wines = query.order_by(Wine.name.asc()).offset(offset).limit(limit).all()
    
    include_insights = request.args.get("include_insights", "").lower() == "true"
    if include_insights:
        # Charger les insights si demandé
        wine_ids = [w.id for w in wines]
        Wine.query.options(selectinload(Wine.insights)).filter(Wine.id.in_(wine_ids)).all()
    
    return jsonify({
        "wines": [_wine_to_dict(w, include_insights=include_insights) for w in wines],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@api_bp.route("/wines/<int:wine_id>", methods=["GET"])
@api_token_required
def get_wine(wine_id: int):
    """Récupère les détails d'une bouteille.
    
    Pour un sous-compte, accède aux bouteilles du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    wine = Wine.query.options(
        selectinload(Wine.cellar),
        selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
        selectinload(Wine.insights),
    ).filter(Wine.id == wine_id, Wine.user_id == owner_id).first()
    
    if not wine:
        return jsonify({"error": "Bouteille non trouvée"}), 404
    
    return jsonify(_wine_to_dict(wine, include_insights=True))


@api_bp.route("/wines", methods=["POST"])
@api_token_required
def create_wine():
    """Crée une nouvelle bouteille.
    
    Pour un sous-compte, la bouteille est créée pour le compte parent.
    
    Body JSON:
        - name: Nom de la bouteille (requis)
        - cellar_id: ID de la cave (requis)
        - quantity: Quantité (défaut: 1)
        - barcode: Code-barres (optionnel)
        - subcategory_id: ID de la sous-catégorie (optionnel)
        - extra_attributes: Attributs supplémentaires (optionnel)
    """
    user = g.api_user
    owner_id = user.owner_id
    owner_account = user.owner_account
    data = request.get_json() or {}
    
    # Validation
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Le nom est requis"}), 400
    
    cellar_id = data.get("cellar_id")
    if not cellar_id:
        return jsonify({"error": "cellar_id est requis"}), 400
    
    cellar = Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first()
    if not cellar:
        return jsonify({"error": "Cave non trouvée"}), 404
    
    subcategory_id = data.get("subcategory_id")
    subcategory = None
    if subcategory_id:
        subcategory = AlcoholSubcategory.query.get(subcategory_id)
        if not subcategory:
            return jsonify({"error": "Sous-catégorie non trouvée"}), 404
    
    wine = Wine(
        name=name,
        barcode=data.get("barcode"),
        quantity=data.get("quantity", 1),
        cellar=cellar,
        subcategory=subcategory,
        extra_attributes=data.get("extra_attributes", {}),
        owner=owner_account,
    )
    
    db.session.add(wine)
    db.session.commit()
    
    return jsonify(_wine_to_dict(wine)), 201


@api_bp.route("/wines/<int:wine_id>", methods=["PUT", "PATCH"])
@api_token_required
def update_wine(wine_id: int):
    """Met à jour une bouteille existante.
    
    Pour un sous-compte, permet de modifier les bouteilles du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    data = request.get_json() or {}
    
    wine = Wine.query.filter_by(id=wine_id, user_id=owner_id).first()
    if not wine:
        return jsonify({"error": "Bouteille non trouvée"}), 404
    
    if "name" in data:
        wine.name = (data["name"] or "").strip() or wine.name
    
    if "quantity" in data:
        wine.quantity = max(0, int(data["quantity"]))
    
    if "barcode" in data:
        wine.barcode = data["barcode"]
    
    if "cellar_id" in data:
        cellar = Cellar.query.filter_by(id=data["cellar_id"], user_id=owner_id).first()
        if not cellar:
            return jsonify({"error": "Cave non trouvée"}), 404
        wine.cellar = cellar
    
    if "subcategory_id" in data:
        if data["subcategory_id"]:
            subcategory = AlcoholSubcategory.query.get(data["subcategory_id"])
            if not subcategory:
                return jsonify({"error": "Sous-catégorie non trouvée"}), 404
            wine.subcategory = subcategory
        else:
            wine.subcategory = None
    
    if "extra_attributes" in data:
        wine.extra_attributes = data["extra_attributes"]
    
    db.session.commit()
    
    return jsonify(_wine_to_dict(wine))


@api_bp.route("/wines/<int:wine_id>", methods=["DELETE"])
@api_token_required
def delete_wine(wine_id: int):
    """Supprime une bouteille.
    
    Pour un sous-compte, permet de supprimer les bouteilles du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    wine = Wine.query.filter_by(id=wine_id, user_id=owner_id).first()
    if not wine:
        return jsonify({"error": "Bouteille non trouvée"}), 404
    
    db.session.delete(wine)
    db.session.commit()
    
    return jsonify({"message": "Bouteille supprimée"}), 200


@api_bp.route("/wines/<int:wine_id>/consume", methods=["POST"])
@api_token_required
def consume_wine(wine_id: int):
    """Marque une bouteille comme consommée.
    
    Pour un sous-compte, permet de consommer les bouteilles du compte parent.
    
    Body JSON:
        - quantity: Nombre de bouteilles à consommer (défaut: 1)
        - comment: Commentaire optionnel
    """
    user = g.api_user
    owner_id = user.owner_id
    data = request.get_json() or {}
    
    wine = Wine.query.options(selectinload(Wine.cellar)).filter_by(
        id=wine_id, user_id=owner_id
    ).first()
    
    if not wine:
        return jsonify({"error": "Bouteille non trouvée"}), 404
    
    quantity_to_consume = data.get("quantity", 1)
    if quantity_to_consume <= 0:
        return jsonify({"error": "La quantité doit être positive"}), 400
    
    if wine.quantity < quantity_to_consume:
        return jsonify({"error": "Stock insuffisant"}), 400
    
    wine.quantity -= quantity_to_consume
    
    extras = wine.extra_attributes or {}
    consumption = WineConsumption(
        wine=wine,
        user=wine.owner,
        quantity=quantity_to_consume,
        comment=data.get("comment"),
        snapshot_name=wine.name,
        snapshot_year=extras.get("year"),
        snapshot_region=extras.get("region"),
        snapshot_grape=extras.get("grape"),
        snapshot_cellar=wine.cellar.name if wine.cellar else None,
    )
    
    db.session.add(consumption)
    db.session.commit()
    
    return jsonify({
        "message": f"{quantity_to_consume} bouteille(s) consommée(s)",
        "remaining_quantity": wine.quantity,
        "consumption": _consumption_to_dict(consumption),
    })


# ============================================================================
# Cellars endpoints
# ============================================================================


@api_bp.route("/cellars", methods=["GET"])
@api_token_required
def list_cellars():
    """Liste toutes les caves de l'utilisateur.
    
    Pour un sous-compte, retourne les caves du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    cellars = Cellar.query.options(
        selectinload(Cellar.category)
    ).filter_by(user_id=owner_id).order_by(Cellar.name.asc()).all()
    
    return jsonify({
        "cellars": [_cellar_to_dict(c) for c in cellars],
        "total": len(cellars),
    })


@api_bp.route("/cellars/<int:cellar_id>", methods=["GET"])
@api_token_required
def get_cellar(cellar_id: int):
    """Récupère les détails d'une cave avec ses bouteilles.
    
    Pour un sous-compte, accède aux caves du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    cellar = Cellar.query.options(
        selectinload(Cellar.category),
    ).filter_by(id=cellar_id, user_id=owner_id).first()
    
    if not cellar:
        return jsonify({"error": "Cave non trouvée"}), 404
    
    # Charger les vins séparément car Cellar.wines est lazy="dynamic"
    wines = Wine.query.options(
        selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
    ).filter_by(cellar_id=cellar.id, user_id=owner_id).all()
    
    data = _cellar_to_dict(cellar)
    data["wines"] = [_wine_to_dict(w) for w in wines]
    data["total_bottles"] = sum(w.quantity or 0 for w in wines)
    
    return jsonify(data)


# ============================================================================
# Search endpoint
# ============================================================================


@api_bp.route("/search", methods=["GET"])
@api_token_required
def search_wines():
    """Recherche multi-critères dans les bouteilles.
    
    Pour un sous-compte, recherche dans les ressources du compte parent.
    
    Query params:
        - q: Recherche textuelle dans le nom
        - subcategory_id: Filtrer par sous-catégorie
        - food_pairing: Recherche dans les accords mets-vins (insights)
        - in_stock: Si "true", ne retourne que les bouteilles en stock
        - limit: Nombre max de résultats (défaut: 50)
    """
    user = g.api_user
    owner_id = user.owner_id
    
    query = Wine.query.options(
        selectinload(Wine.cellar),
        selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
        selectinload(Wine.insights),
    ).filter(Wine.user_id == owner_id)
    
    # Recherche textuelle
    q = request.args.get("q", "").strip()
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(Wine.name.ilike(f"%{escaped}%", escape="\\"))
    
    # Filtre par sous-catégorie
    subcategory_id = request.args.get("subcategory_id", type=int)
    if subcategory_id:
        query = query.filter(Wine.subcategory_id == subcategory_id)
    
    # Filtre par stock
    in_stock = request.args.get("in_stock", "").lower() == "true"
    if in_stock:
        query = query.filter(Wine.quantity > 0)
    
    # Recherche dans les accords mets-vins
    food_pairing = request.args.get("food_pairing", "").strip()
    if food_pairing:
        escaped = food_pairing.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        wine_ids = db.session.query(WineInsight.wine_id).filter(
            WineInsight.content.ilike(pattern, escape="\\")
        ).distinct().subquery()
        query = query.filter(Wine.id.in_(wine_ids))
    
    limit = min(request.args.get("limit", 50, type=int), 200)
    wines = query.order_by(Wine.name.asc()).limit(limit).all()
    
    return jsonify({
        "wines": [_wine_to_dict(w, include_insights=True) for w in wines],
        "total": len(wines),
    })


# ============================================================================
# Statistics endpoint
# ============================================================================


@api_bp.route("/statistics", methods=["GET"])
@api_token_required
def get_statistics():
    """Retourne les statistiques de la cave.
    
    Pour un sous-compte, retourne les statistiques du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    wines = Wine.query.options(
        selectinload(Wine.cellar),
        selectinload(Wine.subcategory).selectinload(AlcoholSubcategory.category),
        selectinload(Wine.consumptions),
    ).filter(Wine.user_id == owner_id).all()
    
    total_bottles = sum(w.quantity or 0 for w in wines if (w.quantity or 0) > 0)
    total_references = len([w for w in wines if (w.quantity or 0) > 0])
    
    # Distribution par catégorie
    category_distribution: dict[str, int] = defaultdict(int)
    subcategory_distribution: dict[str, int] = defaultdict(int)
    
    for wine in wines:
        quantity = wine.quantity or 0
        if quantity <= 0:
            continue
        
        if wine.subcategory and wine.subcategory.category:
            cat_name = wine.subcategory.category.name
            sub_name = wine.subcategory.name
        else:
            cat_name = "Non catégorisé"
            sub_name = "Sans sous-catégorie"
        
        category_distribution[cat_name] += quantity
        subcategory_distribution[f"{cat_name} - {sub_name}"] += quantity
    
    # Distribution par cave
    cellar_distribution: dict[str, int] = defaultdict(int)
    for wine in wines:
        if (wine.quantity or 0) <= 0:
            continue
        cellar_name = wine.cellar.name if wine.cellar else "Sans cave"
        cellar_distribution[cellar_name] += wine.quantity
    
    # Consommations
    total_consumed = sum(
        sum(c.quantity or 0 for c in w.consumptions)
        for w in wines
    )
    
    return jsonify({
        "total_bottles": total_bottles,
        "total_references": total_references,
        "total_consumed": total_consumed,
        "category_distribution": dict(category_distribution),
        "subcategory_distribution": dict(subcategory_distribution),
        "cellar_distribution": dict(cellar_distribution),
    })


# ============================================================================
# Categories endpoints
# ============================================================================


@api_bp.route("/categories", methods=["GET"])
@api_token_required
def list_categories():
    """Liste toutes les catégories d'alcool avec leurs sous-catégories."""
    categories = AlcoholCategory.query.options(
        selectinload(AlcoholCategory.subcategories)
    ).order_by(AlcoholCategory.display_order, AlcoholCategory.name).all()
    
    return jsonify({
        "categories": [
            {
                "id": cat.id,
                "name": cat.name,
                "description": cat.description,
                "subcategories": [
                    {
                        "id": sub.id,
                        "name": sub.name,
                        "description": sub.description,
                        "badge_bg_color": sub.badge_bg_color,
                        "badge_text_color": sub.badge_text_color,
                    }
                    for sub in cat.subcategories
                ],
            }
            for cat in categories
        ]
    })


@api_bp.route("/cellar-categories", methods=["GET"])
@api_token_required
def list_cellar_categories():
    """Liste toutes les catégories de caves."""
    categories = CellarCategory.query.order_by(
        CellarCategory.display_order, CellarCategory.name
    ).all()
    
    return jsonify({
        "categories": [
            {
                "id": cat.id,
                "name": cat.name,
                "description": cat.description,
            }
            for cat in categories
        ]
    })


# ============================================================================
# Consumption history endpoint
# ============================================================================


@api_bp.route("/consumptions", methods=["GET"])
@api_token_required
def list_consumptions():
    """Liste l'historique des consommations.
    
    Pour un sous-compte, retourne les consommations du compte parent.
    
    Query params:
        - limit: Nombre max de résultats (défaut: 50)
        - offset: Décalage pour pagination (défaut: 0)
    """
    user = g.api_user
    owner_id = user.owner_id
    
    limit = min(request.args.get("limit", 50, type=int), 200)
    offset = request.args.get("offset", 0, type=int)
    
    query = WineConsumption.query.filter_by(user_id=owner_id)
    total = query.count()
    
    consumptions = query.order_by(
        WineConsumption.consumed_at.desc()
    ).offset(offset).limit(limit).all()
    
    return jsonify({
        "consumptions": [_consumption_to_dict(c) for c in consumptions],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


# ============================================================================
# Collection overview endpoint
# ============================================================================


@api_bp.route("/collection", methods=["GET"])
@api_token_required
def get_collection():
    """Retourne une vue d'ensemble de la collection par cave.
    
    Pour un sous-compte, retourne la collection du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    # Charger les caves sans eager loading sur wines (lazy="dynamic")
    cellars = Cellar.query.options(
        selectinload(Cellar.category),
    ).filter_by(user_id=owner_id).order_by(Cellar.name.asc()).all()
    
    # Charger tous les vins de l'utilisateur et les grouper par cave
    wines = Wine.query.options(
        selectinload(Wine.subcategory),
    ).filter_by(user_id=owner_id).all()
    
    wines_by_cellar: dict[int, list[Wine]] = defaultdict(list)
    for wine in wines:
        wines_by_cellar[wine.cellar_id].append(wine)
    
    collection = []
    for cellar in cellars:
        cellar_wines = wines_by_cellar.get(cellar.id, [])
        wines_in_stock = [w for w in cellar_wines if (w.quantity or 0) > 0]
        total_quantity = sum(w.quantity or 0 for w in wines_in_stock)
        
        subcategories = set()
        regions = set()
        years = set()
        
        for wine in wines_in_stock:
            if wine.subcategory:
                subcategories.add(wine.subcategory.name)
            extras = wine.extra_attributes or {}
            if extras.get("region"):
                regions.add(extras["region"])
            if extras.get("year"):
                try:
                    years.add(int(extras["year"]))
                except (TypeError, ValueError):
                    pass
        
        collection.append({
            "cellar": _cellar_to_dict(cellar),
            "total_bottles": total_quantity,
            "wine_count": len(wines_in_stock),
            "subcategories": sorted(subcategories),
            "regions": sorted(regions),
            "vintage_range": [min(years), max(years)] if years else None,
        })
    
    return jsonify({
        "collection": collection,
        "total_cellars": len(cellars),
        "total_bottles": sum(c["total_bottles"] for c in collection),
    })
