"""High level service that enriches wine entries with contextual information."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests

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
    """Aggregate data from public APIs (Wikipedia, DuckDuckGo, …)."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

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

        for provider in (self._wikipedia_insights, self._duckduckgo_insights):
            try:
                insights.extend(provider(query))
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Provider %s failed for %s", provider.__name__, query)

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
