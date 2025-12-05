# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

ENV DEBIAN_FRONTEND=noninteractive

# 1. Instalacja podstawowych narzędzi systemowych
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

# Ustawienie katalogu roboczego
WORKDIR /app

# 2. Instalacja zależności Python (z requirements.txt dla lepszego cachowania)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Instalacja narzędzi deweloperskich (AVBTOOL)
# Ta warstwa zostanie zbuforowana, dopóki URL się nie zmieni
RUN curl -o /tmp/avbtool.b64 https://android.googlesource.com/platform/external/avb/+/refs/heads/master/avbtool.py?format=TEXT \
    && base64 -d /tmp/avbtool.b64 > /usr/local/bin/avbtool.py \
    && chmod +x /usr/local/bin/avbtool.py \
    && rm /tmp/avbtool.b64

# 4. Instalacja MAGISKBOOT (dynamicznie pobierana najnowsza wersja)
# UWAGA: Ta warstwa będzie rzadko cachowana, ponieważ URL do Magisk jest dynamiczny.
# Jest to celowe, aby zawsze używać najnowszej wersji magiskboot.
RUN echo "Pobieranie najnowszego Magiskboot..." \
    && MAGISK_URL=$(curl -sL https://api.github.com/repos/topjohnwu/Magisk/releases/latest | jq -r '.assets[] | select(.name | endswith(".apk")) | .browser_download_url' | head -n 1) \
    && echo "Znaleziono URL: $MAGISK_URL" \
    && wget -q "$MAGISK_URL" -O magisk.apk \
    && unzip -j magisk.apk "lib/x86_64/libmagiskboot.so" -d /tmp \
    && mv /tmp/libmagiskboot.so /usr/local/bin/magiskboot \
    && chmod +x /usr/local/bin/magiskboot \
    && rm -f magisk.apk

# 5. Kopiowanie skryptów aplikacji i nadawanie uprawnień
COPY pixel_automator.py patcher.sh entrypoint.sh google_verifier.py zip_extractor.py /app/
RUN chmod +x /app/*.sh /app/*.py

# 6. Tworzenie katalogu wyjściowego
RUN mkdir -p /app/output

# 7. Ustawienie punktu wejścia
ENTRYPOINT ["/app/entrypoint.sh"]
