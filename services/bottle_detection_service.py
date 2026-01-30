"""Service d'analyse d'images pour détecter et identifier plusieurs bouteilles."""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)


class TimedCall:
    """Context manager pour mesurer le temps d'exécution."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.duration_ms = 0
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        return False


@dataclass
class DetectedBottle:
    """Représente une bouteille détectée dans une image."""

    name: str
    quantity: int = 1
    year: Optional[int] = None
    region: Optional[str] = None
    grape: Optional[str] = None
    volume_ml: Optional[int] = None
    description: Optional[str] = None
    alcohol_type: Optional[str] = None  # Ex: "Vin rouge", "Champagne", "Rhum"
    confidence: float = 0.0  # Score de confiance de la détection (0-1)

    def to_dict(self) -> dict:
        """Convertit l'objet en dictionnaire."""
        return {
            "name": self.name,
            "quantity": self.quantity,
            "year": self.year,
            "region": self.region,
            "grape": self.grape,
            "volume_ml": self.volume_ml,
            "description": self.description,
            "alcohol_type": self.alcohol_type,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DetectedBottle":
        """Crée une instance à partir d'un dictionnaire."""
        # Convertir les valeurs 0 ou vides en None
        year = data.get("year")
        if year == 0:
            year = None
        
        region = data.get("region")
        if region == "" or region is None:
            region = None
        
        grape = data.get("grape")
        if grape == "" or grape is None:
            grape = None
        
        volume_ml = data.get("volume_ml")
        if volume_ml == 0:
            volume_ml = None
        
        description = data.get("description")
        if description == "" or description is None:
            description = None
        
        alcohol_type = data.get("alcohol_type")
        if alcohol_type == "" or alcohol_type is None:
            alcohol_type = None
        
        return cls(
            name=data.get("name", "Bouteille inconnue"),
            quantity=max(1, data.get("quantity", 1)),
            year=year,
            region=region,
            grape=grape,
            volume_ml=volume_ml,
            description=description,
            alcohol_type=alcohol_type,
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class DetectionResult:
    """Résultat de l'analyse d'une image."""

    bottles: List[DetectedBottle] = field(default_factory=list)
    total_bottles: int = 0
    error: Optional[str] = None
    processing_time_ms: int = 0

    def has_bottles(self) -> bool:
        """Vérifie si des bouteilles ont été détectées."""
        return len(self.bottles) > 0

    def to_dict(self) -> dict:
        """Convertit le résultat en dictionnaire."""
        return {
            "bottles": [b.to_dict() for b in self.bottles],
            "total_bottles": self.total_bottles,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
        }


class BottleDetectionService:
    """Service pour détecter et identifier des bouteilles dans une image."""

    def __init__(
        self,
        *,
        openai_client: Optional[OpenAI] = None,
        openai_model: Optional[str] = None,
        log_requests: bool = False,
        user_id: Optional[int] = None,
        source_name: str = "OpenAI",
    ) -> None:
        self.openai_client = openai_client
        self.openai_model = openai_model or "gpt-4o"
        self.log_requests = log_requests
        self.user_id = user_id
        self.source_name = source_name

    @classmethod
    def for_user(cls, user_id: int) -> "BottleDetectionService":
        """Factory qui initialise le service pour un utilisateur spécifique.
        
        Utilise la clé API personnelle de l'utilisateur si disponible,
        sinon la clé globale configurée dans l'admin.
        """
        from flask import current_app
        from services.openai_utils import get_openai_api_key_for_user
        
        logger.info("🔧 Initialisation de BottleDetectionService pour l'utilisateur %d", user_id)
        
        openai_client = None
        openai_model = "gpt-4o"
        source_name = "OpenAI"
        
        # Récupérer la clé API (utilisateur ou globale)
        api_key, key_source = get_openai_api_key_for_user(user_id)
        
        if api_key:
            # Récupérer la configuration globale pour les autres paramètres
            from app.models import OpenAIConfig
            config = OpenAIConfig.get_active()
            
            client_kwargs = {"api_key": api_key}
            
            if config:
                if config.base_url:
                    client_kwargs["base_url"] = config.base_url.rstrip("/")
                # Utiliser un modèle vision (gpt-4o par défaut)
                openai_model = config.default_model or "gpt-4o"
                # Pour la vision, on préfère gpt-4o
                if openai_model in ("gpt-4o-mini", "gpt-3.5-turbo"):
                    openai_model = "gpt-4o"
                source_name = config.source_name or "OpenAI"
            
            try:
                openai_client = OpenAI(**client_kwargs)
                logger.info("✅ Client OpenAI initialisé (source: %s)", key_source)
            except OpenAIError as exc:
                logger.warning("❌ Impossible d'initialiser le client OpenAI : %s", exc)
        else:
            logger.warning("⚠️ Aucune clé API OpenAI disponible")
        
        logger.info("📋 Modèle OpenAI Vision configuré: %s", openai_model)
        
        return cls(
            openai_client=openai_client,
            openai_model=openai_model,
            log_requests=False,  # Désactivé car le logging se fait en base de données via AICallLog
            user_id=user_id,
            source_name=source_name,
        )

    @classmethod
    def from_app(cls, app) -> "BottleDetectionService":
        """Factory qui utilise la configuration Flask pour initialiser le service."""
        logger.info("🔧 Initialisation de BottleDetectionService depuis l'application Flask")

        openai_client = None
        client_kwargs = {}

        api_key = (app.config.get("OPENAI_API_KEY") or "").strip()
        base_url = (app.config.get("OPENAI_BASE_URL") or "").strip()

        if api_key:
            client_kwargs["api_key"] = api_key

        if base_url:
            client_kwargs["base_url"] = base_url.rstrip("/")

        if client_kwargs:
            try:
                openai_client = OpenAI(**client_kwargs)
                logger.info("✅ Client OpenAI initialisé pour la détection de bouteilles")
            except OpenAIError as exc:
                logger.warning("❌ Impossible d'initialiser le client OpenAI : %s", exc)

        # Utiliser un modèle avec capacités vision
        openai_model = (
            (app.config.get("OPENAI_VISION_MODEL") or "").strip()
            or (app.config.get("OPENAI_MODEL") or "").strip()
            or "gpt-4o"
        )
        logger.info("📋 Modèle OpenAI Vision configuré: %s", openai_model)

        return cls(
            openai_client=openai_client,
            openai_model=openai_model,
            log_requests=bool(app.config.get("OPENAI_LOG_REQUESTS")),
        )

    def analyze_image(
        self,
        image_data: str,
        mime_type: str = "image/jpeg",
        available_categories: Optional[List[dict]] = None,
    ) -> DetectionResult:
        """
        Analyse une image pour détecter et identifier les bouteilles.

        Args:
            image_data: Image encodée en base64
            mime_type: Type MIME de l'image (image/jpeg, image/png, etc.)
            available_categories: Liste des catégories disponibles avec leurs sous-catégories
                                  Format: [{"name": "Vins", "subcategories": ["Vin rouge", "Vin blanc", ...]}, ...]

        Returns:
            DetectionResult contenant les bouteilles détectées
        """
        start_time = datetime.now()
        logger.info("🔍 Début de l'analyse d'image pour détection de bouteilles")

        if not self.openai_client:
            logger.error("❌ Client OpenAI non disponible")
            return DetectionResult(
                error="Le service d'analyse d'image n'est pas configuré. "
                      "Veuillez configurer OPENAI_API_KEY.",
                processing_time_ms=0,
            )

        try:
            result = self._analyze_with_openai(image_data, mime_type, available_categories)
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            result.processing_time_ms = processing_time
            logger.info(
                "✅ Analyse terminée: %d bouteilles détectées en %d ms",
                result.total_bottles,
                processing_time,
            )
            return result

        except Exception as exc:
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.exception("❌ Erreur lors de l'analyse d'image: %s", exc)
            return DetectionResult(
                error=f"Erreur lors de l'analyse: {str(exc)}",
                processing_time_ms=processing_time,
            )

    def _analyze_with_openai(
        self,
        image_data: str,
        mime_type: str,
        available_categories: Optional[List[dict]] = None,
    ) -> DetectionResult:
        """Utilise l'API OpenAI Vision pour analyser l'image."""

        # Construire la section des catégories disponibles si fournie
        categories_section = ""
        if available_categories:
            categories_section = "\n\nCATÉGORIES DISPONIBLES (utilise ces noms EXACTEMENT pour le champ alcohol_type si applicable):\n"
            for category in available_categories:
                cat_name = category.get("name", "")
                subcategories = category.get("subcategories", [])
                if subcategories:
                    categories_section += f"- {cat_name}: {', '.join(subcategories)}\n"
                else:
                    categories_section += f"- {cat_name}\n"
            categories_section += "\nSi aucune catégorie ne correspond vraiment, tu peux en suggérer une nouvelle, mais PRIVILÉGIE les catégories existantes."

        # Récupérer le prompt configurable depuis la base de données
        try:
            from app.models import OpenAIPrompt
            prompt_config = OpenAIPrompt.get_or_create_default("bottle_detection")
            system_prompt = prompt_config.render_system_prompt(categories_section=categories_section)
            user_prompt = prompt_config.render_user_prompt()
            schema = prompt_config.response_schema
            max_output_tokens = prompt_config.get_parameter("max_output_tokens", 2000)
        except Exception as e:
            logger.warning("⚠️ Impossible de charger le prompt configurable: %s. Utilisation des valeurs par défaut.", e)
            # Fallback aux valeurs par défaut
            system_prompt = f"""Tu es un expert sommelier et caviste. Tu analyses des photos de bouteilles d'alcool (vins, spiritueux, bières, etc.).

Pour chaque bouteille visible sur l'image, tu dois identifier avec PRÉCISION:
- Le nom COMPLET du produit incluant la marque ET la variante/gamme/couleur
  Exemples: "Chimay Bleue", "Château Margaux 2015", "Rhum Diplomatico Reserva Exclusiva", "Whisky Lagavulin 16 ans", "Leffe Blonde"
- Le type d'alcool PRÉCIS (champ alcohol_type):
  Pour les bières: "Bière blonde", "Bière brune", "Bière trappiste", "Bière blanche", "IPA", etc.
  Pour les vins: "Vin rouge", "Vin blanc", "Vin rosé", "Champagne", "Crémant", etc.
  Pour les spiritueux: "Rhum ambré", "Whisky single malt", "Vodka", "Gin", "Cognac", etc.
- Le millésime/année si visible sur l'étiquette
- La région d'origine ou le pays
- Le cépage pour les vins, ou le style/type pour les bières
- La contenance en mL (750, 330, 500, 1000, etc.)
- Une brève description des caractéristiques
{categories_section}

RÈGLES IMPORTANTES:
1. Le nom doit être COMPLET et PRÉCIS - inclure la couleur/variante (ex: "Chimay Bleue" pas juste "Chimay")
2. Pour les bières, TOUJOURS préciser la couleur ou le style dans le nom ET le type
3. Pour les vins, inclure le domaine/château ET l'appellation si visible
4. Si plusieurs bouteilles identiques, indiquer la quantité exacte
5. Utiliser 0 pour les nombres inconnus, chaîne vide pour les textes inconnus
6. Score de confiance basé sur la lisibilité de l'étiquette
7. Pour alcohol_type, UTILISE EN PRIORITÉ les catégories disponibles listées ci-dessus

Réponds UNIQUEMENT en JSON valide selon le schéma demandé."""

            user_prompt = """Analyse cette image et identifie TOUTES les bouteilles d'alcool visibles.

Pour chaque bouteille:
1. Lis ATTENTIVEMENT l'étiquette pour extraire le nom COMPLET (marque + variante/couleur)
2. Identifie le type PRÉCIS d'alcool (pas juste "bière" mais "bière trappiste brune")
3. Note toutes les informations visibles
4. Regroupe les bouteilles identiques avec leur quantité"""

            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "bottles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Nom du produit (domaine, château, marque)",
                                },
                                "quantity": {
                                    "type": "integer",
                                    "description": "Nombre de bouteilles identiques",
                                },
                                "year": {
                                    "type": "integer",
                                    "description": "Millésime ou année de production (0 si inconnu)",
                                },
                                "region": {
                                    "type": "string",
                                    "description": "Région d'origine (vide si inconnue)",
                                },
                                "grape": {
                                    "type": "string",
                                    "description": "Cépage principal (vide si inconnu)",
                                },
                                "volume_ml": {
                                    "type": "integer",
                                    "description": "Contenance en millilitres (0 si inconnue)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Brève description du produit",
                                },
                                "alcohol_type": {
                                    "type": "string",
                                    "description": "Type d'alcool (Vin rouge, Champagne, Rhum, etc.)",
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "Score de confiance de la détection (0-1)",
                                },
                            },
                            "required": ["name", "quantity", "year", "region", "grape", "volume_ml", "description", "alcohol_type", "confidence"],
                        },
                    },
                    "total_bottles": {
                        "type": "integer",
                        "description": "Nombre total de bouteilles détectées",
                    },
                },
                "required": ["bottles", "total_bottles"],
            }
            max_output_tokens = 2000

        # Construire l'URL de l'image en base64
        image_url = f"data:{mime_type};base64,{image_data}"

        logger.info("📤 Envoi de la requête à OpenAI Vision")

        # Préparer le prompt complet pour le logging (sans l'image)
        request_prompt = f"System: {system_prompt[:500]}...\n\nUser: {user_prompt}"

        try:
            with TimedCall() as timer:
                response = self.openai_client.responses.create(
                    model=self.openai_model,
                    input=[
                        {
                            "role": "system",
                            "content": [{"type": "input_text", "text": system_prompt}],
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": user_prompt},
                                {
                                    "type": "input_image",
                                    "image_url": image_url,
                                },
                            ],
                        },
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "bottle_detection",
                            "schema": schema,
                        },
                    },
                    max_output_tokens=max_output_tokens,
                )

            logger.info("✅ Réponse reçue de OpenAI Vision en %d ms", timer.duration_ms)

            # Log de la requête si activé (fichier)
            if self.log_requests:
                self._log_request_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                    response=response,
                )

            # Parser la réponse
            payload = self._parse_response(response)

            # Extraire les tokens de la réponse
            input_tokens = 0
            output_tokens = 0
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0
            except Exception:
                pass

            # Logger l'appel dans la base de données
            if self.user_id:
                self._log_ai_call(
                    call_type="bottle_detection",
                    request_prompt=request_prompt,
                    response_text=json.dumps(payload, ensure_ascii=False) if payload else None,
                    response_status="success" if payload else "error",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    response_time_ms=timer.duration_ms,
                )

            if not payload:
                return DetectionResult(
                    error="Impossible de parser la réponse de l'API",
                )

            # Construire le résultat
            bottles = []
            for bottle_data in payload.get("bottles", []):
                bottle = DetectedBottle.from_dict(bottle_data)
                bottles.append(bottle)

            total = payload.get("total_bottles", sum(b.quantity for b in bottles))

            return DetectionResult(
                bottles=bottles,
                total_bottles=total,
            )

        except OpenAIError as exc:
            logger.error("❌ Erreur OpenAI: %s", exc)
            
            # Logger l'erreur dans la base de données
            if self.user_id:
                self._log_ai_call(
                    call_type="bottle_detection",
                    request_prompt=request_prompt,
                    response_text=None,
                    response_status="error",
                    error_message=str(exc),
                    input_tokens=0,
                    output_tokens=0,
                    response_time_ms=0,
                )
            
            return DetectionResult(
                error=f"Erreur de l'API OpenAI: {str(exc)}",
            )

    def _parse_response(self, response) -> Optional[dict]:
        """Parse la réponse OpenAI."""
        if response is None:
            return None

        # Essayer output_text d'abord
        text_payload = getattr(response, "output_text", None)
        if text_payload:
            try:
                return json.loads(text_payload)
            except json.JSONDecodeError:
                logger.debug("❌ output_text n'est pas du JSON valide")

        # Essayer model_dump
        try:
            raw = response.model_dump()
        except Exception:
            raw = None

        if isinstance(raw, dict):
            outputs = raw.get("output") or []
            for block in outputs:
                for content in block.get("content", []):
                    if content.get("type") == "json":
                        candidate = content.get("json")
                        if isinstance(candidate, dict):
                            return candidate
                    if content.get("type") in {"text", "output_text"} and content.get("text"):
                        try:
                            return json.loads(content["text"])
                        except json.JSONDecodeError:
                            continue

        return None

    def _log_request_response(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        response,
    ) -> None:
        """Enregistre la requête et la réponse dans un fichier JSON."""
        try:
            log_dir = Path("logs/bottle_detection")
            log_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now()
            filename = timestamp.strftime("detection_%Y%m%d_%H%M%S_%f.json")
            filepath = log_dir / filename

            log_data = {
                "timestamp": timestamp.isoformat(),
                "model": self.openai_model,
                "request": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "schema": schema,
                },
                "response": {},
            }

            parsed_data = self._parse_response(response)
            log_data["response"]["parsed_data"] = parsed_data

            try:
                log_data["response"]["raw"] = response.model_dump() if response else None
            except Exception:
                log_data["response"]["raw"] = None

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.info("💾 Log de détection enregistré: %s", filepath)

        except Exception as exc:
            logger.error("❌ Erreur lors de l'enregistrement du log: %s", exc)

    def _log_ai_call(
        self,
        call_type: str,
        request_prompt: str,
        response_text: Optional[str],
        response_status: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        response_time_ms: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """Enregistre l'appel IA dans la base de données."""
        if not self.user_id:
            return
        
        try:
            from app.models import db, AICallLog
            
            # Déterminer la source de la clé API
            api_key_source = "global"
            try:
                from app.models import User
                user = User.query.get(self.user_id)
                if user and user.get_openai_api_key():
                    api_key_source = "user"
            except Exception:
                pass
            
            # Utiliser la méthode statique log_call qui gère le calcul du coût
            log_entry = AICallLog.log_call(
                user_id=self.user_id,
                call_type=call_type,
                model=self.openai_model,
                api_key_source=api_key_source,
                user_prompt=request_prompt[:5000] if request_prompt else None,  # Limiter la taille
                response_text=response_text[:10000] if response_text else None,  # Limiter la taille
                response_status=response_status,
                error_message=error_message,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=response_time_ms,
            )
            
            db.session.commit()
            
            logger.info(
                "📊 Appel IA loggé: type=%s, user=%d, tokens=%d/%d, coût=$%.6f",
                call_type,
                self.user_id,
                input_tokens,
                output_tokens,
                float(log_entry.estimated_cost_usd or 0),
            )
        
        except Exception as exc:
            logger.error("❌ Erreur lors du logging de l'appel IA: %s", exc)
            # Ne pas faire échouer l'appel principal si le logging échoue
            try:
                db.session.rollback()
            except Exception:
                pass
