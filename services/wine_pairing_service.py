"""Service de recommandation de vins basé sur l'IA pour les accords mets-vins."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.openai_client = openai_client
        self.openai_model = openai_model

    @classmethod
    def from_app(cls, app) -> "WinePairingService":
        """Factory qui utilise la configuration Flask pour initialiser le service."""
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

        current_year = datetime.now().year
        
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

        try:
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
                max_output_tokens=1500,
            )
            logger.info("✅ Réponse OpenAI reçue pour les recommandations")

        except OpenAIError as exc:
            logger.warning("❌ Requête OpenAI échouée : %s", exc)
            return None
        except Exception as exc:
            logger.warning("❌ Erreur inattendue lors de l'appel OpenAI : %s", exc)
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
