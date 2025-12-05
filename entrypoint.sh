#!/bin/bash
# entrypoint.sh

python3 pixel_automator.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[ENTRYPOINT] Kopiowanie wyników do /app/output..."
    cp ksu_patched_*.zip /app/output/ 2>/dev/null
    cp build_status.json /app/output/ 2>/dev/null
    
    if [ "$(ls -A /app/output/)" ]; then
        echo "[ENTRYPOINT] ✅ Pliki skopiowane pomyślnie."
    else
        echo "[ENTRYPOINT] ⚠️  Ostrzeżenie: Nie znaleziono plików wynikowych."
    fi
else
    echo "[ENTRYPOINT] ❌ Skrypt Python zwrócił błąd."
fi

exit $EXIT_CODE