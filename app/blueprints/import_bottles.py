"""Blueprint pour l'import de bouteilles par analyse d'image."""

from __future__ import annotations

import base64
import logging
from io import BytesIO

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required
from PIL import Image

from app.models import (
    AlcoholCategory,
    AlcoholSubcategory,
    Cellar,
    Wine,
    db,
)
from app.field_config import iter_fields
from services.bottle_detection_service import BottleDetectionService, DetectedBottle
from services.push_notification_service import notify_wine_added
from tasks import schedule_wine_enrichment

logger = logging.getLogger(__name__)

import_bp = Blueprint("import", __name__, url_prefix="/import")


def _get_detection_service() -> BottleDetectionService:
    """Récupère ou crée le service de détection de bouteilles pour l'utilisateur courant."""
    return BottleDetectionService.for_user(current_user.id)


def _process_uploaded_image(file) -> tuple[str, str, str]:
    """
    Traite une image uploadée et la convertit en base64.
    
    Returns:
        Tuple (image_data_base64, mime_type, thumbnail_base64)
    """
    image = Image.open(file.stream)
    
    # Convertir en RGB si nécessaire
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        if image.mode in ("RGBA", "LA"):
            background.paste(image, mask=image.split()[-1])
        else:
            background.paste(image)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    
    # Redimensionner si trop grande (max 2048px pour l'API vision)
    max_dimension = 2048
    if image.width > max_dimension or image.height > max_dimension:
        ratio = min(max_dimension / image.width, max_dimension / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    
    # Convertir en base64 pour l'API
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    # Créer une miniature très petite pour l'aperçu (max 150px, qualité très réduite)
    thumbnail = image.copy()
    max_thumb = 150
    if thumbnail.width > max_thumb or thumbnail.height > max_thumb:
        ratio = min(max_thumb / thumbnail.width, max_thumb / thumbnail.height)
        thumb_size = (int(thumbnail.width * ratio), int(thumbnail.height * ratio))
        thumbnail = thumbnail.resize(thumb_size, Image.Resampling.LANCZOS)
    
    thumb_buffer = BytesIO()
    thumbnail.save(thumb_buffer, format="JPEG", quality=30, optimize=True)
    thumbnail_data = base64.b64encode(thumb_buffer.getvalue()).decode("utf-8")
    
    return image_data, "image/jpeg", thumbnail_data


def _find_existing_bottles(name: str, owner_id: int) -> list[dict]:
    """
    Recherche des bouteilles existantes avec un nom similaire.
    
    Returns:
        Liste de dictionnaires avec les informations des bouteilles existantes
    """
    if not name or len(name) < 3:
        return []
    
    name_lower = name.lower().strip()
    
    # Recherche des bouteilles avec un nom similaire
    existing_wines = Wine.query.filter(
        Wine.user_id == owner_id,
        Wine.quantity > 0,
        db.func.lower(Wine.name).contains(name_lower)
    ).limit(5).all()
    
    # Si pas de résultat, essayer avec les premiers mots du nom
    if not existing_wines and " " in name_lower:
        first_words = " ".join(name_lower.split()[:2])
        existing_wines = Wine.query.filter(
            Wine.user_id == owner_id,
            Wine.quantity > 0,
            db.func.lower(Wine.name).contains(first_words)
        ).limit(5).all()
    
    results = []
    for wine in existing_wines:
        extras = wine.extra_attributes or {}
        results.append({
            "id": wine.id,
            "name": wine.name,
            "quantity": wine.quantity,
            "cellar_id": wine.cellar_id,
            "cellar_name": wine.cellar.name if wine.cellar else None,
            "year": extras.get("year"),
            "region": extras.get("region"),
        })
    
    return results


def _get_available_categories() -> list[dict]:
    """
    Récupère les catégories et sous-catégories disponibles pour l'analyse.
    
    Returns:
        Liste de dictionnaires avec les catégories et leurs sous-catégories
    """
    categories = AlcoholCategory.query.order_by(
        AlcoholCategory.display_order, AlcoholCategory.name
    ).all()
    
    result = []
    for category in categories:
        subcategories = [sub.name for sub in category.subcategories]
        result.append({
            "name": category.name,
            "subcategories": subcategories,
        })
    
    return result


def _match_alcohol_type(alcohol_type: str | None) -> int | None:
    """
    Tente de faire correspondre un type d'alcool détecté avec une sous-catégorie existante.
    
    Returns:
        L'ID de la sous-catégorie correspondante ou None
    """
    if not alcohol_type:
        return None
    
    alcohol_type_lower = alcohol_type.lower().strip()
    
    # Recherche exacte d'abord
    subcategory = AlcoholSubcategory.query.filter(
        db.func.lower(AlcoholSubcategory.name) == alcohol_type_lower
    ).first()
    
    if subcategory:
        return subcategory.id
    
    # Recherche partielle
    subcategory = AlcoholSubcategory.query.filter(
        db.func.lower(AlcoholSubcategory.name).contains(alcohol_type_lower)
    ).first()
    
    if subcategory:
        return subcategory.id
    
    # Mappings courants
    type_mappings = {
        "vin rouge": ["rouge", "red wine"],
        "vin blanc": ["blanc", "white wine"],
        "vin rosé": ["rosé", "rose"],
        "champagne": ["champagne", "mousseux", "sparkling"],
        "rhum": ["rum", "rhum"],
        "whisky": ["whiskey", "scotch", "bourbon"],
        "vodka": ["vodka"],
        "gin": ["gin"],
        "cognac": ["cognac", "armagnac"],
        "bière": ["beer", "biere", "ale", "lager"],
    }
    
    for subcat_name, aliases in type_mappings.items():
        if alcohol_type_lower in aliases or any(alias in alcohol_type_lower for alias in aliases):
            subcategory = AlcoholSubcategory.query.filter(
                db.func.lower(AlcoholSubcategory.name).contains(subcat_name)
            ).first()
            if subcategory:
                return subcategory.id
    
    return None


@import_bp.route("/")
@login_required
def index():
    """Page principale d'import avec upload d'image."""
    owner_id = current_user.owner_id
    
    cellars = (
        Cellar.query.filter_by(user_id=owner_id)
        .order_by(Cellar.name.asc())
        .all()
    )
    
    if not cellars:
        flash("Créez d'abord une cave avant d'importer des bouteilles.")
        return redirect(url_for("cellars.add_cellar"))
    
    categories = AlcoholCategory.query.order_by(
        AlcoholCategory.display_order, AlcoholCategory.name
    ).all()
    
    # Récupérer les résultats d'analyse en session si présents
    detection_results = session.get("import_detection_results")
    uploaded_image = session.get("import_uploaded_image")
    
    return render_template(
        "import/index.html",
        cellars=cellars,
        categories=categories,
        detection_results=detection_results,
        uploaded_image=uploaded_image,
        default_cellar_id=current_user.default_cellar_id,
    )


@import_bp.route("/analyze", methods=["POST"])
@login_required
def analyze_image():
    """Analyse une image uploadée pour détecter les bouteilles."""
    
    if "image" not in request.files:
        flash("Veuillez sélectionner une image à analyser.")
        return redirect(url_for("import.index"))
    
    file = request.files["image"]
    if not file or not file.filename:
        flash("Veuillez sélectionner une image à analyser.")
        return redirect(url_for("import.index"))
    
    try:
        # Traiter l'image
        image_data, mime_type, thumbnail_data = _process_uploaded_image(file)
        
        # Récupérer les catégories disponibles pour l'analyse
        available_categories = _get_available_categories()
        
        # Analyser l'image (avec l'image complète et les catégories)
        service = _get_detection_service()
        result = service.analyze_image(image_data, mime_type, available_categories)
        
        if result.error:
            flash(f"Erreur lors de l'analyse : {result.error}")
            session.pop("import_detection_results", None)
            session.pop("import_uploaded_image", None)
            return redirect(url_for("import.index"))
        
        if not result.has_bottles():
            flash("Aucune bouteille n'a été détectée dans l'image. "
                  "Essayez avec une photo plus nette ou mieux éclairée.")
            session.pop("import_detection_results", None)
            session.pop("import_uploaded_image", None)
            return redirect(url_for("import.index"))
        
        # Enrichir les résultats avec les correspondances de sous-catégories et les doublons
        owner_id = current_user.owner_id
        bottles_data = []
        for bottle in result.bottles:
            bottle_dict = bottle.to_dict()
            bottle_dict["matched_subcategory_id"] = _match_alcohol_type(bottle.alcohol_type)
            # Rechercher les bouteilles existantes similaires
            bottle_dict["existing_bottles"] = _find_existing_bottles(bottle.name, owner_id)
            bottles_data.append(bottle_dict)
        
        # Sauvegarder les résultats en session (sans l'image pour éviter les cookies trop grands)
        session["import_detection_results"] = {
            "bottles": bottles_data,
            "total_bottles": result.total_bottles,
            "processing_time_ms": result.processing_time_ms,
        }
        
        # Ne pas stocker l'image en session - elle sera affichée côté client via JavaScript
        session.pop("import_uploaded_image", None)
        
        flash(f"✅ {result.total_bottles} bouteille(s) détectée(s) en {result.processing_time_ms}ms. "
              "Vérifiez et modifiez les informations si nécessaire avant de valider.")
        
    except Exception as exc:
        logger.exception("Erreur lors de l'analyse d'image: %s", exc)
        flash(f"Erreur lors du traitement de l'image : {str(exc)}")
        session.pop("import_detection_results", None)
    
    return redirect(url_for("import.index"))


@import_bp.route("/clear", methods=["POST"])
@login_required
def clear_results():
    """Efface les résultats d'analyse en session."""
    session.pop("import_detection_results", None)
    session.pop("import_uploaded_image", None)
    flash("Résultats effacés.")
    return redirect(url_for("import.index"))


@import_bp.route("/validate", methods=["POST"])
@login_required
def validate_import():
    """Valide et importe les bouteilles détectées."""
    owner_id = current_user.owner_id
    owner_account = current_user.owner_account
    
    # Récupérer les données du formulaire
    bottle_count = request.form.get("bottle_count", type=int, default=0)
    default_cellar_id = request.form.get("default_cellar_id", type=int)
    
    if bottle_count == 0:
        flash("Aucune bouteille à importer.")
        return redirect(url_for("import.index"))
    
    # Vérifier que la cave par défaut existe
    default_cellar = None
    if default_cellar_id:
        default_cellar = Cellar.query.filter_by(
            id=default_cellar_id, user_id=owner_id
        ).first()
    
    imported_count = 0
    errors = []
    
    for i in range(bottle_count):
        prefix = f"bottle_{i}_"
        
        # Vérifier si cette bouteille est sélectionnée pour l'import
        if not request.form.get(f"{prefix}selected"):
            continue
        
        try:
            name = (request.form.get(f"{prefix}name") or "").strip()
            if not name:
                errors.append(f"Bouteille {i+1}: Le nom est obligatoire.")
                continue
            
            quantity = request.form.get(f"{prefix}quantity", type=int, default=1)
            if quantity < 1:
                quantity = 1
            
            # Vérifier si on ajoute à une bouteille existante
            add_to_existing_id = request.form.get(f"{prefix}add_to_existing", type=int)
            
            if add_to_existing_id:
                # Ajouter la quantité à une bouteille existante
                existing_wine = Wine.query.filter_by(
                    id=add_to_existing_id, user_id=owner_id
                ).first()
                
                if existing_wine:
                    existing_wine.quantity += quantity
                    imported_count += 1
                    logger.info(
                        "Ajout de %d à la bouteille existante %s (ID: %d)",
                        quantity, existing_wine.name, existing_wine.id
                    )
                    continue
                else:
                    logger.warning(
                        "Bouteille existante ID %d non trouvée, création d'une nouvelle",
                        add_to_existing_id
                    )
            
            cellar_id = request.form.get(f"{prefix}cellar_id", type=int)
            if not cellar_id and default_cellar:
                cellar_id = default_cellar.id
            
            cellar = Cellar.query.filter_by(id=cellar_id, user_id=owner_id).first()
            if not cellar:
                errors.append(f"Bouteille {i+1} ({name}): Cave non trouvée.")
                continue
            
            subcategory_id = request.form.get(f"{prefix}subcategory_id", type=int)
            subcategory = None
            if subcategory_id:
                subcategory = AlcoholSubcategory.query.get(subcategory_id)
            
            # Construire les attributs supplémentaires
            extra_attributes = {}
            
            year = request.form.get(f"{prefix}year", type=int)
            if year:
                extra_attributes["year"] = year
            
            region = (request.form.get(f"{prefix}region") or "").strip()
            if region:
                extra_attributes["region"] = region
            
            grape = (request.form.get(f"{prefix}grape") or "").strip()
            if grape:
                extra_attributes["grape"] = grape
            
            volume_ml = request.form.get(f"{prefix}volume_ml", type=int)
            if volume_ml:
                extra_attributes["volume_ml"] = volume_ml
            
            description = (request.form.get(f"{prefix}description") or "").strip()
            if description:
                extra_attributes["description"] = description
            
            # Créer la bouteille
            wine = Wine(
                name=name,
                quantity=quantity,
                cellar=cellar,
                subcategory=subcategory,
                extra_attributes=extra_attributes,
                owner=owner_account,
            )
            db.session.add(wine)
            db.session.flush()  # Pour obtenir l'ID
            
            # Planifier l'enrichissement
            schedule_wine_enrichment(wine.id)
            
            # Notification
            try:
                notify_wine_added(wine, current_user.id)
            except Exception:
                pass
            
            imported_count += 1
            
        except Exception as exc:
            logger.exception("Erreur lors de l'import de la bouteille %d: %s", i, exc)
            errors.append(f"Bouteille {i+1}: Erreur inattendue - {str(exc)}")
    
    # Commit final
    if imported_count > 0:
        db.session.commit()
    
    # Nettoyer la session
    session.pop("import_detection_results", None)
    session.pop("import_uploaded_image", None)
    
    # Messages de résultat
    if imported_count > 0:
        flash(f"✅ {imported_count} bouteille(s) importée(s) avec succès ! "
              "L'enrichissement automatique est en cours.")
    
    for error in errors:
        flash(error)
    
    if imported_count > 0:
        return redirect(url_for("wines.overview"))
    else:
        return redirect(url_for("import.index"))


@import_bp.route("/api/analyze", methods=["POST"])
@login_required
def api_analyze_image():
    """
    API endpoint pour analyser une image (utilisé par AJAX).
    
    Returns:
        JSON avec les résultats de détection
    """
    if "image" not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400
    
    file = request.files["image"]
    if not file or not file.filename:
        return jsonify({"error": "Aucune image fournie"}), 400
    
    try:
        image_data, mime_type, thumbnail_data = _process_uploaded_image(file)
        
        # Récupérer les catégories disponibles pour l'analyse
        available_categories = _get_available_categories()
        
        service = _get_detection_service()
        result = service.analyze_image(image_data, mime_type, available_categories)
        
        if result.error:
            return jsonify({"error": result.error}), 500
        
        # Enrichir avec les correspondances de sous-catégories
        bottles_data = []
        for bottle in result.bottles:
            bottle_dict = bottle.to_dict()
            bottle_dict["matched_subcategory_id"] = _match_alcohol_type(bottle.alcohol_type)
            bottles_data.append(bottle_dict)
        
        return jsonify({
            "bottles": bottles_data,
            "total_bottles": result.total_bottles,
            "processing_time_ms": result.processing_time_ms,
            "image_preview": f"data:{mime_type};base64,{thumbnail_data}",
        })
        
    except Exception as exc:
        logger.exception("Erreur API analyse: %s", exc)
        return jsonify({"error": str(exc)}), 500


@import_bp.route("/api/create-subcategory", methods=["POST"])
@login_required
def api_create_subcategory():
    """
    API endpoint pour créer une sous-catégorie à la volée.
    
    Permet de créer automatiquement une catégorie détectée par l'IA
    qui n'existe pas encore dans le système.
    
    Returns:
        JSON avec les informations de la sous-catégorie créée
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données JSON requises"}), 400
    
    subcategory_name = (data.get("name") or "").strip()
    category_id = data.get("category_id")
    
    if not subcategory_name:
        return jsonify({"error": "Le nom de la sous-catégorie est requis"}), 400
    
    if not category_id:
        return jsonify({"error": "L'ID de la catégorie parente est requis"}), 400
    
    try:
        # Vérifier que la catégorie parente existe
        category = AlcoholCategory.query.get(category_id)
        if not category:
            return jsonify({"error": "Catégorie parente non trouvée"}), 404
        
        # Vérifier si la sous-catégorie existe déjà
        existing = AlcoholSubcategory.query.filter(
            AlcoholSubcategory.category_id == category_id,
            db.func.lower(AlcoholSubcategory.name) == subcategory_name.lower()
        ).first()
        
        if existing:
            return jsonify({
                "id": existing.id,
                "name": existing.name,
                "category_id": existing.category_id,
                "category_name": category.name,
                "already_exists": True,
            })
        
        # Calculer l'ordre d'affichage (à la fin)
        max_order = db.session.query(db.func.max(AlcoholSubcategory.display_order)).filter(
            AlcoholSubcategory.category_id == category_id
        ).scalar() or 0
        
        # Créer la nouvelle sous-catégorie
        new_subcategory = AlcoholSubcategory(
            name=subcategory_name,
            category_id=category_id,
            display_order=max_order + 1,
        )
        db.session.add(new_subcategory)
        db.session.commit()
        
        logger.info(
            "Nouvelle sous-catégorie créée: %s (ID: %d) dans %s",
            new_subcategory.name, new_subcategory.id, category.name
        )
        
        return jsonify({
            "id": new_subcategory.id,
            "name": new_subcategory.name,
            "category_id": new_subcategory.category_id,
            "category_name": category.name,
            "already_exists": False,
        })
        
    except Exception as exc:
        logger.exception("Erreur lors de la création de la sous-catégorie: %s", exc)
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500
