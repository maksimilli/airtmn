# This small Space downloads an immutable, checksum-verified release of the portal.
# To upgrade, replace both the commit in the URL and the archive SHA256.
FROM python:3.12-slim-bookworm AS source
ADD --checksum=sha256:23fb42fcaf6bdba0ddcb0c90a3bfa18bb79de980790fc0d61b6de77c258b0df2 https://codeload.github.com/maksimilli/airtmn/tar.gz/ff2db861fd35993b456379508422f511bd5c6ac5 /tmp/source.tar.gz
RUN mkdir /source && python -c "import tarfile; tarfile.open('/tmp/source.tar.gz').extractall('/source', filter='data')"

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HOME=/home/catalog CATALOG_DATA_DIR=/data/catalog PORT=7860 \
    CATALOG_SERVER_MODE=1 CATALOG_COOKIE_SECURE=1 CATALOG_ADMIN_USERNAME=admin
RUN --mount=type=secret,id=build_ca,mode=0444 \
    set --; if [ -f /run/secrets/build_ca ]; then set -- -o Acquire::https::CaInfo=/run/secrets/build_ca; fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get "$@" update && apt-get "$@" install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 catalog && useradd --uid 1000 --gid catalog --create-home catalog \
    && mkdir -p /data/catalog && chown -R catalog:catalog /data
WORKDIR /app
COPY --from=source /source/airtmn-ff2db861fd35993b456379508422f511bd5c6ac5/backend/requirements.txt ./requirements.txt
RUN --mount=type=secret,id=build_ca,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --requirement requirements.txt
COPY --from=source --chown=catalog:catalog /source/airtmn-ff2db861fd35993b456379508422f511bd5c6ac5/backend/app/ ./backend/app/
COPY --from=source --chown=catalog:catalog /source/airtmn-ff2db861fd35993b456379508422f511bd5c6ac5/deploy/ ./deploy/
COPY --from=source --chown=catalog:catalog /source/airtmn-ff2db861fd35993b456379508422f511bd5c6ac5/frontend/dist/ ./frontend/dist/
USER catalog
EXPOSE 7860
CMD ["python", "deploy/start_hosted.py"]
