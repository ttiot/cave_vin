"""High level service that enriches wine entries with contextual information."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests

from .openai_client import OpenAIClient

logger = logging.getLogger(__name__)


@dataclass
class InsightData:
    """Transport object describing an insight about a wine."""

    category: Optional[str]
    title: Optional[str]
    content: str
    source_name: Optional[str]
    source_url: Optional[str]
    weight: int = 0


class WineInfoService:
    """Aggregate data from public APIs (Wikipedia, DuckDuckGo, OpenAI, …)."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        openai_client: Optional[OpenAIClient] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.openai_client = openai_client

    @classmethod
    def from_app(cls, app) -> "WineInfoService":
        """Factory that uses the Flask app configuration to bootstrap providers."""

        openai_client = OpenAIClient.from_config(app.config)
        return cls(openai_client=openai_client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch(self, wine) -> List[InsightData]:
        """Return a list of insights for the provided wine model instance."""

        query = self._build_query(wine)
        if not query:
            return []

        logger.info("Fetching contextual data for wine %s", query)
        insights: List[InsightData] = []

        providers = [
            ("wikipedia", lambda: self._wikipedia_insights(query)),
            ("duckduckgo", lambda: self._duckduckgo_insights(query)),
        ]

        if self.openai_client and self.openai_client.is_available:
            providers.append(("openai", lambda: self._openai_insights(wine, query)))

        for provider_name, provider_callable in providers:
            try:
                insights.extend(provider_callable())
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Provider %s failed for %s", provider_name, query)

        return self._deduplicate(insights)

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------
    def _wikipedia_insights(self, query: str) -> Iterable[InsightData]:
        """Return summary information collected through the Wikipedia API."""

        languages = ("fr", "en")
        for lang in languages:
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "format": "json",
            }
            search_response = self._request(
                f"https://{lang}.wikipedia.org/w/api.php", params=search_params
            )
            if not search_response:
                continue

            hits = search_response.get("query", {}).get("search", [])
            if not hits:
                continue

            hit = hits[0]
            page_id = hit.get("pageid")
            title = hit.get("title")
            if not page_id:
                continue

            extract_params = {
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "exintro": 1,
                "pageids": page_id,
                "format": "json",
            }
            extract_response = self._request(
                f"https://{lang}.wikipedia.org/w/api.php", params=extract_params
            )
            if not extract_response:
                continue

            pages = extract_response.get("query", {}).get("pages", {})
            page_data = pages.get(str(page_id))
            if not page_data:
                continue

            summary = page_data.get("extract", "")
            cleaned = self._clean_text(summary)
            if not cleaned:
                continue

            url_title = (title or "").replace(" ", "_")
            page_url = f"https://{lang}.wikipedia.org/wiki/{url_title}" if title else None
            source_name = f"Wikipedia ({lang})"

            yield InsightData(
                category="domaine",
                title=f"{title} — aperçu" if title else "Aperçu du domaine",
                content=self._truncate(cleaned, 800),
                source_name=source_name,
                source_url=page_url,
                weight=10,
            )

            if cleaned and len(cleaned) > 400:
                # Provide a shorter digest for the hover previews
                yield InsightData(
                    category="synthese",
                    title="Résumé rapide",
                    content=self._truncate(cleaned, 320),
                    source_name=source_name,
                    source_url=page_url,
                    weight=8,
                )

            # Stop at the first language that yields a result to avoid duplicates
            break

    def _duckduckgo_insights(self, query: str) -> Iterable[InsightData]:
        params = {
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "no_html": 1,
            "skip_disambig": 1,
        }
        response_json = self._request("https://api.duckduckgo.com/", params=params)
        if not response_json:
            return []

        abstract = self._clean_text(response_json.get("AbstractText"))
        abstract_url = response_json.get("AbstractURL") or None
        abstract_source = response_json.get("AbstractSource") or "DuckDuckGo"

        insights: List[InsightData] = []
        if abstract:
            insights.append(
                InsightData(
                    category="profil",
                    title=response_json.get("Heading") or "Profil général",
                    content=self._truncate(abstract, 600),
                    source_name=abstract_source,
                    source_url=abstract_url,
                    weight=5,
                )
            )

        related = response_json.get("RelatedTopics") or []
        bullets: List[str] = []
        for item in related:
            if isinstance(item, dict) and item.get("Text"):
                bullets.append(item["Text"])
            elif isinstance(item, dict) and item.get("Topics"):
                for sub_item in item["Topics"]:
                    if isinstance(sub_item, dict) and sub_item.get("Text"):
                        bullets.append(sub_item["Text"])
            if len(bullets) >= 3:
                break

        if bullets:
            formatted = "\n".join(f"• {self._clean_text(text)}" for text in bullets[:3])
            insights.append(
                InsightData(
                    category="faits_marquant",
                    title="Points clés",  # purposely french label
                    content=self._truncate(formatted, 600),
                    source_name="DuckDuckGo",
                    source_url=abstract_url,
                    weight=3,
                )
            )

        return insights

    def _openai_insights(self, wine, query: str) -> Iterable[InsightData]:
        if not self.openai_client or not self.openai_client.is_available:
            return []

        details = [f"Nom: {wine.name}"]
        if getattr(wine, "year", None):
            details.append(f"Millésime: {wine.year}")
        if getattr(wine, "region", None):
            details.append(f"Région: {wine.region}")
        if getattr(wine, "grape", None):
            details.append(f"Cépage: {wine.grape}")
        if getattr(wine, "description", None):
            details.append(
                f"Description utilisateur: {self._truncate(str(wine.description), 280)}"
            )
        if getattr(wine, "cellar", None):
            details.append(f"Cave: {wine.cellar.name}")
        details.append(f"Requête utilisée: {query}")

        system_prompt = (
            "Tu es un assistant sommelier chargé d'enrichir la fiche d'un vin. "
            "Tu réponds exclusivement en français et fournis des informations fiables, "
            "concis, adaptées à un public de passionnés."
        )

        user_prompt = (
            "Voici les informations connues sur le vin :\n"
            + "\n".join(f"- {line}" for line in details if line)
            + "\n\n"
            "Complète avec 3 à 5 éclairages distincts (histoire du domaine, profil aromatique, accords mets et vins, potentiel de garde, etc.). "
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
                        "required": ["content"],
                    },
                }
            },
            "required": ["insights"],
        }

        payload = self.openai_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            temperature=0.25,
            max_output_tokens=900,
        )

        if not payload:
            return []

        items = payload.get("insights") or []
        insights: List[InsightData] = []
        for index, item in enumerate(items[:5]):
            raw_content = (item.get("content") or "").strip()
            if not raw_content:
                continue

            category = (item.get("category") or "").strip() or "analyse"
            title = (item.get("title") or "").strip() or None
            source_name = (item.get("source") or self.openai_client.source_name).strip() or self.openai_client.source_name

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
                    content=self._truncate(raw_content, 900),
                    source_name=source_name,
                    source_url=None,
                    weight=weight_value,
                )
            )

        return insights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _request(self, url: str, params: Optional[dict[str, str]] = None) -> Optional[dict]:
        try:
            response = self.session.get(url, params=params, timeout=8)
        except requests.RequestException as exc:
            logger.warning("Request to %s failed: %s", url, exc)
            return None

        if response.status_code != 200:
            logger.warning("Request to %s failed with status %s", url, response.status_code)
            return None

        try:
            return response.json()
        except json.JSONDecodeError:
            logger.warning("Unable to decode JSON from %s", url)
            return None

    def _build_query(self, wine) -> str:
        parts = [wine.name]
        if getattr(wine, "year", None):
            parts.append(str(wine.year))
        if getattr(wine, "region", None):
            parts.append(wine.region)
        grape = getattr(wine, "grape", None)
        if grape:
            parts.append(grape)
        return " ".join(filter(None, parts)).strip()

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
    def _deduplicate(insights: Iterable[InsightData]) -> List[InsightData]:
        seen = set()
        result: List[InsightData] = []
        for insight in insights:
            key = (
                insight.category,
                insight.title,
                insight.content,
                insight.source_url,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(insight)
        return result
