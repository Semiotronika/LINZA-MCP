FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LINZA_VAULT=/data/vault

WORKDIR /app

COPY pyproject.toml README_EN.md README.md LICENSE MANIFEST.in ./
COPY linza_mcp ./linza_mcp

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

VOLUME ["/data/vault"]

ENTRYPOINT ["linza-mcp"]
