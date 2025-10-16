"""Fonctions de formatage et sanitisation."""

from flask import request, url_for
from urllib.parse import urlparse


DEFAULT_BADGE_BG_COLOR = "#6366f1"
DEFAULT_BADGE_TEXT_COLOR = "#ffffff"


def sanitize_color(value: str, fallback: str) -> str:
    """Valide et nettoie une valeur de couleur hexadécimale.
    
    Args:
        value: Valeur de couleur à valider
        fallback: Couleur par défaut si la validation échoue
        
    Returns:
        Couleur hexadécimale valide en minuscules
    """
    value = (value or "").strip()
    if not value:
        return fallback

    if value.startswith('#') and len(value) in (4, 7):
        hex_part = value[1:]
        if all(c in '0123456789abcdefABCDEF' for c in hex_part):
            return value.lower()

    return fallback


def get_subcategory_badge_style(subcategory):
    """Retourne un style inline basé sur les couleurs configurées pour la sous-catégorie.
    
    Args:
        subcategory: Instance de AlcoholSubcategory ou None
        
    Returns:
        Chaîne de style CSS inline
    """
    if not subcategory:
        return f"background-color: {DEFAULT_BADGE_BG_COLOR}; color: {DEFAULT_BADGE_TEXT_COLOR};"

    background = sanitize_color(subcategory.badge_bg_color, DEFAULT_BADGE_BG_COLOR)
    text_color = sanitize_color(subcategory.badge_text_color, DEFAULT_BADGE_TEXT_COLOR)

    return f"background-color: {background}; color: {text_color};"


def resolve_redirect(default_endpoint: str) -> str:
    """Résout une redirection de manière sécurisée en validant l'URL.
    
    Args:
        default_endpoint: Endpoint Flask par défaut si la redirection n'est pas valide
        
    Returns:
        URL de redirection sécurisée
    """
    target = (request.form.get('redirect') or '').strip()
    
    # Validation stricte : uniquement les chemins relatifs sans '..'
    if target and target.startswith('/') and '..' not in target:
        # Vérifier que c'est un chemin valide de l'application
        try:
            parsed = urlparse(target)
            # Rejeter si contient un schéma (http://, etc.) ou un netloc (domaine)
            if parsed.scheme or parsed.netloc:
                return url_for(default_endpoint)
            return target
        except (ValueError, AttributeError):
            pass
    
    return url_for(default_endpoint)