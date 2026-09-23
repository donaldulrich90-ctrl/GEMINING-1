# GOOD ENGINEERS OS — image de production (Django + gunicorn + WhiteNoise)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    GE_DATA_ROOT=/data

WORKDIR /app

# Dépendances système minimales (SQLite est inclus dans python:slim).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python (couche cache).
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code de l'application.
COPY . .

# Fichiers statiques rassemblés à la construction (clé jetable : l'env réel la remplace au runtime).
RUN GE_SECRET_KEY=build-time-only GE_DEBUG=0 python manage.py collectstatic --noinput

# Dossier des données persistantes (à monter comme volume dans Coolify).
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# gunicorn sert l'application ; WhiteNoise sert les fichiers statiques.
CMD ["sh", "-c", "gunicorn good_engineers_os.wsgi:application --bind 0.0.0.0:${PORT} --workers 3 --timeout 120 --access-logfile - --error-logfile -"]
