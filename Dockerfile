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
    pv \
    bc \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Ustawienie katalogu roboczego
WORKDIR /app

# 2. Instalacja zależności Python (z requirements.txt dla lepszego cachowania)
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Instalacja avbroot (do patchowania i podpisywania)
ENV AVBROOT_VERSION=v3.4.0
RUN curl -L -o /usr/bin/avbroot "https://github.com/chenxiaolong/avbroot/releases/download/${AVBROOT_VERSION}/avbroot-x86_64-unknown-linux-gnu" \
    && chmod +x /usr/bin/avbroot

# 4. Instalacja custota-tool (do generowania metadata json)
ENV CUSTOTA_TOOL_VERSION=v5.0
RUN curl -L -o /usr/bin/custota-tool "https://github.com/chenxiaolong/Custota/releases/download/${CUSTOTA_TOOL_VERSION}/custota-tool-x86_64-unknown-linux-gnu" \
    && chmod +x /usr/bin/custota-tool

# 4b. Instalacja avbtool (dla weryfikacji sygnatur Google)
RUN curl -o /tmp/avbtool.b64 https://android.googlesource.com/platform/external/avb/+/refs/heads/master/avbtool.py?format=TEXT \
    && base64 -d /tmp/avbtool.b64 > /usr/local/bin/avbtool.py \
    && chmod +x /usr/local/bin/avbtool.py \
    && rm /tmp/avbtool.b64

# 5. Kopiowanie skryptów aplikacji i nadawanie uprawnień
COPY src/ /app/
RUN chmod +x /app/*.sh /app/*.py

# 6. Tworzenie katalogu wyjściowego
RUN mkdir -p /app/output

# 7. Ustawienie punktu wejścia
ENTRYPOINT ["/app/entrypoint.sh"]
