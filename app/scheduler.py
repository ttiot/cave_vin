"""Scheduler de tâches planifiées pour Cave à Vin.

Ce module lance un process séparé qui exécute les tâches planifiées
(rapports hebdomadaires, nettoyage, etc.) indépendamment des workers Gunicorn.

Usage:
    python -m app.scheduler

Le scheduler utilise APScheduler avec un BlockingScheduler pour rester actif.
Les jobs sont configurés via les variables d'environnement.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def create_scheduler_app():
    """Crée l'application Flask pour le contexte du scheduler."""
    # Import ici pour éviter les imports circulaires
    from app import create_app
    return create_app()


def job_listener(event):
    """Listener pour logger les événements des jobs."""
    if event.exception:
        logger.error(
            f"Job {event.job_id} a échoué avec l'erreur: {event.exception}"
        )
    else:
        logger.info(f"Job {event.job_id} exécuté avec succès")


def weekly_reports_job(app):
    """Job pour envoyer les rapports hebdomadaires."""
    logger.info("Démarrage du job: envoi des rapports hebdomadaires")
    
    with app.app_context():
        from app.scheduled_tasks import send_weekly_reports_to_all_users
        result = send_weekly_reports_to_all_users()
        logger.info(
            f"Rapports hebdomadaires: {result['sent']} envoyés, "
            f"{result['failed']} échecs"
        )


def cleanup_job(app):
    """Job pour nettoyer les anciennes données."""
    logger.info("Démarrage du job: nettoyage des anciennes données")
    
    with app.app_context():
        from app.scheduled_tasks import run_all_cleanup_tasks
        result = run_all_cleanup_tasks()
        logger.info(f"Nettoyage terminé: {result}")


def get_scheduler_config():
    """Récupère la configuration du scheduler depuis les variables d'environnement."""
    return {
        # Rapport hebdomadaire
        "weekly_report_enabled": os.environ.get(
            "SCHEDULER_WEEKLY_REPORT_ENABLED", "1"
        ).lower() in ("1", "true", "yes", "on"),
        "weekly_report_day": os.environ.get(
            "SCHEDULER_WEEKLY_REPORT_DAY", "mon"
        ),  # mon, tue, wed, thu, fri, sat, sun
        "weekly_report_hour": int(os.environ.get(
            "SCHEDULER_WEEKLY_REPORT_HOUR", "8"
        )),
        "weekly_report_minute": int(os.environ.get(
            "SCHEDULER_WEEKLY_REPORT_MINUTE", "0"
        )),
        
        # Nettoyage
        "cleanup_enabled": os.environ.get(
            "SCHEDULER_CLEANUP_ENABLED", "1"
        ).lower() in ("1", "true", "yes", "on"),
        "cleanup_day": os.environ.get(
            "SCHEDULER_CLEANUP_DAY", "sun"
        ),
        "cleanup_hour": int(os.environ.get(
            "SCHEDULER_CLEANUP_HOUR", "3"
        )),
        "cleanup_minute": int(os.environ.get(
            "SCHEDULER_CLEANUP_MINUTE", "0"
        )),
    }


def setup_scheduler(scheduler: BlockingScheduler, app) -> None:
    """Configure les jobs du scheduler."""
    config = get_scheduler_config()
    
    # Job: Rapports hebdomadaires
    if config["weekly_report_enabled"]:
        scheduler.add_job(
            weekly_reports_job,
            trigger=CronTrigger(
                day_of_week=config["weekly_report_day"],
                hour=config["weekly_report_hour"],
                minute=config["weekly_report_minute"],
            ),
            id="weekly_reports",
            name="Envoi des rapports hebdomadaires",
            args=[app],
            replace_existing=True,
            misfire_grace_time=3600,  # 1 heure de grâce si le job est manqué
        )
        logger.info(
            f"Job 'weekly_reports' configuré: {config['weekly_report_day']} "
            f"à {config['weekly_report_hour']:02d}:{config['weekly_report_minute']:02d}"
        )
    else:
        logger.info("Job 'weekly_reports' désactivé")
    
    # Job: Nettoyage
    if config["cleanup_enabled"]:
        scheduler.add_job(
            cleanup_job,
            trigger=CronTrigger(
                day_of_week=config["cleanup_day"],
                hour=config["cleanup_hour"],
                minute=config["cleanup_minute"],
            ),
            id="cleanup",
            name="Nettoyage des anciennes données",
            args=[app],
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            f"Job 'cleanup' configuré: {config['cleanup_day']} "
            f"à {config['cleanup_hour']:02d}:{config['cleanup_minute']:02d}"
        )
    else:
        logger.info("Job 'cleanup' désactivé")


def run_job_now(job_id: str) -> None:
    """Exécute un job immédiatement (utile pour les tests).
    
    Args:
        job_id: Identifiant du job ('weekly_reports' ou 'cleanup')
    """
    app = create_scheduler_app()
    
    with app.app_context():
        if job_id == "weekly_reports":
            from app.scheduled_tasks import send_weekly_reports_to_all_users
            result = send_weekly_reports_to_all_users()
            print(f"Résultat: {result}")
        elif job_id == "cleanup":
            from app.scheduled_tasks import run_all_cleanup_tasks
            result = run_all_cleanup_tasks()
            print(f"Résultat: {result}")
        else:
            print(f"Job inconnu: {job_id}")
            print("Jobs disponibles: weekly_reports, cleanup")


def main():
    """Point d'entrée principal du scheduler."""
    logger.info("=" * 60)
    logger.info("Démarrage du scheduler Cave à Vin")
    logger.info(f"Heure actuelle: {datetime.now().isoformat()}")
    logger.info("=" * 60)
    
    # Créer l'application Flask
    app = create_scheduler_app()
    
    # Créer le scheduler
    scheduler = BlockingScheduler(
        timezone="Europe/Paris",
        job_defaults={
            "coalesce": True,  # Fusionner les exécutions manquées
            "max_instances": 1,  # Une seule instance par job
        }
    )
    
    # Ajouter le listener pour les événements
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    
    # Configurer les jobs
    setup_scheduler(scheduler, app)
    
    # Afficher les jobs configurés (avant démarrage, next_run_time n'est pas encore calculé)
    jobs = scheduler.get_jobs()
    logger.info(f"Jobs configurés: {len(jobs)}")
    for job in jobs:
        logger.info(f"  - {job.id}: {job.name}")
    
    # Gérer l'arrêt propre
    def shutdown(signum, frame):
        logger.info("Signal d'arrêt reçu, arrêt du scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    # Démarrer le scheduler
    try:
        logger.info("Scheduler démarré, en attente des jobs...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler arrêté")


if __name__ == "__main__":
    # Support pour l'exécution manuelle d'un job
    if len(sys.argv) > 1:
        if sys.argv[1] == "run":
            if len(sys.argv) > 2:
                run_job_now(sys.argv[2])
            else:
                print("Usage: python -m app.scheduler run <job_id>")
                print("Jobs disponibles: weekly_reports, cleanup")
        else:
            print(f"Commande inconnue: {sys.argv[1]}")
            print("Usage:")
            print("  python -m app.scheduler        # Démarrer le scheduler")
            print("  python -m app.scheduler run <job_id>  # Exécuter un job")
    else:
        main()
