#!/bin/bash
set -e

# Script d'entrée pour le scheduler de tâches planifiées
# Ce script est utilisé comme point d'entrée pour le conteneur scheduler

echo "=== Cave à Vin - Scheduler ==="
echo "Démarrage: $(date -Iseconds)"

# Créer le répertoire /data s'il n'existe pas
mkdir -p /data

# S'assurer que l'utilisateur appuser peut écrire dans /data
if [ -w /data ]; then
    echo "Permissions /data OK"
else
    echo "Attention: Permissions /data insuffisantes"
    chmod 755 /data 2>/dev/null || true
fi

# Afficher la configuration du scheduler
echo ""
echo "Configuration:"
echo "  SCHEDULER_WEEKLY_REPORT_ENABLED=${SCHEDULER_WEEKLY_REPORT_ENABLED:-1}"
echo "  SCHEDULER_WEEKLY_REPORT_DAY=${SCHEDULER_WEEKLY_REPORT_DAY:-mon}"
echo "  SCHEDULER_WEEKLY_REPORT_HOUR=${SCHEDULER_WEEKLY_REPORT_HOUR:-8}"
echo "  SCHEDULER_CLEANUP_ENABLED=${SCHEDULER_CLEANUP_ENABLED:-1}"
echo "  SCHEDULER_CLEANUP_DAY=${SCHEDULER_CLEANUP_DAY:-sun}"
echo "  SCHEDULER_CLEANUP_HOUR=${SCHEDULER_CLEANUP_HOUR:-3}"
echo ""

# Lancer le scheduler
exec python -m app.scheduler "$@"
