# syntax=docker/dockerfile:1
FROM python:3.11-slim

# --- Sécurité & perfs ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_ROOT_USER_ACTION=ignore \
    # Gunicorn par défaut : ajuste si besoin (workers = 2*CPU+1 en général)
    GUNICORN_CMD_ARGS="--workers=3 --threads=2 --timeout=30 --graceful-timeout=30 --bind=0.0.0.0:8000 --access-logfile=-" \
    PORT=8000

WORKDIR /app

# Créer l'utilisateur applicatif en amont pour profiter de COPY --chown
RUN useradd -u 10001 -m appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data \
    && chmod 755 /data

# Dépendances système minimales (build puis clean)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl ca-certificates wget \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
 && pip install -r requirements.txt \
 && pip install gunicorn

# Code
COPY --chown=appuser:appuser . .
RUN chmod +x entrypoint.sh

# Utilisateur non-root
USER appuser

# Healthcheck (prévois une route /health qui renvoie 200)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

EXPOSE 8000

# Point d'entrée avec script de vérification des permissions
ENTRYPOINT ["/app/entrypoint.sh"]

# Lancement via Gunicorn (remplace 'wsgi:app' si ton module diffère)
# Exemple : FLASK_APP==wsgi.py contenant "app"
CMD ["gunicorn", "wsgi:app"]
