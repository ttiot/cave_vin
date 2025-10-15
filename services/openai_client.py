"""Utility for interacting with the OpenAI API with graceful fallbacks."""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Thin wrapper around the official OpenAI SDK Responses API."""

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
        default_base_url = "https://api.openai.com/v1"
        env_key = (os.environ.get("OPENAI_API_KEY") or "").strip() or None
        self.api_key = (api_key or "").strip() or env_key
        self.base_url = (base_url or default_base_url).rstrip("/")
        self.preferred_model = (preferred_model or "").strip() or None
        self.free_model = (free_model or "").strip() or "gpt-4o-mini"
        self.source_name = source_name or "OpenAI"

        client_kwargs: Dict[str, str] = {}
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        elif self.base_url != default_base_url:
            client_kwargs["api_key"] = ""

        if self.base_url != default_base_url:
            client_kwargs["base_url"] = self.base_url

        organization = (os.environ.get("OPENAI_ORG") or "").strip()
        if organization:
            client_kwargs["organization"] = organization

        self._client = None
        if client_kwargs:
            try:
                self._client = OpenAI(**client_kwargs)
            except OpenAIError as exc:  # pragma: no cover - defensive guard
                logger.warning("Unable to initialise OpenAI client: %s", exc)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Unexpected error initialising OpenAI client: %s", exc)
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

        return self._client is not None

    def list_models(self, force_refresh: bool = False) -> List[str]:
        """Return the list of models available with the configured token."""

        if not self._client:
            return [self.free_model] if self.free_model else []

        if self._cached_models is not None and not force_refresh:
            return self._cached_models

        try:
            response = self._client.models.list()
        except OpenAIError as exc:
            logger.warning("Unable to list OpenAI models: %s", exc)
            self._cached_models = []
            return self._cached_models
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unexpected failure when listing OpenAI models: %s", exc)
            self._cached_models = []
            return self._cached_models

        models = [
            getattr(model, "id", None)
            for model in getattr(response, "data", [])
            if getattr(model, "id", None)
        ]
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

        if not self._client:
            logger.info("OpenAI client not configured; skipping generation request")
            return None

        try:
            response = self._client.responses.create(
                model=selected_model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": system_prompt.strip()}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_prompt.strip()}],
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "wine_enrichment", "schema": schema},
                },
                max_output_tokens=max_output_tokens,
            )
        except OpenAIError as exc:
            logger.warning("OpenAI request failed: %s", exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unexpected OpenAI failure: %s", exc)
            return None

        data = response
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

    def _extract_text_response(self, payload) -> Optional[str]:
        if payload is None:
            return None

        if hasattr(payload, "output_text"):
            text = getattr(payload, "output_text", None)
            if text:
                return text
            try:
                payload = payload.model_dump()
            except Exception:  # pragma: no cover - defensive guard
                payload = None

        if not isinstance(payload, dict):
            return None

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
__all__ = ["OpenAIClient"]
