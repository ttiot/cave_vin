"""Service utilitaire pour la gestion des clés API OpenAI et le logging des appels."""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)


def get_openai_api_key_for_user(user_id: int) -> Tuple[Optional[str], str]:
    """Récupère la clé API OpenAI appropriée pour un utilisateur.
    
    Priorité :
    1. Clé personnelle de l'utilisateur (si configurée)
    2. Clé globale de l'application (si configurée et active)
    3. Clé de la variable d'environnement (fallback)
    
    Args:
        user_id: ID de l'utilisateur
        
    Returns:
        Tuple contenant :
        - La clé API (ou None si non disponible)
        - La source de la clé ("user", "global", "env", "none")
    """
    from flask import current_app
    from app.models import User, OpenAIConfig
    
    # 1. Vérifier si l'utilisateur a une clé personnelle
    user = User.query.get(user_id)
    if user and user.openai_api_key_encrypted:
        api_key = user.get_openai_api_key()
        if api_key:
            logger.info("🔑 Utilisation de la clé API personnelle pour l'utilisateur %d", user_id)
            return api_key, "user"
    
    # 2. Vérifier la configuration globale en base de données
    global_config = OpenAIConfig.get_active()
    if global_config and global_config.api_key_encrypted:
        api_key = global_config.get_api_key()
        if api_key:
            logger.info("🔑 Utilisation de la clé API globale")
            return api_key, "global"
    
    # 3. Fallback sur les variables d'environnement
    env_api_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
    if env_api_key:
        logger.info("🔑 Utilisation de la clé API depuis les variables d'environnement")
        return env_api_key, "env"
    
    logger.warning("⚠️ Aucune clé API OpenAI disponible")
    return None, "none"


def get_openai_client_for_user(user_id: int) -> Tuple[Optional[OpenAI], str, dict]:
    """Récupère le client OpenAI approprié pour un utilisateur.
    
    Priorité :
    1. Clé personnelle de l'utilisateur (si configurée)
    2. Clé globale de l'application (si configurée et active)
    3. Clé de la variable d'environnement (fallback)
    
    Args:
        user_id: ID de l'utilisateur
        
    Returns:
        Tuple contenant :
        - Le client OpenAI (ou None si non disponible)
        - La source de la clé ("user", "global", "env")
        - Un dictionnaire avec les informations de configuration
    """
    from flask import current_app
    from app.models import User, OpenAIConfig
    
    config_info = {
        "model": None,
        "image_model": None,
        "base_url": None,
        "source_name": "OpenAI",
    }
    
    # 1. Vérifier si l'utilisateur a une clé personnelle
    user = User.query.get(user_id)
    if user and user.openai_api_key_encrypted:
        api_key = user.get_openai_api_key()
        if api_key:
            logger.info("🔑 Utilisation de la clé API personnelle pour l'utilisateur %d", user_id)
            
            # Récupérer la config globale pour les autres paramètres
            global_config = OpenAIConfig.get_active()
            if global_config:
                config_info["model"] = global_config.default_model or "gpt-4o-mini"
                config_info["image_model"] = global_config.image_model
                config_info["base_url"] = global_config.base_url or "https://api.openai.com/v1"
                config_info["source_name"] = global_config.source_name or "OpenAI"
            else:
                # Fallback sur les variables d'environnement
                config_info["model"] = current_app.config.get("OPENAI_MODEL") or "gpt-4o-mini"
                config_info["image_model"] = current_app.config.get("OPENAI_IMAGE_MODEL")
                config_info["base_url"] = current_app.config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
                config_info["source_name"] = current_app.config.get("OPENAI_SOURCE_NAME") or "OpenAI"
            
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url=config_info["base_url"].rstrip("/") if config_info["base_url"] else None,
                )
                return client, "user", config_info
            except Exception as exc:
                logger.warning("❌ Erreur lors de l'initialisation du client avec la clé utilisateur : %s", exc)
    
    # 2. Vérifier la configuration globale en base de données
    global_config = OpenAIConfig.get_active()
    if global_config and global_config.api_key_encrypted:
        api_key = global_config.get_api_key()
        if api_key:
            logger.info("🔑 Utilisation de la clé API globale")
            
            config_info["model"] = global_config.default_model or "gpt-4o-mini"
            config_info["image_model"] = global_config.image_model
            config_info["base_url"] = global_config.base_url or "https://api.openai.com/v1"
            config_info["source_name"] = global_config.source_name or "OpenAI"
            
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url=config_info["base_url"].rstrip("/") if config_info["base_url"] else None,
                )
                return client, "global", config_info
            except Exception as exc:
                logger.warning("❌ Erreur lors de l'initialisation du client avec la clé globale : %s", exc)
    
    # 3. Fallback sur les variables d'environnement
    env_api_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
    if env_api_key:
        logger.info("🔑 Utilisation de la clé API depuis les variables d'environnement")
        
        config_info["model"] = current_app.config.get("OPENAI_MODEL") or current_app.config.get("OPENAI_FREE_MODEL") or "gpt-4o-mini"
        config_info["image_model"] = current_app.config.get("OPENAI_IMAGE_MODEL")
        config_info["base_url"] = current_app.config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        config_info["source_name"] = current_app.config.get("OPENAI_SOURCE_NAME") or "OpenAI"
        
        try:
            client_kwargs = {"api_key": env_api_key}
            if config_info["base_url"]:
                client_kwargs["base_url"] = config_info["base_url"].rstrip("/")
            
            client = OpenAI(**client_kwargs)
            return client, "env", config_info
        except Exception as exc:
            logger.warning("❌ Erreur lors de l'initialisation du client avec la clé env : %s", exc)
    
    logger.warning("⚠️ Aucune clé API OpenAI disponible")
    return None, "none", config_info


def log_ai_call(
    user_id: int,
    call_type: str,
    model: str,
    api_key_source: str,
    system_prompt: str = None,
    user_prompt: str = None,
    response_text: str = None,
    response_status: str = "success",
    error_message: str = None,
    input_tokens: int = None,
    output_tokens: int = None,
    duration_ms: int = None,
    context: dict = None,
) -> None:
    """Enregistre un appel IA dans les logs.
    
    Args:
        user_id: ID de l'utilisateur
        call_type: Type d'appel (enrichment, pairing, detection, image)
        model: Modèle utilisé
        api_key_source: Source de la clé (user, global, env)
        system_prompt: Prompt système (optionnel)
        user_prompt: Prompt utilisateur (optionnel)
        response_text: Texte de la réponse (optionnel)
        response_status: Statut (success, error)
        error_message: Message d'erreur si échec
        input_tokens: Nombre de tokens en entrée
        output_tokens: Nombre de tokens en sortie
        duration_ms: Durée de l'appel en ms
        context: Contexte additionnel (dict)
    """
    from app.models import db, AICallLog
    
    try:
        AICallLog.log_call(
            user_id=user_id,
            call_type=call_type,
            model=model,
            api_key_source=api_key_source,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            response_status=response_status,
            error_message=error_message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            context=context,
        )
        db.session.commit()
        logger.debug("✅ Log d'appel IA enregistré pour l'utilisateur %d", user_id)
    except Exception as exc:
        logger.error("❌ Erreur lors de l'enregistrement du log d'appel IA : %s", exc)
        db.session.rollback()


def extract_token_usage(response) -> Tuple[Optional[int], Optional[int]]:
    """Extrait les informations d'utilisation de tokens d'une réponse OpenAI.
    
    Args:
        response: Réponse de l'API OpenAI
        
    Returns:
        Tuple (input_tokens, output_tokens)
    """
    if response is None:
        return None, None
    
    # Essayer d'extraire depuis l'attribut usage
    usage = getattr(response, "usage", None)
    if usage:
        input_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
        return input_tokens, output_tokens
    
    # Essayer depuis model_dump
    try:
        raw = response.model_dump()
        if isinstance(raw, dict):
            usage_dict = raw.get("usage", {})
            if usage_dict:
                input_tokens = usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens")
                output_tokens = usage_dict.get("completion_tokens") or usage_dict.get("output_tokens")
                return input_tokens, output_tokens
    except Exception:
        pass
    
    return None, None


class TimedCall:
    """Context manager pour mesurer la durée d'un appel."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.duration_ms = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        return False
