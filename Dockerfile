# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKOFFICE_DIST_DIR=/opt/ascencia/frontend/dist

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Dist hors de /app pour rester disponible même si un bind-mount écrase /app
COPY --from=frontend /fe/dist /opt/ascencia/frontend/dist
COPY --from=frontend /fe/dist /app/frontend/dist

EXPOSE 8000

CMD ["python", "-m", "scripts.docker_entrypoint"]
