"""Service de recommandation de vins basé sur l'IA pour les accords mets-vins."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)


# Import conditionnel pour éviter les imports circulaires
def _get_openai_utils():
    from services.openai_utils import get_openai_client_for_user, log_ai_call, extract_token_usage, TimedCall
    return get_openai_client_for_user, log_ai_call, extract_token_usage, TimedCall


@dataclass
class WineRecommendation:
    """Représente une recommandation de vin."""
    
    wine_id: int
    wine_name: str
    reason: str
    score: int  # Score de 1 à 10
    cellar_name: Optional[str] = None
    year: Optional[int] = None
    region: Optional[str] = None
    grape: Optional[str] = None
    subcategory: Optional[str] = None
    is_to_consume: bool = False  # True si le vin est à consommer en priorité
    garde_info: Optional[str] = None  # Information sur la garde


@dataclass
class PairingResult:
    """Résultat d'une recommandation d'accords mets-vins."""
    
    dish: str
    priority_wines: List[WineRecommendation]  # Vins à consommer en priorité
    best_wines: List[WineRecommendation]  # Meilleurs vins peu importe la garde
    explanation: str
    generated_at: datetime


class WinePairingService:
    """Service de recommandation de vins pour les accords mets-vins."""

    def __init__(
        self,
        openai_client: Optional[OpenAI] = None,
        openai_model: Optional[str] = None,
        user_id: Optional[int] = None,
        api_key_source: str = "env",
    ) -> None:
        self.openai_client = openai_client
        self.openai_model = openai_model
        self.user_id = user_id
        self.api_key_source = api_key_source

    @classmethod
    def for_user(cls, user_id: int) -> "WinePairingService":
        """Factory qui crée un service avec la clé API appropriée pour l'utilisateur.
        
        Priorité des clés :
        1. Clé personnelle de l'utilisateur
        2. Clé globale configurée en base de données
        3. Clé de la variable d'environnement (fallback)
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Instance de WinePairingService configurée pour l'utilisateur
        """
        logger.info("🔧 Initialisation de WinePairingService pour l'utilisateur %d", user_id)
        
        get_openai_client_for_user, _, _, _ = _get_openai_utils()
        
        client, api_key_source, config_info = get_openai_client_for_user(user_id)
        
        if client:
            logger.info("✅ Client OpenAI initialisé (source: %s)", api_key_source)
        else:
            logger.warning("⚠️ Aucun client OpenAI disponible pour l'utilisateur %d", user_id)
        
        return cls(
            openai_client=client,
            openai_model=config_info.get("model") or "gpt-4o-mini",
            user_id=user_id,
            api_key_source=api_key_source,
        )

    @classmethod
    def from_app(cls, app) -> "WinePairingService":
        """Factory qui utilise la configuration Flask pour initialiser le service.
        
        Note: Cette méthode est conservée pour la rétrocompatibilité.
        Pour les nouveaux usages, préférez `for_user(user_id)`.
        """
        logger.info("🔧 Initialisation de WinePairingService depuis l'application Flask")

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
                logger.info("✅ Client OpenAI initialisé pour WinePairingService")
            except OpenAIError as exc:
                logger.warning("❌ Impossible d'initialiser le client OpenAI : %s", exc)

        openai_model = (
            (app.config.get("OPENAI_MODEL") or "").strip()
            or (app.config.get("OPENAI_FREE_MODEL") or "").strip()
            or "gpt-4o-mini"
        )

        return cls(
            openai_client=openai_client,
            openai_model=openai_model,
            user_id=None,
            api_key_source="env",
        )

    def get_recommendations(
        self,
        dish: str,
        wines_data: List[dict],
    ) -> Optional[PairingResult]:
        """
        Obtient des recommandations de vins pour un plat donné.
        
        Args:
            dish: Description du plat prévu
            wines_data: Liste des vins disponibles au format JSON
            
        Returns:
            PairingResult avec les recommandations ou None si erreur
        """
        if not self.openai_client:
            logger.warning("⚠️ Client OpenAI non disponible pour les recommandations")
            return None

        if not wines_data:
            logger.warning("⚠️ Aucun vin disponible pour les recommandations")
            return None

        logger.info("🍷 Génération de recommandations pour le plat: %s", dish)
        logger.info("📊 Nombre de vins disponibles: %d", len(wines_data))

        # Préparer le JSON des vins (limité pour éviter les tokens excessifs)
        wines_json = json.dumps(wines_data[:100], ensure_ascii=False, indent=2)
        current_year = datetime.now().year

        # Récupérer le prompt configurable depuis la base de données
        try:
            from app.models import OpenAIPrompt
            prompt_config = OpenAIPrompt.get_or_create_default("wine_pairing")
            system_prompt = prompt_config.render_system_prompt()
            user_prompt = prompt_config.render_user_prompt(
                dish=dish,
                current_year=current_year,
                wines_json=wines_json
            )
            schema = prompt_config.response_schema
            max_output_tokens = prompt_config.get_parameter("max_output_tokens", 1500)
        except Exception as e:
            logger.warning("⚠️ Impossible de charger le prompt configurable: %s. Utilisation des valeurs par défaut.", e)
            # Fallback aux valeurs par défaut
            system_prompt = """Tu es un sommelier expert spécialisé dans les accords mets-vins.
Tu dois analyser la liste des vins disponibles et recommander les meilleurs accords pour le plat indiqué.

Tu dois fournir DEUX types de recommandations :
1. "priority_wines" : Les vins à consommer EN PRIORITÉ (ceux qui sont dans leur fenêtre de dégustation optimale ou qui doivent être bus rapidement selon leur garde)
2. "best_wines" : Les MEILLEURS vins pour ce plat, peu importe s'ils sont à consommer maintenant ou non

Pour chaque vin, tu dois :
- Évaluer l'accord avec le plat (score de 1 à 10)
- Expliquer pourquoi ce vin convient
- Indiquer si le vin est à consommer en priorité (basé sur l'année et la garde recommandée)
- Donner des informations sur la garde si disponibles

Réponds UNIQUEMENT en JSON selon le schéma demandé."""

            user_prompt = f"""Voici le plat prévu : {dish}

Année actuelle : {current_year}

Voici la liste des vins disponibles en JSON :
{wines_json}

Analyse ces vins et recommande :
1. 1 à 2 vins à consommer EN PRIORITÉ (qui sont dans leur fenêtre de dégustation ou doivent être bus bientôt)
2. 1 à 2 MEILLEURS vins pour ce plat (peu importe la garde)

IMPORTANT : Les vins recommandés dans "priority_wines" et "best_wines" doivent être DIFFÉRENTS.
Ne recommande pas le même vin dans les deux catégories.

Pour déterminer si un vin est à consommer en priorité, considère :
- L'année du millésime
- La garde recommandée (garde_min, garde_max dans extra_attributes)
- Le type de vin (les vins blancs et rosés se conservent généralement moins longtemps)

Fournis une explication générale sur les accords recommandés."""

            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "priority_wines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "wine_id": {"type": "integer"},
                                "reason": {"type": "string"},
                                "score": {"type": "integer"},
                                "garde_info": {"type": "string"},
                            },
                            "required": ["wine_id", "reason", "score", "garde_info"],
                        },
                    },
                    "best_wines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "wine_id": {"type": "integer"},
                                "reason": {"type": "string"},
                                "score": {"type": "integer"},
                                "garde_info": {"type": "string"},
                            },
                            "required": ["wine_id", "reason", "score", "garde_info"],
                        },
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["priority_wines", "best_wines", "explanation"],
            }
            max_output_tokens = 1500

        # Import des utilitaires pour le logging en base de données
        _, log_ai_call, extract_token_usage, TimedCall = _get_openai_utils()
        
        # Préparer le prompt complet pour le logging
        full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
        
        response = None
        error_message = None
        duration_ms = None
        
        try:
            with TimedCall() as timer:
                response = self.openai_client.responses.create(
                    model=self.openai_model,
                    input=[
                        {
                            "role": "system",
                            "content": [{"type": "input_text", "text": system_prompt.strip()}],
                        },
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": user_prompt.strip()}],
                        },
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "wine_pairing",
                            "schema": schema
                        },
                    },
                    max_output_tokens=max_output_tokens,
                )
            duration_ms = timer.duration_ms
            logger.info("✅ Réponse OpenAI reçue pour les recommandations (durée: %dms)", duration_ms)

        except OpenAIError as exc:
            error_message = str(exc)
            logger.warning("❌ Requête OpenAI échouée : %s", exc)
        except Exception as exc:
            error_message = f"Unexpected error: {exc}"
            logger.warning("❌ Erreur inattendue lors de l'appel OpenAI : %s", exc)
        
        # Logging en base de données si un user_id est défini
        if self.user_id:
            try:
                # Extraire les informations de tokens
                input_tokens, output_tokens = extract_token_usage(response) if response else (0, 0)
                
                # Préparer la réponse pour le log
                response_text = None
                if response:
                    try:
                        response_text = getattr(response, "output_text", None)
                        if not response_text:
                            response_text = json.dumps(response.model_dump(), ensure_ascii=False)
                    except Exception:
                        response_text = str(response)
                
                log_ai_call(
                    user_id=self.user_id,
                    call_type="wine_pairing",
                    model=self.openai_model,
                    prompt=full_prompt,
                    response=response_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    success=error_message is None,
                    error_message=error_message,
                    api_key_source=self.api_key_source,
                )
                logger.debug("📊 Appel IA loggé en base de données")
            except Exception as log_exc:
                logger.warning("⚠️ Impossible de logger l'appel IA en base: %s", log_exc)
        
        # Si erreur, retourner None
        if error_message:
            return None

        # Parser la réponse
        payload = self._parse_response(response)
        if not payload:
            logger.warning("⚠️ Impossible de parser la réponse OpenAI")
            return None

        # Créer un dictionnaire des vins pour lookup rapide
        wines_by_id = {w["id"]: w for w in wines_data}

        # Construire les recommandations prioritaires
        priority_wines = []
        for item in payload.get("priority_wines", []):
            wine_id = item.get("wine_id")
            wine_data = wines_by_id.get(wine_id)
            if wine_data:
                priority_wines.append(self._build_recommendation(
                    item, wine_data, is_to_consume=True
                ))

        # Construire les meilleures recommandations
        best_wines = []
        for item in payload.get("best_wines", []):
            wine_id = item.get("wine_id")
            wine_data = wines_by_id.get(wine_id)
            if wine_data:
                best_wines.append(self._build_recommendation(
                    item, wine_data, is_to_consume=False
                ))

        logger.info(
            "✅ Recommandations générées: %d prioritaires, %d meilleurs",
            len(priority_wines), len(best_wines)
        )

        return PairingResult(
            dish=dish,
            priority_wines=priority_wines,
            best_wines=best_wines,
            explanation=payload.get("explanation", ""),
            generated_at=datetime.utcnow(),
        )

    def _build_recommendation(
        self,
        item: dict,
        wine_data: dict,
        is_to_consume: bool,
    ) -> WineRecommendation:
        """Construit un objet WineRecommendation à partir des données."""
        extra = wine_data.get("extra_attributes", {}) or {}
        
        year = extra.get("year")
        if year:
            try:
                year = int(year)
            except (TypeError, ValueError):
                year = None

        return WineRecommendation(
            wine_id=wine_data["id"],
            wine_name=wine_data["name"],
            reason=item.get("reason", ""),
            score=item.get("score", 5),
            cellar_name=wine_data.get("cellar_name"),
            year=year,
            region=extra.get("region"),
            grape=extra.get("grape"),
            subcategory=wine_data.get("subcategory_name"),
            is_to_consume=is_to_consume,
            garde_info=item.get("garde_info"),
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
                pass

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

            choices = raw.get("choices") or []
            for choice in choices:
                message = choice.get("message") or {}
                text = message.get("content")
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        continue

        return None
