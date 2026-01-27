"""Service de notifications push pour Cave à Vin.

Ce module fournit des fonctions pour envoyer des notifications push
aux utilisateurs via Web Push API.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from flask import current_app


def get_vapid_config() -> tuple[str | None, dict[str, str]]:
    """Récupère la configuration VAPID depuis les variables d'environnement.
    
    Returns:
        tuple: (vapid_private_key, vapid_claims)
    """
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_claims = {
        "sub": os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com")
    }
    return vapid_private_key, vapid_claims


def is_push_configured() -> bool:
    """Vérifie si les notifications push sont configurées."""
    return bool(os.environ.get("VAPID_PRIVATE_KEY")) and bool(os.environ.get("VAPID_PUBLIC_KEY"))


def send_push_to_user(
    user_id: int,
    title: str,
    body: str,
    url: str = "/",
    icon: str = "/static/icons/icon-192x192.png",
    badge: str = "/static/icons/icon-72x72.png",
    tag: str | None = None,
    image: str | None = None,
    require_interaction: bool = False,
    actions: list[dict] | None = None,
) -> dict[str, Any]:
    """Envoie une notification push à un utilisateur spécifique.
    
    Args:
        user_id: ID de l'utilisateur destinataire
        title: Titre de la notification
        body: Corps du message
        url: URL à ouvrir au clic
        icon: URL de l'icône
        badge: URL du badge
        tag: Tag pour regrouper les notifications
        image: URL d'une image à afficher
        require_interaction: Si True, la notification reste jusqu'à interaction
        actions: Liste d'actions (boutons)
    
    Returns:
        dict: {"sent": int, "failed": int, "errors": list}
    """
    from models import PushSubscription, db
    
    if not is_push_configured():
        return {"sent": 0, "failed": 0, "errors": ["Notifications push non configurées"]}
    
    subscriptions = PushSubscription.query.filter_by(
        user_id=user_id,
        is_active=True
    ).all()
    
    if not subscriptions:
        return {"sent": 0, "failed": 0, "errors": []}
    
    payload = {
        "title": title,
        "body": body,
        "icon": icon,
        "badge": badge,
        "url": url,
        "tag": tag or f"notification-{datetime.utcnow().timestamp()}",
        "requireInteraction": require_interaction,
    }
    
    if image:
        payload["image"] = image
    
    if actions:
        payload["actions"] = actions
    
    return _send_to_subscriptions(subscriptions, payload)


def send_push_to_users(
    user_ids: list[int],
    title: str,
    body: str,
    url: str = "/",
    **kwargs
) -> dict[str, Any]:
    """Envoie une notification push à plusieurs utilisateurs.
    
    Args:
        user_ids: Liste des IDs utilisateurs
        title: Titre de la notification
        body: Corps du message
        url: URL à ouvrir au clic
        **kwargs: Options supplémentaires (icon, badge, tag, etc.)
    
    Returns:
        dict: {"sent": int, "failed": int, "errors": list, "users_notified": int}
    """
    from models import PushSubscription, db
    
    if not is_push_configured():
        return {"sent": 0, "failed": 0, "errors": ["Notifications push non configurées"], "users_notified": 0}
    
    if not user_ids:
        return {"sent": 0, "failed": 0, "errors": [], "users_notified": 0}
    
    subscriptions = PushSubscription.query.filter(
        PushSubscription.user_id.in_(user_ids),
        PushSubscription.is_active == True
    ).all()
    
    if not subscriptions:
        return {"sent": 0, "failed": 0, "errors": [], "users_notified": 0}
    
    payload = {
        "title": title,
        "body": body,
        "url": url,
        "icon": kwargs.get("icon", "/static/icons/icon-192x192.png"),
        "badge": kwargs.get("badge", "/static/icons/icon-72x72.png"),
        "tag": kwargs.get("tag", f"notification-{datetime.utcnow().timestamp()}"),
        "requireInteraction": kwargs.get("require_interaction", False),
    }
    
    if kwargs.get("image"):
        payload["image"] = kwargs["image"]
    
    if kwargs.get("actions"):
        payload["actions"] = kwargs["actions"]
    
    result = _send_to_subscriptions(subscriptions, payload)
    result["users_notified"] = len(set(s.user_id for s in subscriptions if s.is_active))
    return result


def send_push_to_account_family(
    user_id: int,
    title: str,
    body: str,
    url: str = "/",
    include_parent: bool = True,
    include_sub_accounts: bool = True,
    exclude_self: bool = False,
    **kwargs
) -> dict[str, Any]:
    """Envoie une notification à un compte et sa famille (parent + sous-comptes).
    
    Args:
        user_id: ID de l'utilisateur de référence
        title: Titre de la notification
        body: Corps du message
        url: URL à ouvrir au clic
        include_parent: Inclure le compte parent (si sous-compte)
        include_sub_accounts: Inclure les sous-comptes
        exclude_self: Exclure l'utilisateur lui-même
        **kwargs: Options supplémentaires
    
    Returns:
        dict: Résultat de l'envoi
    """
    from models import User
    
    user = User.query.get(user_id)
    if not user:
        return {"sent": 0, "failed": 0, "errors": ["Utilisateur non trouvé"], "users_notified": 0}
    
    target_ids = set()
    
    # Déterminer le compte principal
    if user.is_sub_account:
        owner = user.parent
        if include_parent:
            target_ids.add(owner.id)
    else:
        owner = user
    
    # Ajouter l'utilisateur lui-même si pas exclu
    if not exclude_self:
        target_ids.add(user_id)
    
    # Ajouter les sous-comptes du propriétaire
    if include_sub_accounts:
        for sub in owner.sub_accounts:
            if not exclude_self or sub.id != user_id:
                target_ids.add(sub.id)
    
    if not target_ids:
        return {"sent": 0, "failed": 0, "errors": [], "users_notified": 0}
    
    return send_push_to_users(list(target_ids), title, body, url, **kwargs)


def send_push_to_all_users(
    title: str,
    body: str,
    url: str = "/",
    exclude_admins: bool = False,
    **kwargs
) -> dict[str, Any]:
    """Envoie une notification à tous les utilisateurs.
    
    Args:
        title: Titre de la notification
        body: Corps du message
        url: URL à ouvrir au clic
        exclude_admins: Exclure les administrateurs
        **kwargs: Options supplémentaires
    
    Returns:
        dict: Résultat de l'envoi
    """
    from models import User, PushSubscription
    
    query = User.query
    if exclude_admins:
        query = query.filter(User.is_admin == False)
    
    user_ids = [u.id for u in query.all()]
    
    return send_push_to_users(user_ids, title, body, url, **kwargs)


def _send_to_subscriptions(subscriptions: list, payload: dict) -> dict[str, Any]:
    """Envoie une notification à une liste de subscriptions.
    
    Args:
        subscriptions: Liste d'objets PushSubscription
        payload: Données de la notification
    
    Returns:
        dict: {"sent": int, "failed": int, "errors": list}
    """
    from models import db
    
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return {
            "sent": 0,
            "failed": len(subscriptions),
            "errors": ["Module pywebpush non installé. Installez-le avec: pip install pywebpush"]
        }
    
    vapid_private_key, vapid_claims = get_vapid_config()
    
    if not vapid_private_key:
        return {
            "sent": 0,
            "failed": len(subscriptions),
            "errors": ["Clé VAPID privée non configurée"]
        }
    
    sent = 0
    failed = 0
    errors = []
    
    payload_json = json.dumps(payload)
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub.to_dict(),
                data=payload_json,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
            )
            sub.last_used_at = datetime.utcnow()
            sent += 1
        except WebPushException as e:
            failed += 1
            error_msg = str(e)
            if error_msg not in errors:
                errors.append(error_msg)
            
            # Désactiver les subscriptions invalides (410 Gone, 404 Not Found)
            if e.response and e.response.status_code in (404, 410):
                sub.is_active = False
        except Exception as e:
            failed += 1
            error_msg = f"Erreur inattendue: {str(e)}"
            if error_msg not in errors:
                errors.append(error_msg)
    
    try:
        db.session.commit()
    except Exception as e:
        errors.append(f"Erreur lors de la sauvegarde: {str(e)}")
    
    return {"sent": sent, "failed": failed, "errors": errors}


# ============================================================================
# Notifications automatiques pour les événements de l'application
# ============================================================================

def notify_wine_added(wine, actor_user_id: int) -> dict[str, Any]:
    """Notifie la famille d'un compte qu'une bouteille a été ajoutée.
    
    Args:
        wine: Objet Wine ajouté
        actor_user_id: ID de l'utilisateur qui a fait l'action
    
    Returns:
        dict: Résultat de l'envoi
    """
    extras = wine.extra_attributes or {}
    year = extras.get("year", "")
    year_str = f" {year}" if year else ""
    
    return send_push_to_account_family(
        user_id=actor_user_id,
        title="🍾 Nouvelle bouteille",
        body=f"{wine.name}{year_str} ajoutée à la cave",
        url=f"/wines/{wine.id}",
        exclude_self=True,
        tag=f"wine-added-{wine.id}",
    )


def notify_wine_consumed(wine, quantity: int, actor_user_id: int) -> dict[str, Any]:
    """Notifie la famille d'un compte qu'une bouteille a été consommée.
    
    Args:
        wine: Objet Wine consommé
        quantity: Nombre de bouteilles consommées
        actor_user_id: ID de l'utilisateur qui a fait l'action
    
    Returns:
        dict: Résultat de l'envoi
    """
    extras = wine.extra_attributes or {}
    year = extras.get("year", "")
    year_str = f" {year}" if year else ""
    
    qty_str = f"{quantity} bouteille{'s' if quantity > 1 else ''}"
    remaining = f" ({wine.quantity} restante{'s' if wine.quantity > 1 else ''})" if wine.quantity > 0 else " (épuisé)"
    
    return send_push_to_account_family(
        user_id=actor_user_id,
        title="🍷 Consommation",
        body=f"{qty_str} de {wine.name}{year_str}{remaining}",
        url=f"/wines/{wine.id}",
        exclude_self=True,
        tag=f"wine-consumed-{wine.id}",
    )


def notify_wine_updated(wine, actor_user_id: int, changes: list[str] | None = None) -> dict[str, Any]:
    """Notifie la famille d'un compte qu'une bouteille a été modifiée.
    
    Args:
        wine: Objet Wine modifié
        actor_user_id: ID de l'utilisateur qui a fait l'action
        changes: Liste des champs modifiés (optionnel)
    
    Returns:
        dict: Résultat de l'envoi
    """
    changes_str = ""
    if changes:
        changes_str = f" ({', '.join(changes[:3])})"
    
    return send_push_to_account_family(
        user_id=actor_user_id,
        title="📝 Bouteille modifiée",
        body=f"{wine.name}{changes_str}",
        url=f"/wines/{wine.id}",
        exclude_self=True,
        tag=f"wine-updated-{wine.id}",
    )


def notify_wine_deleted(wine_name: str, actor_user_id: int) -> dict[str, Any]:
    """Notifie la famille d'un compte qu'une bouteille a été supprimée.
    
    Args:
        wine_name: Nom de la bouteille supprimée
        actor_user_id: ID de l'utilisateur qui a fait l'action
    
    Returns:
        dict: Résultat de l'envoi
    """
    return send_push_to_account_family(
        user_id=actor_user_id,
        title="🗑️ Bouteille supprimée",
        body=f"{wine_name} a été retirée de la cave",
        url="/wines/overview",
        exclude_self=True,
        tag=f"wine-deleted-{datetime.utcnow().timestamp()}",
    )


def notify_low_stock(wine, threshold: int = 2) -> dict[str, Any]:
    """Notifie le propriétaire qu'une bouteille est en stock bas.
    
    Args:
        wine: Objet Wine en stock bas
        threshold: Seuil de stock bas
    
    Returns:
        dict: Résultat de l'envoi
    """
    if wine.quantity > threshold:
        return {"sent": 0, "failed": 0, "errors": []}
    
    return send_push_to_account_family(
        user_id=wine.user_id,
        title="⚠️ Stock bas",
        body=f"Il ne reste que {wine.quantity} bouteille{'s' if wine.quantity > 1 else ''} de {wine.name}",
        url=f"/wines/{wine.id}",
        exclude_self=False,
        tag=f"low-stock-{wine.id}",
        require_interaction=True,
    )


def notify_cellar_created(cellar, actor_user_id: int) -> dict[str, Any]:
    """Notifie la famille d'un compte qu'une cave a été créée.
    
    Args:
        cellar: Objet Cellar créé
        actor_user_id: ID de l'utilisateur qui a fait l'action
    
    Returns:
        dict: Résultat de l'envoi
    """
    return send_push_to_account_family(
        user_id=actor_user_id,
        title="📦 Nouvelle cave",
        body=f"Cave '{cellar.name}' créée ({cellar.capacity} emplacements)",
        url=f"/cellars/{cellar.id}",
        exclude_self=True,
        tag=f"cellar-created-{cellar.id}",
    )


def notify_cellar_deleted(cellar_name: str, actor_user_id: int) -> dict[str, Any]:
    """Notifie la famille d'un compte qu'une cave a été supprimée.
    
    Args:
        cellar_name: Nom de la cave supprimée
        actor_user_id: ID de l'utilisateur qui a fait l'action
    
    Returns:
        dict: Résultat de l'envoi
    """
    return send_push_to_account_family(
        user_id=actor_user_id,
        title="🗑️ Cave supprimée",
        body=f"La cave '{cellar_name}' a été supprimée",
        url="/cellars",
        exclude_self=True,
        tag=f"cellar-deleted-{datetime.utcnow().timestamp()}",
    )
