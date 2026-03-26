# --- build stage ---
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- runtime stage ---
FROM python:3.12-slim

RUN groupadd -r bot && useradd -r -g bot -d /app -s /sbin/nologin bot

WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

USER bot

# Run migrations, then start the bot. Migrations run on every deploy.
ENTRYPOINT ["/bin/sh", "-c", "alembic upgrade head && exec python -m app"]
