# # Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

ENV DEBIAN_FRONTEND=noninteractive

# 1. Instalacja narzędzi (dodano openssl)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    zip \
    unzip \
    git \
    jq \
    openssl \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalacja Python deps
RUN pip install --no-cache-dir requests beautifulsoup4 playwright==1.41.0

# Katalog roboczy
WORKDIR /app

# 3. Instalacja AVBTOOL
RUN curl -o /tmp/avbtool.b64 https://android.googlesource.com/platform/external/avb/+/refs/heads/master/avbtool.py?format=TEXT \
    && base64 -d /tmp/avbtool.b64 > /usr/local/bin/avbtool.py \
    && chmod +x /usr/local/bin/avbtool.py \
    && rm /tmp/avbtool.b64

# 4. Instalacja MAGISKBOOT
RUN echo "Pobieranie najnowszego Magiskboot..." \
    && MAGISK_URL=$(curl -sL https://api.github.com/repos/topjohnwu/Magisk/releases/latest | jq -r '.assets[] | select(.name | endswith(".apk")) | .browser_download_url' | head -n 1) \
    && echo "Znaleziono URL: $MAGISK_URL" \
    && wget -q "$MAGISK_URL" -O magisk.apk \
    && unzip -j magisk.apk "lib/x86_64/libmagiskboot.so" -d /tmp \
    && mv /tmp/libmagiskboot.so /usr/local/bin/magiskboot \
    && chmod +x /usr/local/bin/magiskboot \
    && rm -f magisk.apk

# Kopiowanie wszystkich skryptów
COPY pixel_automator.py /app/
COPY patcher.sh /app/
COPY entrypoint.sh /app/
COPY google_verifier.py /app/
COPY zip_extractor.py /app/

# Uprawnienia
RUN chmod +x /app/*.sh /app/*.py

# Tworzymy katalog output
RUN mkdir -p /app/output

ENTRYPOINT ["/app/entrypoint.sh"]