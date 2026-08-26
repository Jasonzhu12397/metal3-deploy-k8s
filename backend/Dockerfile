FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
# Baked into the image so the container is self-contained wherever it
# runs (a Kubernetes Deployment has no host filesystem to volume-mount
# this from, unlike docker-compose's dev-convenience bind mount --
# see yaml_generator.py's _env(), which looks for /templates first and
# only falls back to TEMPLATES_DIR if that path doesn't exist).
COPY templates /templates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
