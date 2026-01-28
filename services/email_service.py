"""Service d'envoi d'emails via SMTP."""

from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime
from typing import TYPE_CHECKING

from flask import current_app, render_template

if TYPE_CHECKING:
    from models import SMTPConfig, User


def get_smtp_config() -> "SMTPConfig | None":
    """Récupère la configuration SMTP active."""
    from models import SMTPConfig
    return SMTPConfig.get_active()


def is_email_configured() -> bool:
    """Vérifie si l'envoi d'emails est configuré."""
    return get_smtp_config() is not None


def create_smtp_connection(config: "SMTPConfig") -> smtplib.SMTP | smtplib.SMTP_SSL:
    """Crée une connexion SMTP avec la configuration donnée."""
    if config.use_ssl:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=config.timeout)
    else:
        server = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
        if config.use_tls:
            context = ssl.create_default_context()
            server.starttls(context=context)
    
    # Authentification si nécessaire
    password = config.get_password()
    if config.username and password:
        server.login(config.username, password)
    
    return server


def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    config: "SMTPConfig | None" = None,
    recipient_user_id: int | None = None,
    template_name: str | None = None,
) -> dict:
    """
    Envoie un email.
    
    Args:
        to_email: Adresse email du destinataire
        subject: Sujet de l'email
        body_html: Corps de l'email en HTML
        body_text: Corps de l'email en texte brut (optionnel)
        config: Configuration SMTP à utiliser (optionnel, utilise la config par défaut sinon)
        recipient_user_id: ID de l'utilisateur destinataire (pour le log)
        template_name: Nom du template utilisé (pour le log)
    
    Returns:
        dict avec les clés 'success', 'error' (si échec)
    """
    from models import EmailLog, db
    
    if config is None:
        config = get_smtp_config()
    
    if config is None:
        return {"success": False, "error": "Aucune configuration SMTP disponible"}
    
    # Créer le log d'email
    email_log = EmailLog.log_email(
        recipient_email=to_email,
        subject=subject,
        smtp_config_id=config.id,
        recipient_user_id=recipient_user_id,
        template_name=template_name,
    )
    db.session.commit()
    
    try:
        # Créer le message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((config.sender_name or "", config.sender_email))
        msg["To"] = to_email
        
        # Ajouter le corps en texte brut
        if body_text:
            part_text = MIMEText(body_text, "plain", "utf-8")
            msg.attach(part_text)
        
        # Ajouter le corps en HTML
        part_html = MIMEText(body_html, "html", "utf-8")
        msg.attach(part_html)
        
        # Envoyer l'email
        with create_smtp_connection(config) as server:
            server.sendmail(config.sender_email, to_email, msg.as_string())
        
        # Marquer comme envoyé
        email_log.mark_sent()
        db.session.commit()
        
        current_app.logger.info(f"Email envoyé à {to_email}: {subject}")
        return {"success": True}
    
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Erreur d'authentification SMTP: {str(e)}"
        email_log.mark_failed(error_msg)
        db.session.commit()
        current_app.logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except smtplib.SMTPRecipientsRefused as e:
        error_msg = f"Destinataire refusé: {str(e)}"
        email_log.mark_failed(error_msg)
        db.session.commit()
        current_app.logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except smtplib.SMTPException as e:
        error_msg = f"Erreur SMTP: {str(e)}"
        email_log.mark_failed(error_msg)
        db.session.commit()
        current_app.logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Erreur lors de l'envoi: {str(e)}"
        email_log.mark_failed(error_msg)
        db.session.commit()
        current_app.logger.error(error_msg)
        return {"success": False, "error": error_msg}


def test_smtp_connection(config: "SMTPConfig") -> dict:
    """
    Teste la connexion SMTP.
    
    Returns:
        dict avec les clés 'success', 'error' (si échec)
    """
    from models import db
    
    try:
        with create_smtp_connection(config) as server:
            # Vérifier que la connexion fonctionne
            server.noop()
        
        # Mettre à jour le statut du test
        config.last_test_at = datetime.utcnow()
        config.last_test_success = True
        config.last_test_error = None
        db.session.commit()
        
        return {"success": True}
    
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Erreur d'authentification: {str(e)}"
        config.last_test_at = datetime.utcnow()
        config.last_test_success = False
        config.last_test_error = error_msg
        db.session.commit()
        return {"success": False, "error": error_msg}
    
    except smtplib.SMTPConnectError as e:
        error_msg = f"Impossible de se connecter au serveur: {str(e)}"
        config.last_test_at = datetime.utcnow()
        config.last_test_success = False
        config.last_test_error = error_msg
        db.session.commit()
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Erreur: {str(e)}"
        config.last_test_at = datetime.utcnow()
        config.last_test_success = False
        config.last_test_error = error_msg
        db.session.commit()
        return {"success": False, "error": error_msg}


def send_test_email(config: "SMTPConfig", to_email: str) -> dict:
    """
    Envoie un email de test.
    
    Args:
        config: Configuration SMTP à tester
        to_email: Adresse email de destination
    
    Returns:
        dict avec les clés 'success', 'error' (si échec)
    """
    subject = "🍷 Test de configuration email - Cave à Vin"
    
    tls_status = "Oui" if config.use_tls else "Non"
    ssl_status = "Oui" if config.use_ssl else "Non"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #722f37, #9b4d56); color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
                <h1 style="margin: 0;">🍷 Cave à Vin</h1>
            </div>
            <div style="background: #ffffff; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #28a745; font-weight: bold;">✅ Configuration réussie !</h2>
                <p>Cet email confirme que votre configuration SMTP fonctionne correctement.</p>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e0e0e0;"><strong>Serveur</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e0e0e0;">{config.host}:{config.port}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e0e0e0;"><strong>TLS</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e0e0e0;">{tls_status}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e0e0e0;"><strong>SSL</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e0e0e0;">{ssl_status}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px;"><strong>Expéditeur</strong></td>
                        <td style="padding: 8px;">{config.sender_email}</td>
                    </tr>
                </table>
                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                <p style="color: #6c757d; font-size: 12px; margin: 0;">
                    Cet email a été envoyé automatiquement depuis l'application Cave à Vin.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
    Cave à Vin - Test de configuration email
    
    ✅ Configuration réussie !
    
    Cet email confirme que votre configuration SMTP fonctionne correctement.
    
    Serveur : {config.host}:{config.port}
    TLS : {"Oui" if config.use_tls else "Non"}
    SSL : {"Oui" if config.use_ssl else "Non"}
    Expéditeur : {config.sender_email}
    """
    
    return send_email(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        config=config,
        template_name="test_email",
    )


def send_email_to_user(
    user: "User",
    subject: str,
    body_html: str,
    body_text: str | None = None,
    template_name: str | None = None,
) -> dict:
    """
    Envoie un email à un utilisateur.
    
    Args:
        user: Utilisateur destinataire
        subject: Sujet de l'email
        body_html: Corps de l'email en HTML
        body_text: Corps de l'email en texte brut (optionnel)
        template_name: Nom du template utilisé (pour le log)
    
    Returns:
        dict avec les clés 'success', 'error' (si échec)
    """
    if not user.email:
        return {"success": False, "error": "L'utilisateur n'a pas d'adresse email"}
    
    return send_email(
        to_email=user.email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        recipient_user_id=user.id,
        template_name=template_name,
    )


def send_email_to_users_with_email(
    subject: str,
    body_html: str,
    body_text: str | None = None,
    template_name: str | None = None,
    user_ids: list[int] | None = None,
) -> dict:
    """
    Envoie un email à tous les utilisateurs ayant une adresse email.
    
    Args:
        subject: Sujet de l'email
        body_html: Corps de l'email en HTML
        body_text: Corps de l'email en texte brut (optionnel)
        template_name: Nom du template utilisé (pour le log)
        user_ids: Liste d'IDs d'utilisateurs à cibler (optionnel, tous si None)
    
    Returns:
        dict avec les clés 'sent', 'failed', 'errors'
    """
    from models import User
    
    query = User.query.filter(User.email.isnot(None))
    if user_ids:
        query = query.filter(User.id.in_(user_ids))
    
    users = query.all()
    
    result = {"sent": 0, "failed": 0, "errors": []}
    
    for user in users:
        email_result = send_email_to_user(
            user=user,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            template_name=template_name,
        )
        
        if email_result["success"]:
            result["sent"] += 1
        else:
            result["failed"] += 1
            result["errors"].append(f"{user.email}: {email_result.get('error', 'Erreur inconnue')}")
    
    return result
