"""Utility for interacting with the OpenAI API with graceful fallbacks."""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Thin wrapper around the OpenAI REST API.

    The client is intentionally implemented with ``requests`` instead of the official
    SDK to minimise dependencies. It supports the Responses API which is available
    for both paid and free (gpt-4o-mini) models.
    """

    #: Preference order used when an API key is provided. The first model found in
    #: the list is picked if no explicit choice is configured by the user.
    _PREFERRED_MODELS: tuple[str, ...] = (
        "gpt-5-mini",
        "gpt-4.1-mini",
        "gpt-4o-mini",
        "gpt-4.1",
        "o4-mini",
    )

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        preferred_model: Optional[str] = None,
        free_model: Optional[str] = None,
        source_name: Optional[str] = None,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.preferred_model = (preferred_model or "").strip() or None
        self.free_model = (free_model or "").strip() or "gpt-4o-mini"
        self.source_name = source_name or "OpenAI"

        self._session = requests.Session()
        self._cached_models: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: Dict[str, Optional[str]]) -> "OpenAIClient":
        """Instantiate a client from a Flask app configuration mapping."""

        return cls(
            api_key=config.get("OPENAI_API_KEY"),
            base_url=config.get("OPENAI_BASE_URL"),
            preferred_model=config.get("OPENAI_MODEL"),
            free_model=config.get("OPENAI_FREE_MODEL"),
            source_name=config.get("OPENAI_SOURCE_NAME"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        """Indicate if at least one model can be queried."""

        return bool(self.api_key or self.free_model)

    def list_models(self, force_refresh: bool = False) -> List[str]:
        """Return the list of models available with the configured token."""

        if not self.api_key:
            return [self.free_model] if self.free_model else []

        if self._cached_models is not None and not force_refresh:
            return self._cached_models

        try:
            response = self._session.get(
                self._url("/models"),
                headers=self._headers(),
                timeout=15,
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure
            logger.warning("Unable to list OpenAI models: %s", exc)
            self._cached_models = []
            return self._cached_models

        if response.status_code != 200:
            logger.warning(
                "Listing OpenAI models failed with status %s: %s",
                response.status_code,
                response.text,
            )
            self._cached_models = []
            return self._cached_models

        payload = response.json()
        models = [model.get("id") for model in payload.get("data", []) if model.get("id")]
        self._cached_models = models
        return models

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        model: Optional[str] = None,
        max_output_tokens: int = 800,
    ) -> Optional[dict]:
        """Generate a JSON payload according to the provided schema."""

        if not self.is_available:
            return None

        selected_model = self._select_model(model)
        if not selected_model:
            logger.info("No OpenAI model available to satisfy the request")
            return None

        payload = {
            "model": selected_model,
            "input": [
                {
                    "role": "system",
                    "type": "message",
                    "content": system_prompt.strip(),
                },
                {
                    "role": "user",
                    "type": "message",
                    "content": user_prompt.strip(),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "wine_enrichment",
                    "schema": schema,
                }
            },
            "max_output_tokens": max_output_tokens,
        }

        try:
            response = self._session.post(
                self._url("/responses"),
                headers=self._headers(include_auth=bool(self.api_key)),
                json=payload,
                timeout=60,
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure
            logger.warning("OpenAI request failed: %s", exc)
            return None

        if response.status_code != 200:
            logger.warning(
                "OpenAI request failed with status %s: %s",
                response.status_code,
                response.text,
            )
            return None

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON payload returned by OpenAI")
            return None

        text_payload = self._extract_text_response(data)
        if text_payload is None:
            logger.warning("OpenAI response did not contain textual content")
            return None

        try:
            return json.loads(text_payload)
        except json.JSONDecodeError:
            logger.warning("OpenAI response was not valid JSON: %s", text_payload)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _select_model(self, override: Optional[str]) -> Optional[str]:
        if override:
            return override

        if self.api_key:
            available = self.list_models()
            if self.preferred_model and self.preferred_model in available:
                return self.preferred_model
            for candidate in self._PREFERRED_MODELS:
                if candidate in available:
                    return candidate
            if available:
                return available[0]

        return self.free_model

    def _extract_text_response(self, payload: dict) -> Optional[str]:
        outputs = payload.get("output") or []
        for block in outputs:
            for content in block.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if text:
                        return text
                if content.get("type") == "json":
                    try:
                        return json.dumps(content.get("json"))
                    except (TypeError, ValueError):
                        continue

        # Backwards compatibility with the chat completions-like payloads
        choices = payload.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            text = message.get("content")
            if text:
                return text

        return None

    def _headers(self, include_auth: bool = True) -> dict:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2",
        }
        if include_auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        org = os.environ.get("OPENAI_ORG")
        if org:
            headers["OpenAI-Organization"] = org
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


__all__ = ["OpenAIClient"]
