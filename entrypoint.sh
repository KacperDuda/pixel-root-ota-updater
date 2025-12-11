#!/bin/bash
# entrypoint.sh

python3 pixel_automator.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[ENTRYPOINT] Kopiowanie wyników do /app/output..."
    cp ksu_patched_*.zip /app/output/ 2>/dev/null
    cp build_status.json /app/output/ 2>/dev/null
    
    if [ "$(ls -A /app/output/)" ]; then
        # Fix permissions for host user (since we run as root inside Docker)
        chmod 777 /app/output/ksu_patched_*.zip 2>/dev/null
        chmod 777 /app/output/build_status.json 2>/dev/null
        echo "[ENTRYPOINT] ✅ Pliki skopiowane pomyślnie (uprawnienia poprawione)."
    else
        echo "[ENTRYPOINT] ⚠️  Ostrzeżenie: Nie znaleziono plików wynikowych."
    fi
else
    echo "[ENTRYPOINT] ❌ Skrypt Python zwrócił błąd."
fi

exit $EXIT_CODE