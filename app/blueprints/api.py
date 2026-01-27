"""Blueprint API REST pour l'accès programmatique aux données."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request, g, render_template_string, current_app

from sqlalchemy.orm import selectinload

from models import (
    AlcoholCategory,
    AlcoholSubcategory,
    Cellar,
    CellarCategory,
    Wine,
    WineConsumption,
    WineInsight,
    Webhook,
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


@api_bp.route("/cellars", methods=["POST"])
@api_token_required
def create_cellar():
    """Crée une nouvelle cave.
    
    Pour un sous-compte, la cave est créée pour le compte parent.
    
    Body JSON:
        - name: Nom de la cave (requis)
        - category_id: ID de la catégorie de cave (requis)
        - floor_count: Nombre d'étages (requis)
        - bottles_per_floor: Capacité par étage (requis)
    """
    user = g.api_user
    owner_id = user.owner_id
    owner_account = user.owner_account
    data = request.get_json() or {}
    
    # Validation
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Le nom est requis"}), 400
    
    category_id = data.get("category_id")
    if not category_id:
        return jsonify({"error": "category_id est requis"}), 400
    
    category = CellarCategory.query.get(category_id)
    if not category:
        return jsonify({"error": "Catégorie de cave non trouvée"}), 404
    
    floor_count = data.get("floor_count")
    if not floor_count or floor_count < 1:
        return jsonify({"error": "floor_count doit être >= 1"}), 400
    
    bottles_per_floor = data.get("bottles_per_floor")
    if not bottles_per_floor or bottles_per_floor < 1:
        return jsonify({"error": "bottles_per_floor doit être >= 1"}), 400
    
    cellar = Cellar(
        name=name,
        category_id=category_id,
        floor_count=floor_count,
        bottles_per_floor=bottles_per_floor,
        user_id=owner_id,
    )
    
    db.session.add(cellar)
    db.session.commit()
    
    return jsonify(_cellar_to_dict(cellar)), 201


@api_bp.route("/cellars/<int:cellar_id>", methods=["PUT", "PATCH"])
@api_token_required
def update_cellar(cellar_id: int):
    """Met à jour une cave existante.
    
    Pour un sous-compte, permet de modifier les caves du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    data = request.get_json() or {}
    
    cellar = Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first()
    if not cellar:
        return jsonify({"error": "Cave non trouvée"}), 404
    
    if "name" in data:
        cellar.name = (data["name"] or "").strip() or cellar.name
    
    if "category_id" in data:
        category = CellarCategory.query.get(data["category_id"])
        if not category:
            return jsonify({"error": "Catégorie de cave non trouvée"}), 404
        cellar.category_id = data["category_id"]
    
    if "floor_count" in data:
        if data["floor_count"] < 1:
            return jsonify({"error": "floor_count doit être >= 1"}), 400
        cellar.floor_count = data["floor_count"]
    
    if "bottles_per_floor" in data:
        if data["bottles_per_floor"] < 1:
            return jsonify({"error": "bottles_per_floor doit être >= 1"}), 400
        cellar.bottles_per_floor = data["bottles_per_floor"]
    
    db.session.commit()
    
    return jsonify(_cellar_to_dict(cellar))


@api_bp.route("/cellars/<int:cellar_id>", methods=["DELETE"])
@api_token_required
def delete_cellar(cellar_id: int):
    """Supprime une cave.
    
    Pour un sous-compte, permet de supprimer les caves du compte parent.
    Attention : supprime également toutes les bouteilles de la cave.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    cellar = Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first()
    if not cellar:
        return jsonify({"error": "Cave non trouvée"}), 404
    
    # Vérifier s'il y a des bouteilles
    wine_count = Wine.query.filter_by(cellar_id=cellar_id, user_id=owner_id).count()
    
    db.session.delete(cellar)
    db.session.commit()
    
    return jsonify({
        "message": "Cave supprimée",
        "wines_deleted": wine_count,
    }), 200


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


# ============================================================================
# Webhooks endpoints
# ============================================================================


def _webhook_to_dict(webhook: Webhook) -> dict[str, Any]:
    """Convertit un objet Webhook en dictionnaire JSON-serializable."""
    return {
        "id": webhook.id,
        "name": webhook.name,
        "url": webhook.url,
        "events": webhook.events,
        "is_active": webhook.is_active,
        "secret": webhook.secret[:8] + "..." if webhook.secret else None,
        "created_at": webhook.created_at.isoformat() if webhook.created_at else None,
        "last_triggered_at": webhook.last_triggered_at.isoformat() if webhook.last_triggered_at else None,
    }


@api_bp.route("/webhooks", methods=["GET"])
@api_token_required
def list_webhooks():
    """Liste tous les webhooks de l'utilisateur.
    
    Pour un sous-compte, retourne les webhooks du compte parent.
    """
    user = g.api_user
    owner_id = user.owner_id
    
    webhooks = Webhook.query.filter_by(user_id=owner_id).order_by(Webhook.name.asc()).all()
    
    return jsonify({
        "webhooks": [_webhook_to_dict(w) for w in webhooks],
        "total": len(webhooks),
        "available_events": Webhook.EVENTS,
    })


@api_bp.route("/webhooks", methods=["POST"])
@api_token_required
def create_webhook():
    """Crée un nouveau webhook.
    
    Pour un sous-compte, le webhook est créé pour le compte parent.
    
    Body JSON:
        - name: Nom du webhook (requis)
        - url: URL de destination (requis)
        - events: Liste des événements à écouter (requis)
        - secret: Secret pour la signature HMAC (optionnel, généré si absent)
    """
    import secrets
    
    user = g.api_user
    owner_id = user.owner_id
    data = request.get_json() or {}
    
    # Validation
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Le nom est requis"}), 400
    
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "L'URL est requise"}), 400
    
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "L'URL doit commencer par http:// ou https://"}), 400
    
    events = data.get("events", [])
    if not events:
        return jsonify({"error": "Au moins un événement est requis"}), 400
    
    invalid_events = [e for e in events if e not in Webhook.EVENTS]
    if invalid_events:
        return jsonify({
            "error": f"Événements invalides: {', '.join(invalid_events)}",
            "available_events": Webhook.EVENTS,
        }), 400
    
    # Générer un secret si non fourni
    secret = data.get("secret") or secrets.token_urlsafe(32)
    
    webhook = Webhook(
        name=name,
        url=url,
        events=events,
        secret=secret,
        user_id=owner_id,
    )
    
    db.session.add(webhook)
    db.session.commit()
    
    # Retourner le secret complet à la création
    result = _webhook_to_dict(webhook)
    result["secret"] = webhook.secret  # Secret complet
    
    return jsonify(result), 201


@api_bp.route("/webhooks/<int:webhook_id>", methods=["GET"])
@api_token_required
def get_webhook(webhook_id: int):
    """Récupère les détails d'un webhook."""
    user = g.api_user
    owner_id = user.owner_id
    
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=owner_id).first()
    if not webhook:
        return jsonify({"error": "Webhook non trouvé"}), 404
    
    return jsonify(_webhook_to_dict(webhook))


@api_bp.route("/webhooks/<int:webhook_id>", methods=["PUT", "PATCH"])
@api_token_required
def update_webhook(webhook_id: int):
    """Met à jour un webhook existant."""
    user = g.api_user
    owner_id = user.owner_id
    data = request.get_json() or {}
    
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=owner_id).first()
    if not webhook:
        return jsonify({"error": "Webhook non trouvé"}), 404
    
    if "name" in data:
        webhook.name = (data["name"] or "").strip() or webhook.name
    
    if "url" in data:
        url = (data["url"] or "").strip()
        if url and not url.startswith(("http://", "https://")):
            return jsonify({"error": "L'URL doit commencer par http:// ou https://"}), 400
        webhook.url = url or webhook.url
    
    if "events" in data:
        events = data["events"]
        if events:
            invalid_events = [e for e in events if e not in Webhook.EVENTS]
            if invalid_events:
                return jsonify({
                    "error": f"Événements invalides: {', '.join(invalid_events)}",
                    "available_events": Webhook.EVENTS,
                }), 400
            webhook.events = events
    
    if "is_active" in data:
        webhook.is_active = bool(data["is_active"])
    
    db.session.commit()
    
    return jsonify(_webhook_to_dict(webhook))


@api_bp.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
@api_token_required
def delete_webhook(webhook_id: int):
    """Supprime un webhook."""
    user = g.api_user
    owner_id = user.owner_id
    
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=owner_id).first()
    if not webhook:
        return jsonify({"error": "Webhook non trouvé"}), 404
    
    db.session.delete(webhook)
    db.session.commit()
    
    return jsonify({"message": "Webhook supprimé"}), 200


@api_bp.route("/webhooks/<int:webhook_id>/test", methods=["POST"])
@api_token_required
def test_webhook(webhook_id: int):
    """Envoie un événement de test au webhook."""
    import hashlib
    import hmac
    import json
    import requests
    
    user = g.api_user
    owner_id = user.owner_id
    
    webhook = Webhook.query.filter_by(id=webhook_id, user_id=owner_id).first()
    if not webhook:
        return jsonify({"error": "Webhook non trouvé"}), 404
    
    # Préparer le payload de test
    payload = {
        "event": "test",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "message": "Ceci est un événement de test",
            "webhook_id": webhook.id,
            "webhook_name": webhook.name,
        },
    }
    
    payload_json = json.dumps(payload, separators=(",", ":"))
    
    # Calculer la signature HMAC
    signature = hmac.new(
        webhook.secret.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": "test",
    }
    
    try:
        response = requests.post(
            webhook.url,
            data=payload_json,
            headers=headers,
            timeout=10,
        )
        
        webhook.last_triggered_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "success": response.ok,
            "status_code": response.status_code,
            "response_body": response.text[:500] if response.text else None,
        })
    except requests.RequestException as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 502


# ============================================================================
# Push Notifications endpoints
# ============================================================================


@api_bp.route("/push/vapid-key", methods=["GET"])
def get_vapid_key():
    """Retourne la clé publique VAPID pour les notifications push."""
    import os
    vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY", "")
    
    if not vapid_public_key:
        return jsonify({"error": "Notifications push non configurées"}), 503
    
    return jsonify({"publicKey": vapid_public_key})


@api_bp.route("/push/subscribe", methods=["POST"])
def subscribe_push():
    """Enregistre un abonnement aux notifications push.
    
    Body JSON (format Web Push standard):
        - endpoint: URL de l'endpoint push
        - keys:
            - p256dh: Clé publique
            - auth: Secret d'authentification
        - expirationTime: (optionnel) Temps d'expiration
    """
    from flask_login import current_user
    from models import PushSubscription
    
    try:
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentification requise"}), 401
        
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Corps de requête JSON requis"}), 400
        
        endpoint = data.get("endpoint")
        keys = data.get("keys", {})
        
        # Log pour debug
        current_app.logger.info(f"[Push] Subscription reçue pour user {current_user.id}: endpoint={endpoint[:50] if endpoint else 'None'}...")
        current_app.logger.info(f"[Push] Keys reçues: p256dh={bool(keys.get('p256dh'))}, auth={bool(keys.get('auth'))}")
        
        if not endpoint:
            return jsonify({"error": "Endpoint manquant dans la subscription"}), 400
        
        if not keys.get("p256dh"):
            return jsonify({"error": "Clé p256dh manquante dans la subscription"}), 400
            
        if not keys.get("auth"):
            return jsonify({"error": "Clé auth manquante dans la subscription"}), 400
        
        # Vérifier si l'abonnement existe déjà
        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        
        if existing:
            # Mettre à jour si c'est le même utilisateur
            if existing.user_id == current_user.owner_id:
                existing.p256dh_key = keys["p256dh"]
                existing.auth_key = keys["auth"]
                existing.is_active = True
                existing.user_agent = request.headers.get("User-Agent")
                db.session.commit()
                current_app.logger.info(f"[Push] Abonnement mis à jour: id={existing.id}")
                return jsonify({"message": "Abonnement mis à jour", "id": existing.id})
            else:
                # Endpoint déjà utilisé par un autre utilisateur - le réassigner
                current_app.logger.warning(f"[Push] Endpoint réassigné de user {existing.user_id} à user {current_user.owner_id}")
                existing.user_id = current_user.owner_id
                existing.p256dh_key = keys["p256dh"]
                existing.auth_key = keys["auth"]
                existing.is_active = True
                existing.user_agent = request.headers.get("User-Agent")
                db.session.commit()
                return jsonify({"message": "Abonnement réassigné", "id": existing.id})
        
        # Créer un nouvel abonnement
        subscription = PushSubscription(
            user_id=current_user.owner_id,
            endpoint=endpoint,
            p256dh_key=keys["p256dh"],
            auth_key=keys["auth"],
            user_agent=request.headers.get("User-Agent"),
        )
        
        db.session.add(subscription)
        db.session.commit()
        
        current_app.logger.info(f"[Push] Nouvel abonnement créé: id={subscription.id} pour user {current_user.owner_id}")
        
        return jsonify({"message": "Abonnement créé", "id": subscription.id}), 201
        
    except Exception as e:
        current_app.logger.error(f"[Push] Erreur lors de l'abonnement: {str(e)}")
        import traceback
        current_app.logger.error(f"[Push] Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({"error": f"Erreur serveur: {str(e)}"}), 500


@api_bp.route("/push/unsubscribe", methods=["POST"])
def unsubscribe_push():
    """Supprime un abonnement aux notifications push.
    
    Body JSON:
        - endpoint: URL de l'endpoint à désabonner
    """
    from flask_login import current_user
    from models import PushSubscription
    
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentification requise"}), 401
    
    data = request.get_json() or {}
    endpoint = data.get("endpoint")
    
    if not endpoint:
        return jsonify({"error": "Endpoint requis"}), 400
    
    subscription = PushSubscription.query.filter_by(
        endpoint=endpoint,
        user_id=current_user.owner_id
    ).first()
    
    if subscription:
        db.session.delete(subscription)
        db.session.commit()
        return jsonify({"message": "Désabonnement réussi"})
    
    return jsonify({"message": "Abonnement non trouvé"}), 404


@api_bp.route("/push/test", methods=["POST"])
def test_push():
    """Envoie une notification push de test à l'utilisateur connecté."""
    from flask_login import current_user
    from models import PushSubscription
    import os
    
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentification requise"}), 401
    
    # Récupérer les abonnements de l'utilisateur
    subscriptions = PushSubscription.query.filter_by(
        user_id=current_user.owner_id,
        is_active=True
    ).all()
    
    if not subscriptions:
        return jsonify({"error": "Aucun abonnement actif"}), 404
    
    # Vérifier la configuration VAPID
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_claims = {
        "sub": os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com")
    }
    
    if not vapid_private_key:
        return jsonify({"error": "Notifications push non configurées sur le serveur"}), 503
    
    # Préparer le payload
    payload = {
        "title": "🍷 Cave à Vin",
        "body": "Les notifications sont activées ! Vous recevrez des alertes pour vos bouteilles.",
        "icon": "/static/icons/icon-192x192.png",
        "badge": "/static/icons/icon-72x72.png",
        "url": "/",
        "tag": "test-notification",
    }
    
    # Envoyer les notifications
    sent = 0
    errors = []
    
    try:
        from pywebpush import webpush, WebPushException
        
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info=sub.to_dict(),
                    data=__import__("json").dumps(payload),
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                )
                sub.last_used_at = datetime.utcnow()
                sent += 1
            except WebPushException as e:
                errors.append(str(e))
                # Si l'abonnement est invalide, le désactiver
                if e.response and e.response.status_code in (404, 410):
                    sub.is_active = False
        
        db.session.commit()
        
    except ImportError:
        return jsonify({
            "error": "Module pywebpush non installé",
            "message": "Installez pywebpush pour activer les notifications push"
        }), 503
    
    return jsonify({
        "message": f"Notification envoyée à {sent} appareil(s)",
        "sent": sent,
        "errors": errors if errors else None,
    })


@api_bp.route("/ping", methods=["GET", "HEAD"])
def ping():
    """Endpoint de vérification de connectivité."""
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ============================================================================
# OpenAPI / Swagger documentation
# ============================================================================


OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Cave à Vin API",
        "description": "API REST pour la gestion de cave à vin. Permet de gérer les bouteilles, caves, consommations et plus encore.",
        "version": "1.0.0",
        "contact": {
            "name": "Support API",
        },
    },
    "servers": [
        {
            "url": "/api",
            "description": "Serveur principal",
        }
    ],
    "security": [
        {"ApiTokenAuth": []},
    ],
    "components": {
        "securitySchemes": {
            "ApiTokenAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "Token API au format: Bearer <token>",
            },
        },
        "schemas": {
            "Wine": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "ID unique de la bouteille"},
                    "name": {"type": "string", "description": "Nom de la bouteille"},
                    "barcode": {"type": "string", "nullable": True, "description": "Code-barres"},
                    "quantity": {"type": "integer", "description": "Quantité en stock"},
                    "image_url": {"type": "string", "nullable": True, "description": "URL de l'image"},
                    "cellar_id": {"type": "integer", "description": "ID de la cave"},
                    "cellar_name": {"type": "string", "nullable": True, "description": "Nom de la cave"},
                    "subcategory_id": {"type": "integer", "nullable": True, "description": "ID de la sous-catégorie"},
                    "subcategory_name": {"type": "string", "nullable": True, "description": "Nom de la sous-catégorie"},
                    "category_name": {"type": "string", "nullable": True, "description": "Nom de la catégorie"},
                    "extra_attributes": {"type": "object", "description": "Attributs supplémentaires (année, région, cépage, etc.)"},
                    "created_at": {"type": "string", "format": "date-time", "description": "Date de création"},
                    "updated_at": {"type": "string", "format": "date-time", "description": "Date de mise à jour"},
                },
            },
            "WineCreate": {
                "type": "object",
                "required": ["name", "cellar_id"],
                "properties": {
                    "name": {"type": "string", "description": "Nom de la bouteille"},
                    "cellar_id": {"type": "integer", "description": "ID de la cave"},
                    "quantity": {"type": "integer", "default": 1, "description": "Quantité"},
                    "barcode": {"type": "string", "description": "Code-barres"},
                    "subcategory_id": {"type": "integer", "description": "ID de la sous-catégorie"},
                    "extra_attributes": {"type": "object", "description": "Attributs supplémentaires"},
                },
            },
            "Cellar": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "ID unique de la cave"},
                    "name": {"type": "string", "description": "Nom de la cave"},
                    "category_id": {"type": "integer", "description": "ID de la catégorie"},
                    "category_name": {"type": "string", "nullable": True, "description": "Nom de la catégorie"},
                    "floor_count": {"type": "integer", "description": "Nombre d'étages"},
                    "capacity": {"type": "integer", "description": "Capacité totale"},
                    "floor_capacities": {"type": "object", "description": "Capacités par étage"},
                },
            },
            "CellarCreate": {
                "type": "object",
                "required": ["name", "category_id", "floor_count", "bottles_per_floor"],
                "properties": {
                    "name": {"type": "string", "description": "Nom de la cave"},
                    "category_id": {"type": "integer", "description": "ID de la catégorie de cave"},
                    "floor_count": {"type": "integer", "minimum": 1, "description": "Nombre d'étages"},
                    "bottles_per_floor": {"type": "integer", "minimum": 1, "description": "Capacité par étage"},
                },
            },
            "Consumption": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "wine_id": {"type": "integer"},
                    "consumed_at": {"type": "string", "format": "date-time"},
                    "quantity": {"type": "integer"},
                    "comment": {"type": "string", "nullable": True},
                    "snapshot_name": {"type": "string"},
                    "snapshot_year": {"type": "string", "nullable": True},
                    "snapshot_region": {"type": "string", "nullable": True},
                    "snapshot_grape": {"type": "string", "nullable": True},
                    "snapshot_cellar": {"type": "string", "nullable": True},
                },
            },
            "Webhook": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "url": {"type": "string", "format": "uri"},
                    "events": {"type": "array", "items": {"type": "string"}},
                    "is_active": {"type": "boolean"},
                    "secret": {"type": "string", "description": "Secret tronqué (complet à la création)"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "last_triggered_at": {"type": "string", "format": "date-time", "nullable": True},
                },
            },
            "WebhookCreate": {
                "type": "object",
                "required": ["name", "url", "events"],
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": "string", "format": "uri"},
                    "events": {
                        "type": "array",
                        "items": {"type": "string", "enum": Webhook.EVENTS},
                        "description": "Événements à écouter",
                    },
                    "secret": {"type": "string", "description": "Secret HMAC (généré si absent)"},
                },
            },
            "Category": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string", "nullable": True},
                    "subcategories": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Subcategory"},
                    },
                },
            },
            "Subcategory": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string", "nullable": True},
                    "badge_bg_color": {"type": "string"},
                    "badge_text_color": {"type": "string"},
                },
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string", "description": "Message d'erreur"},
                },
            },
            "Statistics": {
                "type": "object",
                "properties": {
                    "total_bottles": {"type": "integer"},
                    "total_references": {"type": "integer"},
                    "total_consumed": {"type": "integer"},
                    "category_distribution": {"type": "object"},
                    "subcategory_distribution": {"type": "object"},
                    "cellar_distribution": {"type": "object"},
                },
            },
        },
    },
    "paths": {
        "/wines": {
            "get": {
                "summary": "Liste des bouteilles",
                "description": "Retourne la liste paginée des bouteilles de l'utilisateur.",
                "tags": ["Bouteilles"],
                "parameters": [
                    {"name": "cellar_id", "in": "query", "schema": {"type": "integer"}, "description": "Filtrer par cave"},
                    {"name": "subcategory_id", "in": "query", "schema": {"type": "integer"}, "description": "Filtrer par sous-catégorie"},
                    {"name": "in_stock", "in": "query", "schema": {"type": "boolean"}, "description": "Uniquement en stock"},
                    {"name": "include_insights", "in": "query", "schema": {"type": "boolean"}, "description": "Inclure les insights"},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100, "maximum": 500}},
                    {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}},
                ],
                "responses": {
                    "200": {
                        "description": "Liste des bouteilles",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "wines": {"type": "array", "items": {"$ref": "#/components/schemas/Wine"}},
                                        "total": {"type": "integer"},
                                        "limit": {"type": "integer"},
                                        "offset": {"type": "integer"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "post": {
                "summary": "Créer une bouteille",
                "tags": ["Bouteilles"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/WineCreate"},
                        },
                    },
                },
                "responses": {
                    "201": {
                        "description": "Bouteille créée",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Wine"}}},
                    },
                    "400": {"description": "Données invalides", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                },
            },
        },
        "/wines/{wine_id}": {
            "get": {
                "summary": "Détails d'une bouteille",
                "tags": ["Bouteilles"],
                "parameters": [{"name": "wine_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {"description": "Détails de la bouteille", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Wine"}}}},
                    "404": {"description": "Bouteille non trouvée"},
                },
            },
            "put": {
                "summary": "Modifier une bouteille",
                "tags": ["Bouteilles"],
                "parameters": [{"name": "wine_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/WineCreate"}}}},
                "responses": {
                    "200": {"description": "Bouteille modifiée", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Wine"}}}},
                    "404": {"description": "Bouteille non trouvée"},
                },
            },
            "delete": {
                "summary": "Supprimer une bouteille",
                "tags": ["Bouteilles"],
                "parameters": [{"name": "wine_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {"description": "Bouteille supprimée"},
                    "404": {"description": "Bouteille non trouvée"},
                },
            },
        },
        "/wines/{wine_id}/consume": {
            "post": {
                "summary": "Consommer une bouteille",
                "tags": ["Bouteilles"],
                "parameters": [{"name": "wine_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "quantity": {"type": "integer", "default": 1},
                                    "comment": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "responses": {
                    "200": {"description": "Consommation enregistrée"},
                    "400": {"description": "Stock insuffisant"},
                    "404": {"description": "Bouteille non trouvée"},
                },
            },
        },
        "/cellars": {
            "get": {
                "summary": "Liste des caves",
                "tags": ["Caves"],
                "responses": {
                    "200": {
                        "description": "Liste des caves",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "cellars": {"type": "array", "items": {"$ref": "#/components/schemas/Cellar"}},
                                        "total": {"type": "integer"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "post": {
                "summary": "Créer une cave",
                "tags": ["Caves"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CellarCreate"}}},
                },
                "responses": {
                    "201": {"description": "Cave créée", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Cellar"}}}},
                    "400": {"description": "Données invalides"},
                },
            },
        },
        "/cellars/{cellar_id}": {
            "get": {
                "summary": "Détails d'une cave",
                "tags": ["Caves"],
                "parameters": [{"name": "cellar_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {"description": "Détails de la cave avec ses bouteilles"},
                    "404": {"description": "Cave non trouvée"},
                },
            },
            "put": {
                "summary": "Modifier une cave",
                "tags": ["Caves"],
                "parameters": [{"name": "cellar_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CellarCreate"}}}},
                "responses": {
                    "200": {"description": "Cave modifiée"},
                    "404": {"description": "Cave non trouvée"},
                },
            },
            "delete": {
                "summary": "Supprimer une cave",
                "description": "Supprime la cave et toutes ses bouteilles.",
                "tags": ["Caves"],
                "parameters": [{"name": "cellar_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {"description": "Cave supprimée"},
                    "404": {"description": "Cave non trouvée"},
                },
            },
        },
        "/search": {
            "get": {
                "summary": "Recherche multi-critères",
                "tags": ["Recherche"],
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Recherche textuelle"},
                    {"name": "subcategory_id", "in": "query", "schema": {"type": "integer"}},
                    {"name": "food_pairing", "in": "query", "schema": {"type": "string"}, "description": "Recherche dans les accords mets-vins"},
                    {"name": "in_stock", "in": "query", "schema": {"type": "boolean"}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50, "maximum": 200}},
                ],
                "responses": {"200": {"description": "Résultats de recherche"}},
            },
        },
        "/statistics": {
            "get": {
                "summary": "Statistiques de la cave",
                "tags": ["Statistiques"],
                "responses": {
                    "200": {
                        "description": "Statistiques",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Statistics"}}},
                    },
                },
            },
        },
        "/categories": {
            "get": {
                "summary": "Liste des catégories d'alcool",
                "tags": ["Catégories"],
                "responses": {
                    "200": {
                        "description": "Liste des catégories avec sous-catégories",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "categories": {"type": "array", "items": {"$ref": "#/components/schemas/Category"}},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "/cellar-categories": {
            "get": {
                "summary": "Liste des catégories de caves",
                "tags": ["Catégories"],
                "responses": {"200": {"description": "Liste des catégories de caves"}},
            },
        },
        "/consumptions": {
            "get": {
                "summary": "Historique des consommations",
                "tags": ["Consommations"],
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50, "maximum": 200}},
                    {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}},
                ],
                "responses": {
                    "200": {
                        "description": "Liste des consommations",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "consumptions": {"type": "array", "items": {"$ref": "#/components/schemas/Consumption"}},
                                        "total": {"type": "integer"},
                                        "limit": {"type": "integer"},
                                        "offset": {"type": "integer"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "/collection": {
            "get": {
                "summary": "Vue d'ensemble de la collection",
                "tags": ["Collection"],
                "responses": {"200": {"description": "Collection par cave"}},
            },
        },
        "/webhooks": {
            "get": {
                "summary": "Liste des webhooks",
                "tags": ["Webhooks"],
                "responses": {
                    "200": {
                        "description": "Liste des webhooks",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "webhooks": {"type": "array", "items": {"$ref": "#/components/schemas/Webhook"}},
                                        "total": {"type": "integer"},
                                        "available_events": {"type": "array", "items": {"type": "string"}},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "post": {
                "summary": "Créer un webhook",
                "tags": ["Webhooks"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/WebhookCreate"}}},
                },
                "responses": {
                    "201": {"description": "Webhook créé (secret complet retourné)"},
                    "400": {"description": "Données invalides"},
                },
            },
        },
        "/webhooks/{webhook_id}": {
            "get": {
                "summary": "Détails d'un webhook",
                "tags": ["Webhooks"],
                "parameters": [{"name": "webhook_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Détails du webhook"}, "404": {"description": "Webhook non trouvé"}},
            },
            "put": {
                "summary": "Modifier un webhook",
                "tags": ["Webhooks"],
                "parameters": [{"name": "webhook_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Webhook modifié"}, "404": {"description": "Webhook non trouvé"}},
            },
            "delete": {
                "summary": "Supprimer un webhook",
                "tags": ["Webhooks"],
                "parameters": [{"name": "webhook_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Webhook supprimé"}, "404": {"description": "Webhook non trouvé"}},
            },
        },
        "/webhooks/{webhook_id}/test": {
            "post": {
                "summary": "Tester un webhook",
                "description": "Envoie un événement de test au webhook.",
                "tags": ["Webhooks"],
                "parameters": [{"name": "webhook_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {"description": "Résultat du test"},
                    "404": {"description": "Webhook non trouvé"},
                    "502": {"description": "Erreur de connexion au webhook"},
                },
            },
        },
    },
    "tags": [
        {"name": "Bouteilles", "description": "Gestion des bouteilles"},
        {"name": "Caves", "description": "Gestion des caves"},
        {"name": "Recherche", "description": "Recherche multi-critères"},
        {"name": "Statistiques", "description": "Statistiques de la cave"},
        {"name": "Catégories", "description": "Catégories d'alcool et de caves"},
        {"name": "Consommations", "description": "Historique des consommations"},
        {"name": "Collection", "description": "Vue d'ensemble de la collection"},
        {"name": "Webhooks", "description": "Gestion des webhooks pour notifications externes"},
    ],
}


SWAGGER_UI_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cave à Vin API - Documentation</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <style>
        :root {
            --primary-color: #722f37;
            --primary-hover: #5a252c;
            --bg-light: #f8f9fa;
        }
        
        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }
        
        .swagger-ui .topbar { display: none; }
        .swagger-ui .info .title { font-size: 2rem; }
        
        /* Header personnalisé */
        .api-header {
            background: linear-gradient(135deg, var(--primary-color) 0%, #4a1f24 100%);
            color: white;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .api-header h1 {
            margin: 0;
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .api-header h1 i {
            font-size: 1.8rem;
        }
        
        .header-links {
            display: flex;
            gap: 1rem;
            align-items: center;
        }
        
        .header-links a {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            transition: background 0.2s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .header-links a:hover {
            background: rgba(255,255,255,0.1);
        }
        
        /* Panneau d'authentification */
        .auth-panel {
            background: var(--bg-light);
            border-bottom: 1px solid #dee2e6;
            padding: 1rem 2rem;
        }
        
        .auth-container {
            max-width: 800px;
            margin: 0 auto;
        }
        
        .auth-title {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            color: #333;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .auth-form {
            display: flex;
            gap: 0.75rem;
            align-items: stretch;
        }
        
        .auth-input-group {
            flex: 1;
            position: relative;
        }
        
        .auth-input {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            font-size: 0.95rem;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            transition: border-color 0.2s, box-shadow 0.2s;
            box-sizing: border-box;
        }
        
        .auth-input:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(114, 47, 55, 0.1);
        }
        
        .auth-input::placeholder {
            color: #adb5bd;
        }
        
        .auth-btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 6px;
            font-size: 0.95rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            white-space: nowrap;
        }
        
        .auth-btn-primary {
            background: var(--primary-color);
            color: white;
        }
        
        .auth-btn-primary:hover {
            background: var(--primary-hover);
        }
        
        .auth-btn-secondary {
            background: #6c757d;
            color: white;
        }
        
        .auth-btn-secondary:hover {
            background: #5a6268;
        }
        
        .auth-btn-success {
            background: #28a745;
            color: white;
        }
        
        .auth-status {
            margin-top: 0.75rem;
            padding: 0.75rem 1rem;
            border-radius: 6px;
            font-size: 0.9rem;
            display: none;
        }
        
        .auth-status.success {
            display: block;
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .auth-status.error {
            display: block;
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .auth-status.info {
            display: block;
            background: #cce5ff;
            color: #004085;
            border: 1px solid #b8daff;
        }
        
        .auth-help {
            margin-top: 0.75rem;
            font-size: 0.85rem;
            color: #6c757d;
        }
        
        .auth-help a {
            color: var(--primary-color);
            text-decoration: none;
        }
        
        .auth-help a:hover {
            text-decoration: underline;
        }
        
        /* Swagger UI customizations */
        .swagger-ui .info {
            margin: 30px 0;
        }
        
        .swagger-ui .scheme-container {
            background: var(--bg-light);
            padding: 15px;
        }
        
        .swagger-ui .btn.authorize {
            background: var(--primary-color);
            border-color: var(--primary-color);
        }
        
        .swagger-ui .btn.authorize:hover {
            background: var(--primary-hover);
        }
        
        .swagger-ui .btn.authorize svg {
            fill: white;
        }
        
        .swagger-ui .opblock.opblock-get .opblock-summary-method {
            background: #61affe;
        }
        
        .swagger-ui .opblock.opblock-post .opblock-summary-method {
            background: #49cc90;
        }
        
        .swagger-ui .opblock.opblock-put .opblock-summary-method {
            background: #fca130;
        }
        
        .swagger-ui .opblock.opblock-delete .opblock-summary-method {
            background: #f93e3e;
        }
        
        .swagger-ui .opblock.opblock-patch .opblock-summary-method {
            background: #50e3c2;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .api-header {
                flex-direction: column;
                gap: 1rem;
                text-align: center;
            }
            
            .auth-form {
                flex-direction: column;
            }
            
            .auth-btn {
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <!-- Header -->
    <div class="api-header">
        <h1><i class="bi bi-code-slash"></i> Cave à Vin API</h1>
        <div class="header-links">
            <a href="/"><i class="bi bi-house"></i> Accueil</a>
            <a href="/api-tokens"><i class="bi bi-key"></i> Mes tokens</a>
        </div>
    </div>
    
    <!-- Panneau d'authentification -->
    <div class="auth-panel">
        <div class="auth-container">
            <div class="auth-title">
                <i class="bi bi-shield-lock"></i> Authentification API
            </div>
            <div class="auth-form">
                <div class="auth-input-group">
                    <input type="text"
                           id="api-token"
                           class="auth-input"
                           placeholder="Collez votre token API ici (ex: cvt_abc123...)"
                           autocomplete="off">
                </div>
                <button type="button" class="auth-btn auth-btn-primary" onclick="applyToken()">
                    <i class="bi bi-unlock"></i> Authentifier
                </button>
                <button type="button" class="auth-btn auth-btn-secondary" onclick="clearToken()">
                    <i class="bi bi-x-circle"></i> Effacer
                </button>
            </div>
            <div id="auth-status" class="auth-status"></div>
            <div class="auth-help">
                <i class="bi bi-info-circle"></i>
                Vous n'avez pas de token ? <a href="/api-tokens/create">Créez-en un ici</a>.
                Le token sera automatiquement ajouté à toutes vos requêtes.
            </div>
        </div>
    </div>
    
    <!-- Swagger UI -->
    <div id="swagger-ui"></div>
    
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script>
        let swaggerUI = null;
        let currentToken = localStorage.getItem('api_token') || '';
        
        // Initialiser Swagger UI
        window.onload = function() {
            initSwaggerUI();
            
            // Restaurer le token sauvegardé
            if (currentToken) {
                document.getElementById('api-token').value = currentToken;
                showStatus('Token restauré depuis la session précédente', 'info');
            }
        };
        
        function initSwaggerUI() {
            swaggerUI = SwaggerUIBundle({
                url: "{{ spec_url }}",
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "BaseLayout",
                deepLinking: true,
                showExtensions: true,
                showCommonExtensions: true,
                persistAuthorization: true,
                requestInterceptor: function(request) {
                    // Ajouter le token à chaque requête si présent
                    if (currentToken) {
                        request.headers['Authorization'] = 'Bearer ' + currentToken;
                    }
                    return request;
                },
                onComplete: function() {
                    // Si un token est présent, l'appliquer à Swagger UI
                    if (currentToken) {
                        applyTokenToSwagger(currentToken);
                    }
                }
            });
        }
        
        function applyToken() {
            const tokenInput = document.getElementById('api-token');
            const token = tokenInput.value.trim();
            
            if (!token) {
                showStatus('Veuillez entrer un token API', 'error');
                return;
            }
            
            // Valider le format du token (optionnel)
            if (!token.startsWith('cvt_')) {
                showStatus('Le token doit commencer par "cvt_"', 'error');
                return;
            }
            
            currentToken = token;
            localStorage.setItem('api_token', token);
            
            // Appliquer à Swagger UI
            applyTokenToSwagger(token);
            
            showStatus('Token appliqué avec succès ! Vous pouvez maintenant tester les endpoints.', 'success');
        }
        
        function applyTokenToSwagger(token) {
            if (swaggerUI) {
                swaggerUI.preauthorizeApiKey('ApiTokenAuth', 'Bearer ' + token);
            }
        }
        
        function clearToken() {
            currentToken = '';
            localStorage.removeItem('api_token');
            document.getElementById('api-token').value = '';
            
            // Réinitialiser Swagger UI
            if (swaggerUI) {
                swaggerUI.preauthorizeApiKey('ApiTokenAuth', '');
            }
            
            showStatus('Token effacé', 'info');
        }
        
        function showStatus(message, type) {
            const statusEl = document.getElementById('auth-status');
            statusEl.textContent = message;
            statusEl.className = 'auth-status ' + type;
            
            // Masquer après 5 secondes pour les messages de succès/info
            if (type !== 'error') {
                setTimeout(() => {
                    statusEl.style.display = 'none';
                }, 5000);
            }
        }
        
        // Permettre l'authentification avec Entrée
        document.addEventListener('DOMContentLoaded', function() {
            const tokenInput = document.getElementById('api-token');
            if (tokenInput) {
                tokenInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        applyToken();
                    }
                });
            }
        });
    </script>
</body>
</html>
"""


@api_bp.route("/openapi.json", methods=["GET"])
def openapi_spec():
    """Retourne la spécification OpenAPI au format JSON."""
    return jsonify(OPENAPI_SPEC)


@api_bp.route("/docs", methods=["GET"])
def swagger_ui():
    """Affiche l'interface Swagger UI pour explorer l'API."""
    from flask import url_for
    # Utiliser le même schéma que la requête pour éviter les erreurs de mixed-content
    # Vérifier X-Forwarded-Proto pour les proxies (nginx, etc.)
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    spec_url = url_for("api.openapi_spec", _external=True, _scheme=scheme)
    return render_template_string(SWAGGER_UI_HTML, spec_url=spec_url)
