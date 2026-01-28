# Scheduler - Tâches Planifiées

Ce document décrit le système de tâches planifiées de Cave à Vin.

## Architecture

Le scheduler est un **process séparé** qui s'exécute indépendamment des workers Gunicorn. Cette architecture évite les problèmes de double exécution liés aux multiples workers.

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Host                              │
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────┐         │
│  │   App (Gunicorn)    │    │     Scheduler       │         │
│  │   - Worker 1        │    │   (APScheduler)     │         │
│  │   - Worker 2        │    │                     │         │
│  │   - Worker 3        │    │   - weekly_reports  │         │
│  │                     │    │   - cleanup         │         │
│  └──────────┬──────────┘    └──────────┬──────────┘         │
│             │                          │                     │
│             └──────────┬───────────────┘                     │
│                        │                                     │
│                 ┌──────▼──────┐                              │
│                 │   SQLite    │                              │
│                 │   /data     │                              │
│                 └─────────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

## Jobs disponibles

### 1. Rapport hebdomadaire (`weekly_reports`)

Envoie un email récapitulatif à tous les utilisateurs avec :
- Statistiques des caves (nombre de bouteilles, taux de remplissage)
- Activité de la semaine (entrées/sorties)
- Vins à consommer (apogée atteinte ou dépassée)

**Configuration par défaut** : Lundi à 8h00

### 2. Nettoyage (`cleanup`)

Supprime les anciennes données pour maintenir les performances :
- Logs d'emails > 90 jours
- Logs d'activité > 180 jours
- Logs d'utilisation API > 30 jours

**Configuration par défaut** : Dimanche à 3h00

## Configuration

### Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `SCHEDULER_WEEKLY_REPORT_ENABLED` | Active le rapport hebdomadaire | `1` |
| `SCHEDULER_WEEKLY_REPORT_DAY` | Jour d'envoi (mon, tue, wed, thu, fri, sat, sun) | `mon` |
| `SCHEDULER_WEEKLY_REPORT_HOUR` | Heure d'envoi (0-23) | `8` |
| `SCHEDULER_WEEKLY_REPORT_MINUTE` | Minute d'envoi (0-59) | `0` |
| `SCHEDULER_CLEANUP_ENABLED` | Active le nettoyage automatique | `1` |
| `SCHEDULER_CLEANUP_DAY` | Jour de nettoyage | `sun` |
| `SCHEDULER_CLEANUP_HOUR` | Heure de nettoyage | `3` |
| `SCHEDULER_CLEANUP_MINUTE` | Minute de nettoyage | `0` |

### Exemple de configuration

```bash
# Rapport hebdomadaire le vendredi à 18h30
SCHEDULER_WEEKLY_REPORT_ENABLED=1
SCHEDULER_WEEKLY_REPORT_DAY=fri
SCHEDULER_WEEKLY_REPORT_HOUR=18
SCHEDULER_WEEKLY_REPORT_MINUTE=30

# Désactiver le nettoyage automatique
SCHEDULER_CLEANUP_ENABLED=0
```

## Déploiement

### Avec Docker Compose

Le fichier `docker-compose.yml` inclut le service scheduler :

```bash
# Démarrer tous les services
docker-compose up -d

# Voir les logs du scheduler
docker-compose logs -f scheduler

# Redémarrer le scheduler
docker-compose restart scheduler
```

### Sans Docker

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le scheduler
python -m app.scheduler
```

## Exécution manuelle

Pour tester ou exécuter un job manuellement :

```bash
# Exécuter le rapport hebdomadaire maintenant
python -m app.scheduler run weekly_reports

# Exécuter le nettoyage maintenant
python -m app.scheduler run cleanup
```

## Prérequis

### Pour les rapports par email

1. **Configuration SMTP** : Une configuration SMTP active doit être présente dans l'application (via l'interface admin).

2. **Emails utilisateurs** : Les utilisateurs doivent avoir une adresse email renseignée pour recevoir les rapports.

3. **Clé de chiffrement** : La variable `SMTP_ENCRYPTION_KEY` doit être définie pour déchiffrer les mots de passe SMTP.

## Logs

Le scheduler écrit ses logs sur stdout. En Docker, utilisez :

```bash
docker-compose logs -f scheduler
```

Exemple de sortie :

```
2024-01-15 08:00:00 - app.scheduler - INFO - Démarrage du job: envoi des rapports hebdomadaires
2024-01-15 08:00:05 - app.scheduler - INFO - Rapports hebdomadaires: 3 envoyés, 0 échecs
2024-01-15 08:00:05 - app.scheduler - INFO - Job weekly_reports exécuté avec succès
```

## Ajout de nouveaux jobs

Pour ajouter un nouveau job planifié :

1. **Créer la fonction métier** dans `app/scheduled_tasks.py` :

```python
def my_new_task():
    """Description de la tâche."""
    # Logique métier
    pass
```

2. **Créer le wrapper** dans `app/scheduler.py` :

```python
def my_new_job(app):
    """Job pour ma nouvelle tâche."""
    logger.info("Démarrage du job: ma nouvelle tâche")
    
    with app.app_context():
        from app.scheduled_tasks import my_new_task
        my_new_task()
```

3. **Enregistrer le job** dans `setup_scheduler()` :

```python
scheduler.add_job(
    my_new_job,
    trigger=CronTrigger(
        day_of_week="mon",
        hour=9,
        minute=0,
    ),
    id="my_new_job",
    name="Ma nouvelle tâche",
    args=[app],
    replace_existing=True,
)
```

## Dépannage

### Le scheduler ne démarre pas

1. Vérifiez que la base de données est accessible
2. Vérifiez les variables d'environnement
3. Consultez les logs : `docker-compose logs scheduler`

### Les emails ne sont pas envoyés

1. Vérifiez la configuration SMTP dans l'interface admin
2. Testez l'envoi d'email depuis l'interface
3. Vérifiez que `SMTP_ENCRYPTION_KEY` est définie
4. Vérifiez que les utilisateurs ont une adresse email

### Jobs manqués

APScheduler a une "grace time" de 1 heure. Si le scheduler redémarre dans l'heure suivant un job manqué, celui-ci sera exécuté.

Pour forcer l'exécution d'un job manqué :

```bash
python -m app.scheduler run weekly_reports
```
