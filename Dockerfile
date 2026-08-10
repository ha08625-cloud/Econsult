# Build stage: install Node and build the frontend
FROM node:26-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Copy shared JSON constants that are imported by the frontend build.
# consultation_outcomes.json lives at app/core/ alongside the Python module
# that reads it. It is not inside frontend/, so it must be copied explicitly.
# The import in OutcomeScreen.tsx resolves two levels up from src/screens/
# to the /frontend workdir root, which is where this file lands.
COPY app/core/consultation_outcomes.json ./
# VITE_SENTRY_DSN is passed as a build argument so Vite can bake it into the
# compiled bundle. It is not a secret — the DSN is visible in browser network
# traffic regardless. Railway passes service variables as build args automatically
# when using the Dockerfile builder, so no railway.toml change is needed.
ARG VITE_SENTRY_DSN
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
RUN npm run build

# Final stage: Python runtime with built frontend
FROM python:3.14-slim

WORKDIR /app

# Apply OS-level security patches. This ensures that Debian system packages
# (including OpenSSL) are upgraded to their latest patched versions at build
# time, rather than relying on whatever was baked into the base image.
# --no-install-recommends keeps the image lean.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies, then strip the packaging toolchain (pip,
# setuptools, wheel) from the final image. Nothing at runtime imports pip,
# setuptools, or pkg_resources -- they are build-time-only tools. Keeping
# them around ships two CE+ Trivy findings that pip upgrades alone cannot
# fix: setuptools' own CVEs (e.g. CVE-2025-47273, a path traversal in its
# PackageIndex) and pip's vendored msgpack copy (e.g. GHSA-6v7p-g79w-8964),
# which stays pinned to a vulnerable version even in the latest pip release
# because pip vendors its own dependencies rather than resolving them.
# ensurepip's bundled pip wheel is also removed since it embeds the same
# vendored msgpack and would otherwise reintroduce the finding.
COPY requirements.txt ./
RUN pip install --no-cache-dir "setuptools>=78.1.1" \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y --no-input pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.14/ensurepip

# Copy application source
COPY app/ ./app/
COPY main.py ./
COPY worker_main.py ./
COPY pdf_worker_main.py ./
COPY mesh_worker_main.py ./
COPY deletion_job.py ./

# Copy Alembic configuration and migrations
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Copy data files (condition JSON rulesets)
COPY data/ ./data/

# Copy built frontend from build stage
COPY --from=frontend-build /frontend/dist ./frontend/dist

# Run as an unprivileged user. The application never writes to the container
# filesystem (PDFs and photos are stored in Postgres, logs go to stdout), so
# /app can remain root-owned and read-only to this user. A home directory is
# created so any library that expects a writable $HOME has one. Port 8000 is
# unprivileged, so no special capability is needed. All four processes (web,
# delivery worker, PDF worker, deletion job) share this image and therefore
# all run as this user.
RUN useradd --system --create-home appuser
USER appuser

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]