# TaskFlow Pro — application image
# Build context is the project root. See .dockerignore to keep the build lean.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + migration tooling.
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY pyproject.toml ./pyproject.toml

# Run as a non-root user.
# `storage` is the attachment upload root (UPLOAD_DIR, §17 / TASK-042): it must
# exist and be writable by appuser, otherwise uploads fail with EACCES.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
