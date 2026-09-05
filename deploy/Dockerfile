# One image serving both the API and the built SPA from a single origin (spec A12).
#
# One artifact and one host is what "deployed" means for this milestone: it removes
# CORS, a second TLS certificate and a second deployment to keep in step.

# --- stage 1: build the SPA -------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /build

# Copy the manifests first so the dependency layer is reused when only source changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- stage 2: the runtime ---------------------------------------------------
FROM python:3.12-slim AS runtime

# PYTHONDONTWRITEBYTECODE: a read-only filesystem should not need .pyc scratch.
# PYTHONUNBUFFERED: logs must reach the platform's collector as they happen, not
# when a buffer happens to flush — a crash otherwise loses its own explanation.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/srv/static \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /srv/app

# Dependencies first, from the lockfile, so the layer caches independently of source.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

COPY --from=frontend /build/dist /srv/static
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Run as a non-root user: a container process that does not need root should not
# have it, and this one only reads its own code and talks to Postgres.
RUN useradd --system --create-home --uid 10001 planner \
    && chown -R planner:planner /srv
USER planner

EXPOSE 8000

# TLS is terminated at the platform's proxy (spec, Deployment), so the app itself
# speaks plain HTTP on this port and is never exposed directly.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["serve"]
