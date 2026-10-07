FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=build_ca,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 CATALOG_DATA_DIR=/data
RUN --mount=type=secret,id=build_ca,mode=0444 \
    set --; if [ -f /run/secrets/build_ca ]; then set -- -o Acquire::https::CaInfo=/run/secrets/build_ca; fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get "$@" update && apt-get "$@" install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 catalog && useradd --uid 10001 --gid catalog --no-create-home catalog \
    && mkdir -p /data && chown catalog:catalog /data
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN --mount=type=secret,id=build_ca,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --requirement requirements.txt
COPY --chown=catalog:catalog backend/app/ ./backend/app/
COPY --chown=catalog:catalog deploy/ ./deploy/
COPY --from=frontend /build/frontend/dist/ ./frontend/dist/
USER catalog
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
