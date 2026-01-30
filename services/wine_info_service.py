"""High level service that enriches wine entries with contextual information."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urlparse

import bleach
import requests

from openai import OpenAI, OpenAIError
from app.field_config import FIELD_STORAGE_MAP, iter_fields

logger = logging.getLogger(__name__)

# Import conditionnel pour éviter les imports circulaires
def _get_openai_utils():
    from services.openai_utils import get_openai_client_for_user, log_ai_call, extract_token_usage, TimedCall
    return get_openai_client_for_user, log_ai_call, extract_token_usage, TimedCall


@dataclass
class InsightData:
    """Transport object describing an insight about a wine."""

    category: Optional[str]
    title: Optional[str]
    content: str
    source_name: Optional[str]
    source_url: Optional[str]
    weight: int = 0


@dataclass
class EnrichmentResult:
    """Aggregate payload produced for a wine enrichment run."""

    insights: List[InsightData]
    label_image_data: Optional[str] = None
    label_image_mime_type: str = "image/png"

    def has_payload(self) -> bool:
        return bool(self.insights or self.label_image_data)


class WineInfoService:
    """Aggregate data from public APIs (OpenAI)."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        openai_client: Optional[OpenAI] = None,
        openai_model: Optional[str] = None,
        openai_image_model: Optional[str] = None,
        openai_source_name: str = "OpenAI",
        log_openai_payloads: bool = False,
        user_id: Optional[int] = None,
        api_key_source: str = "env",
    ) -> None:
        self.session = session or requests.Session()
        self.openai_client = openai_client
        self.openai_model = openai_model
        self.openai_image_model = openai_image_model
        self.openai_source_name = openai_source_name
        self.log_openai_payloads = log_openai_payloads
        self.user_id = user_id
        self.api_key_source = api_key_source

    @classmethod
    def for_user(cls, user_id: int) -> "WineInfoService":
        """Factory qui crée un service avec la clé API appropriée pour l'utilisateur.
        
        Priorité des clés :
        1. Clé personnelle de l'utilisateur
        2. Clé globale configurée en base de données
        3. Clé de la variable d'environnement (fallback)
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            Instance de WineInfoService configurée pour l'utilisateur
        """
        logger.info("🔧 Initialisation de WineInfoService pour l'utilisateur %d", user_id)
        
        get_openai_client_for_user, _, _, _ = _get_openai_utils()
        
        client, api_key_source, config_info = get_openai_client_for_user(user_id)
        
        if client:
            logger.info("✅ Client OpenAI initialisé (source: %s)", api_key_source)
        else:
            logger.warning("⚠️ Aucun client OpenAI disponible pour l'utilisateur %d", user_id)
        
        return cls(
            openai_client=client,
            openai_model=config_info.get("model") or "gpt-4o-mini",
            openai_image_model=config_info.get("image_model"),
            openai_source_name=config_info.get("source_name") or "OpenAI",
            log_openai_payloads=False,  # Le logging se fait via AICallLog maintenant
            user_id=user_id,
            api_key_source=api_key_source,
        )

    @classmethod
    def from_app(cls, app) -> "WineInfoService":
        """Factory that uses the Flask app configuration to bootstrap providers.
        
        Note: Cette méthode est conservée pour la rétrocompatibilité.
        Pour les nouveaux usages, préférez `for_user(user_id)`.
        """
        logger.info("🔧 Initialisation de WineInfoService depuis l'application Flask")

        openai_client = None
        client_kwargs = {}

        api_key = (app.config.get("OPENAI_API_KEY") or "").strip()
        base_url = (app.config.get("OPENAI_BASE_URL") or "").strip()

        logger.debug("Configuration OpenAI - API Key présente: %s, Base URL: %s",
                    bool(api_key), base_url or "par défaut")

        if api_key:
            client_kwargs["api_key"] = api_key

        if base_url:
            client_kwargs["base_url"] = base_url.rstrip("/")

        if client_kwargs:
            try:
                openai_client = OpenAI(**client_kwargs)
                logger.info("✅ Client OpenAI initialisé avec succès")
            except OpenAIError as exc:  # pragma: no cover - defensive logging
                logger.warning("❌ Impossible d'initialiser le client OpenAI : %s", exc)

        openai_model = (
            (app.config.get("OPENAI_MODEL") or "").strip()
            or (app.config.get("OPENAI_FREE_MODEL") or "").strip()
            or "gpt-4o-mini"
        )
        logger.info("📋 Modèle OpenAI configuré: %s", openai_model)

        raw_image_model = (app.config.get("OPENAI_IMAGE_MODEL") or "").strip()
        openai_image_model = raw_image_model or ("dall-e-2" if openai_client else None)
        if openai_image_model:
            logger.info("🖼️ Modèle d'image OpenAI configuré: %s", openai_image_model)
        else:
            logger.info("🖼️ Génération d'étiquettes désactivée (aucun modèle configuré)")

        source_name = (app.config.get("OPENAI_SOURCE_NAME") or "OpenAI").strip() or "OpenAI"
        logger.debug("Source name: %s", source_name)

        return cls(
            openai_client=openai_client,
            openai_model=openai_model,
            openai_image_model=openai_image_model,
            openai_source_name=source_name,
            log_openai_payloads=bool(app.config.get("OPENAI_LOG_REQUESTS")),
            user_id=None,
            api_key_source="env",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch(self, wine) -> EnrichmentResult:
        """Return insights and optional label artwork for the provided wine."""
        logger.info("=" * 80)
        logger.info("🍷 Début de la récupération d'informations pour le vin: %s", wine.name)

        query = self._build_query(wine)
        logger.debug("🔍 Requête construite: '%s'", query)

        if not query:
            logger.warning("⚠️ Requête vide, abandon de la récupération")
            return EnrichmentResult(insights=[])

        logger.info("📊 Fetching contextual data for wine: %s", query)
        insights: List[InsightData] = []
        label_image_data: Optional[str] = None

        providers = []

        if self.openai_client:
            logger.info("🤖 Client OpenAI disponible, ajout du provider OpenAI")
            providers.append(("openai", lambda: self._openai_insights(wine, query)))
        else:
            logger.info("⚠️ Client OpenAI non disponible, skip du provider OpenAI")

        logger.info("📡 Nombre de providers à interroger: %d", len(providers))

        for provider_name, provider_callable in providers:
            logger.info("🔄 Interrogation du provider: %s", provider_name)
            try:
                provider_insights = list(provider_callable())
                insights.extend(provider_insights)
                logger.info("✅ Provider %s: %d insights récupérés",
                          provider_name, len(provider_insights))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("❌ Provider %s failed for %s: %s",
                               provider_name, query, exc)

        logger.info("🔄 Déduplication des insights (%d avant déduplication)", len(insights))
        deduplicated = self._deduplicate(insights)
        logger.info("✅ Récupération terminée: %d insights uniques", len(deduplicated))

        # Génération d'étiquette automatique désactivée
        # if self.openai_client and self.openai_image_model:
        #     logger.info("🖼️ Tentative de génération d'une étiquette stylisée")
        #     label_image_data = self._openai_label_image(wine, query)
        #     if label_image_data:
        #         logger.info("🖼️ Étiquette générée avec succès (%d caractères)", len(label_image_data))
        #     else:
        #         logger.info("⚠️ Aucune étiquette générée pour ce vin")

        logger.info("=" * 80)

        return EnrichmentResult(insights=deduplicated, label_image_data=label_image_data)

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------
    def _openai_insights(self, wine, query: str) -> Iterable[InsightData]:
        logger.info("🤖 OpenAI: début de la génération d'insights")

        if not self.openai_client:
            logger.warning("⚠️ OpenAI: client non disponible")
            return []

        if not self.openai_model:
            logger.info("⚠️ Aucun modèle OpenAI configuré ; abandon de la requête")
            return []

        logger.debug("🤖 OpenAI: modèle utilisé: %s", self.openai_model)

        details = [f"Nom: {wine.name}"]
        extra_attrs = getattr(wine, "extra_attributes", {}) or {}

        year = extra_attrs.get("year")
        if year:
            details.append(f"Millésime: {year}")

        region = extra_attrs.get("region")
        if region:
            details.append(f"Région: {region}")

        grape = extra_attrs.get("grape")
        if grape:
            details.append(f"Cépage: {grape}")

        volume_ml = extra_attrs.get("volume_ml")
        if volume_ml:
            details.append(f"Contenance: {volume_ml} mL")
        if getattr(wine, "subcategory", None):
            subcategory_name = wine.subcategory.name
            category_name = wine.subcategory.category.name if wine.subcategory.category else None
            if category_name:
                details.append(f"Type: {category_name} - {subcategory_name}")
            else:
                details.append(f"Type: {subcategory_name}")
        description = extra_attrs.get("description")
        if description:
            details.append(
                f"Description utilisateur: {self._truncate(str(description), 280)}"
            )
        try:
            extra_attributes = getattr(wine, "extra_attributes", {}) or {}
            for field in iter_fields():
                if field.name in {"region", "grape", "year", "volume_ml", "description"}:
                    continue
                storage = FIELD_STORAGE_MAP.get(field.name)
                if storage:
                    value = getattr(wine, storage.get("attribute"), None)
                else:
                    value = extra_attributes.get(field.name)
                if value:
                    details.append(f"{field.label}: {value}")
        except Exception:  # pragma: no cover - best effort enrichment
            pass
        details.append(f"Requête utilisée: {query}")

        logger.debug("📋 OpenAI: détails du vin collectés: %s", ", ".join(details))

        # Récupérer le prompt configurable depuis la base de données
        wine_details = "\n".join(f"- {line}" for line in details if line)
        
        try:
            from app.models import OpenAIPrompt
            prompt_config = OpenAIPrompt.get_or_create_default("wine_enrichment")
            system_prompt = prompt_config.render_system_prompt()
            user_prompt = prompt_config.render_user_prompt(wine_details=wine_details)
            schema = prompt_config.response_schema
            max_output_tokens = prompt_config.get_parameter("max_output_tokens", 900)
        except Exception as e:
            logger.warning("⚠️ Impossible de charger le prompt configurable: %s. Utilisation des valeurs par défaut.", e)
            # Fallback aux valeurs par défaut
            system_prompt = (
                "Tu es un assistant sommelier chargé d'enrichir la fiche d'un alcool. "
                "Tu réponds exclusivement en français et fournis des informations fiables, "
                "concis, adaptées à un public de passionnés."
            )

            user_prompt = (
                "Voici les informations connues sur l'alcool :\n"
                + wine_details
                + "\n\n"
                "Complète avec 4 à 6 éclairages distincts (estimation du prix actuel, histoire du domaine, profil aromatique, accords mets et vins, potentiel de garde, etc.). "
                "Chaque éclairage doit tenir en 2 à 4 phrases maximum."
                "Structure ta réponse au format JSON selon le schéma demandé, sans texte additionnel."
            )

            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "insights": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {"type": "string"},
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "source": {"type": "string"},
                                "weight": {"type": "integer"},
                            },
                            "required": ["category", "title", "content", "source", "weight"],
                        },
                    }
                },
                "required": ["insights"],
            }
            max_output_tokens = 900

        logger.info("📤 OpenAI: envoi de la requête à l'API")
        logger.debug(
            "Longueurs des prompts - système: %d, utilisateur: %d",
            len(system_prompt),
            len(user_prompt),
        )

        # Import des utilitaires pour le logging en base de données
        _, log_ai_call, extract_token_usage, TimedCall = _get_openai_utils()
        
        # Préparer le prompt complet pour le logging
        full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
        
        response = None
        error_message = None
        duration_ms = None
        
        try:
            # Utilisation de l'API Responses avec le type correct 'input_text'
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
                            "name": "wine_enrichment",
                            "schema": schema
                        },
                    },
                    max_output_tokens=max_output_tokens,
                )
            duration_ms = timer.duration_ms
            logger.info("✅ OpenAI: réponse reçue de l'API (durée: %dms)", duration_ms)

            # Enregistrement de la requête et de la réponse (fichier)
            self._log_openai_request_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                response=response,
                error=None
            )

        except OpenAIError as exc:
            error_message = str(exc)
            logger.warning("❌ Requête OpenAI échouée : %s", exc)
            self._log_openai_request_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                response=None,
                error=error_message
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            error_message = f"Unexpected error: {exc}"
            logger.warning("❌ Erreur inattendue lors de l'appel OpenAI : %s", exc)
            self._log_openai_request_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                response=None,
                error=error_message
            )
        
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
                    call_type="wine_enrichment",
                    model=self.openai_model,
                    api_key_source=self.api_key_source,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_text=response_text,
                    response_status="success" if error_message is None else "error",
                    error_message=error_message,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                )
                logger.debug("📊 Appel IA loggé en base de données")
            except Exception as log_exc:
                logger.warning("⚠️ Impossible de logger l'appel IA en base: %s", log_exc)
        
        # Si erreur, retourner une liste vide
        if error_message:
            return []

        logger.debug("🔍 OpenAI: parsing de la réponse")
        payload = self._parse_openai_payload(response)

        if not payload:
            logger.warning("⚠️ OpenAI: impossible de parser la réponse")
            return []

        items = payload.get("insights") or []
        logger.info("📊 OpenAI: %d insight(s) trouvé(s) dans la réponse", len(items))
        insights: List[InsightData] = []
        for index, item in enumerate(items[:5]):
            raw_content = (item.get("content") or "").strip()
            if not raw_content:
                logger.debug("⚠️ OpenAI: insight #%d ignoré (contenu vide)", index)
                continue

            category = self._sanitize_text(item.get("category")) or "analyse"
            logger.debug("✅ OpenAI: création insight #%d - catégorie: %s", index, category)
            title = self._sanitize_text(item.get("title"))
            source_name = (
                self._sanitize_text(item.get("source"))
                or self.openai_source_name
            )

            weight = item.get("weight")
            try:
                weight_value = int(weight)
            except (TypeError, ValueError):
                weight_value = max(1, 10 - index)
            weight_value = max(1, min(10, weight_value))

            insights.append(
                InsightData(
                    category=category,
                    title=title,
                    content=self._sanitize_content(self._truncate(raw_content, 900)),
                    source_name=source_name,
                    source_url=self._sanitize_source_url(item.get("url") or item.get("source_url")),
                    weight=weight_value,
                )
            )

        logger.info("✅ OpenAI: %d insight(s) créé(s) avec succès", len(insights))
        return insights

    def _openai_label_image(self, wine, query: str) -> Optional[str]:
        if not self.openai_client or not self.openai_image_model:
            return None

        prompt = self._build_label_prompt(wine, query)
        if not prompt:
            return None

        # Import des utilitaires pour le logging en base de données
        _, log_ai_call, _, TimedCall = _get_openai_utils()
        
        response = None
        error_message = None
        duration_ms = None
        
        try:
            with TimedCall() as timer:
                response = self.openai_client.images.generate(
                    model=self.openai_image_model,
                    prompt=prompt,
                    size="1024x1024",
                    n=1,
                    response_format="b64_json",
                )
            duration_ms = timer.duration_ms
            logger.info("✅ OpenAI: image générée (durée: %dms)", duration_ms)
        except OpenAIError as exc:
            error_message = str(exc)
            logger.warning("❌ OpenAI image generation failed: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            error_message = f"Unexpected error: {exc}"
            logger.warning("❌ Unexpected error during image generation: %s", exc)
        
        # Logging en base de données si un user_id est défini
        if self.user_id:
            try:
                # Pour les images, on estime les tokens différemment
                # DALL-E n'utilise pas de tokens mais un coût fixe par image
                log_ai_call(
                    user_id=self.user_id,
                    call_type="image_generation",
                    model=self.openai_image_model,
                    api_key_source=self.api_key_source,
                    user_prompt=prompt,
                    response_text="[IMAGE_GENERATED]" if response and not error_message else None,
                    response_status="success" if error_message is None else "error",
                    error_message=error_message,
                    input_tokens=0,  # Les images n'utilisent pas de tokens input
                    output_tokens=0,  # Les images n'utilisent pas de tokens output
                    duration_ms=duration_ms,
                )
                logger.debug("📊 Appel génération d'image loggé en base de données")
            except Exception as log_exc:
                logger.warning("⚠️ Impossible de logger l'appel image en base: %s", log_exc)
        
        # Si erreur, retourner None
        if error_message:
            return None

        payload = getattr(response, "data", None) or []
        if not payload:
            logger.info("⚠️ OpenAI image generation returned no data")
            return None

        first_item = payload[0]
        image_b64 = None

        if isinstance(first_item, dict):
            image_b64 = first_item.get("b64_json")
        else:
            image_b64 = getattr(first_item, "b64_json", None)

        if not image_b64:
            logger.info("⚠️ OpenAI image payload missing b64_json field")
            return None

        return image_b64.strip()

    def _build_label_prompt(self, wine, query: str) -> str:
        details = [
            f"Nom du vin : {wine.name}" if wine.name else None,
        ]

        extras = getattr(wine, "extra_attributes", {}) or {}

        if extras.get("year"):
            details.append(f"Millésime : {extras.get('year')}")
        if extras.get("region"):
            details.append(f"Région : {extras.get('region')}")
        if extras.get("grape"):
            details.append(f"Cépage : {extras.get('grape')}")
        if extras.get("description"):
            details.append(
                f"Notes du propriétaire : {self._truncate(str(extras.get('description')), 120)}"
            )
        if getattr(wine, "subcategory", None):
            subtype = wine.subcategory
            if subtype and subtype.category:
                details.append(
                    f"Catégorie : {subtype.category.name} / {subtype.name}"
                )
            elif subtype:
                details.append(f"Catégorie : {subtype.name}")

        detail_text = "; ".join(filter(None, details))

        base_prompt = (
            "Design a flat, poster-like illustration of a refined French wine label. "
            "Use elegant typography, subtle texture, and muted natural colors. "
            "Show only the label on a neutral background, no bottle photo. "
            "Incorporate the following information in French: "
        )

        prompt = f"{base_prompt}{detail_text}. Requête de référence: {query}."
        return prompt.strip()

    def _parse_openai_payload(self, response) -> Optional[dict]:
        logger.debug("🔍 Parsing de la réponse OpenAI")

        if response is None:
            logger.debug("⚠️ Réponse OpenAI est None")
            return None

        text_payload = getattr(response, "output_text", None)
        if text_payload:
            logger.debug("📝 Tentative de parsing depuis output_text")
            try:
                parsed = json.loads(text_payload)
                logger.debug("✅ Parsing réussi depuis output_text")
                return parsed
            except json.JSONDecodeError:
                logger.debug("❌ Le texte retourné par OpenAI n'est pas du JSON valide")

        logger.debug("🔍 Tentative de parsing depuis model_dump()")
        try:
            raw = response.model_dump()
            logger.debug("✅ model_dump() réussi, type: %s", type(raw))
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("❌ model_dump() échoué: %s", exc)
            raw = None

        if isinstance(raw, dict):
            logger.debug("📊 Analyse de la structure raw (dict)")
            outputs = raw.get("output") or []
            for block in outputs:
                for content in block.get("content", []):
                    if content.get("type") == "json":
                        logger.debug("✅ Trouvé un bloc de type 'json'")
                        candidate = content.get("json")
                        if isinstance(candidate, dict):
                            logger.debug("✅ Parsing réussi depuis bloc json")
                            return candidate
                        try:
                            return json.loads(json.dumps(candidate))
                        except (TypeError, ValueError):
                            continue
                    if content.get("type") in {"text", "output_text"} and content.get("text"):
                        logger.debug("🔍 Tentative de parsing depuis bloc text/output_text")
                        try:
                            parsed = json.loads(content["text"])
                            logger.debug("✅ Parsing réussi depuis bloc text")
                            return parsed
                        except json.JSONDecodeError:
                            logger.debug("❌ Parsing JSON échoué depuis bloc text")
                            continue

            choices = raw.get("choices") or []
            for choice in choices:
                message = choice.get("message") or {}
                text = message.get("content")
                if not text:
                    continue
                logger.debug("🔍 Tentative de parsing depuis choices.message.content")
                try:
                    parsed = json.loads(text)
                    logger.debug("✅ Parsing réussi depuis choices")
                    return parsed
                except json.JSONDecodeError:
                    logger.debug("❌ Parsing JSON échoué depuis choices")
                    continue

        logger.warning("⚠️ Impossible de parser la réponse OpenAI avec toutes les méthodes")
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _request(self, url: str, params: Optional[dict[str, str]] = None) -> Optional[dict]:
        logger.debug("🌐 Requête HTTP vers: %s", url)
        logger.debug("📋 Paramètres: %s", params)

        try:
            response = self.session.get(url, params=params, timeout=8)
            logger.debug("✅ Réponse reçue - Status: %d", response.status_code)
        except requests.RequestException as exc:
            logger.warning("❌ Request to %s failed: %s", url, exc)
            return None

        if response.status_code != 200:
            logger.warning("❌ Request to %s failed with status %s", url, response.status_code)
            return None

        try:
            json_data = response.json()
            logger.debug("✅ JSON décodé avec succès")
            return json_data
        except json.JSONDecodeError:
            logger.warning("❌ Unable to decode JSON from %s", url)
            return None

    def _build_query(self, wine) -> str:
        logger.debug("🔨 Construction de la requête pour le vin: %s", wine.name)
        parts = [wine.name]
        extra_attrs = getattr(wine, "extra_attributes", {}) or {}

        year = extra_attrs.get("year")
        if year:
            parts.append(str(year))

        region = extra_attrs.get("region")
        if region:
            parts.append(region)

        grape = extra_attrs.get("grape")
        if grape:
            parts.append(grape)
        query = " ".join(filter(None, parts)).strip()
        logger.debug("✅ Requête construite: '%s'", query)
        return query

    @staticmethod
    def _clean_text(value: Optional[str]) -> str:
        if not value:
            return ""
        text = re.sub(r"\s+", " ", value).strip()
        return text

    @staticmethod
    def _truncate(value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        return value[: max_length - 1].rstrip() + "…"

    @staticmethod
    def _sanitize_text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = bleach.clean(str(value), tags=[], attributes={}, strip=True).strip()
        return cleaned or None

    @classmethod
    def _sanitize_content(cls, value: Optional[str]) -> str:
        cleaned = cls._sanitize_text(value)
        return cleaned or ""

    @staticmethod
    def _sanitize_source_url(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        candidate = str(value).strip()
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"}:
            return None
        if not parsed.netloc:
            return None
        return candidate

    def _log_openai_request_response(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        response,
        error: Optional[str]
    ) -> None:
        """Enregistre la requête et la réponse OpenAI dans un fichier JSON."""
        if not self.log_openai_payloads:
            return

        try:
            # Créer le répertoire si nécessaire
            log_dir = Path("logs/openai_responses")
            log_dir.mkdir(parents=True, exist_ok=True)

            # Générer un nom de fichier unique avec timestamp
            timestamp = datetime.now()
            filename = timestamp.strftime("openai_%Y%m%d_%H%M%S_%f.json")
            filepath = log_dir / filename

            # Préparer les données de log
            log_data = {
                "timestamp": timestamp.isoformat(),
                "model": self.openai_model,
                "request": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "schema": schema
                },
                "response": {}
            }

            if error:
                log_data["response"]["error"] = error
                log_data["response"]["parsed_data"] = None
                logger.debug("💾 Enregistrement de l'erreur OpenAI dans: %s", filepath)
            else:
                # Tenter de parser la réponse
                parsed_data = self._parse_openai_payload(response)
                log_data["response"]["parsed_data"] = parsed_data

                # Ajouter la réponse brute si disponible
                try:
                    log_data["response"]["raw"] = response.model_dump() if response else None
                except Exception:
                    log_data["response"]["raw"] = None

                log_data["response"]["error"] = None
                logger.debug("💾 Enregistrement de la réponse OpenAI dans: %s", filepath)

            # Écrire le fichier JSON
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.info("✅ Log OpenAI enregistré: %s", filepath)

        except Exception as exc:
            logger.error("❌ Erreur lors de l'enregistrement du log OpenAI: %s", exc)

    @staticmethod
    def _deduplicate(insights: Iterable[InsightData]) -> List[InsightData]:
        seen = set()
        result: List[InsightData] = []
        duplicates_count = 0
        for insight in insights:
            key = (
                insight.category,
                insight.title,
                insight.content,
                insight.source_url,
            )
            if key in seen:
                duplicates_count += 1
                continue
            seen.add(key)
            result.append(insight)

        if duplicates_count > 0:
            logger.debug("🔄 Déduplication: %d doublons supprimés", duplicates_count)

        return result
