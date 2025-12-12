# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

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

# 3. Instalacja avbroot (via cargo - najbardziej pewna metoda)
# 3. Instalacja avbroot (pobranie gotowego pliku binarnego ZIP)
ENV AVBROOT_VERSION=v3.23.3
RUN curl -fSL -o /tmp/avbroot.zip "https://github.com/chenxiaolong/avbroot/releases/download/${AVBROOT_VERSION}/avbroot-3.23.3-x86_64-unknown-linux-gnu.zip" \
    && unzip /tmp/avbroot.zip -d /tmp \
    && mv /tmp/avbroot /usr/bin/avbroot \
    && chmod +x /usr/bin/avbroot \
    && rm /tmp/avbroot.zip

# 4. Instalacja custota-tool (pobranie gotowego pliku binarnego ZIP)
ENV CUSTOTA_TOOL_VERSION=v5.19
RUN curl -fSL -o /tmp/custota.zip "https://github.com/chenxiaolong/Custota/releases/download/${CUSTOTA_TOOL_VERSION}/custota-tool-5.19-x86_64-unknown-linux-gnu.zip" \
    && unzip /tmp/custota.zip -d /tmp \
    && mv /tmp/custota-tool /usr/bin/custota-tool \
    && chmod +x /usr/bin/custota-tool \
    && rm /tmp/custota.zip

# 4b. Instalacja avbtool (dla weryfikacji sygnatur Google)
RUN curl -fSL -o /tmp/avbtool.b64 https://android.googlesource.com/platform/external/avb/+/refs/heads/master/avbtool.py?format=TEXT \
    && base64 -d /tmp/avbtool.b64 > /usr/local/bin/avbtool.py \
    && chmod +x /usr/local/bin/avbtool.py \
    && rm /tmp/avbtool.b64

# 4c. Pre-download Magisk (Ensures build reproducibility & avoids API limits)
# Using Magisk v27.0 for stability
ENV MAGISK_VERSION=v27.0
RUN curl -fSL -o /usr/local/share/magisk.zip "https://github.com/topjohnwu/Magisk/releases/download/${MAGISK_VERSION}/Magisk-${MAGISK_VERSION}.apk"

# 5. Kopiowanie skryptów aplikacji i nadawanie uprawnień
COPY src/ /app/
RUN chmod +x /app/*.sh /app/*.py

# 6. Tworzenie katalogu wyjściowego
RUN mkdir -p /app/output

# 7. Ustawienie punktu wejścia
ENTRYPOINT ["/app/entrypoint.sh"]
