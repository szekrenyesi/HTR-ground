# HTR-ground — production/self-host image
#
# Építés:   docker build -t htr-ground:latest .
# Futtatás: docker-compose up -d  (lásd docker-compose.yml)
#
# A konfigurációs és adatfájlok NINCSENEK az image-ben — bind mount-tal
# adod meg őket futtatáskor.

FROM python:3.12-slim AS base

# Rendszer runtime-függőségek (Pillow, lxml, bcrypt wheel-ek jellemzően
# ellátják magukat, de a natív libeket a futtatáshoz meghagyjuk).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        libpng16-16 \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── Függőségek külön layer-ben, hogy a cache jobban használódjon ──────
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# ─── Forráskód ─────────────────────────────────────────────────────────
COPY backend/  /app/backend/
COPY frontend/ /app/frontend/
COPY fonts/    /app/fonts/
COPY LICENSE README.md /app/

# A conf/auth_default.json az image-ben marad, hogy fresh deploy is
# induljon (az uvicorn nem hasal el egyből, a bootstrap CLI-t viszont
# le kell futtatni valódi userek felvételéhez).

ENV PYTHONUNBUFFERED=1
ENV HTR_GROUND_FONT=/app/fonts/EBGaramond-Regular.ttf

EXPOSE 8000
WORKDIR /app/backend

# Egyetlen worker — a presence in-memory, több worker esetén nem osztott
# állapot. Ha nagy forgalom lesz, HTTPS terminációt csinálj reverse proxy-val
# (nginx/Caddy), ne worker-számmal.
#
# --forwarded-allow-ips="*": bízunk a proxy X-Forwarded-Proto / -For fejléceiben.
# Ez akkor biztonságos, ha a container-t csak a proxy éri el (bind 127.0.0.1
# a docker-compose-ban HTTPS-hez).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--forwarded-allow-ips", "*"]
