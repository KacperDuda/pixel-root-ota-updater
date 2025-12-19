#!/bin/bash
# entrypoint.sh

python3 pixel_automator.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[ENTRYPOINT] Copying results to /app/output..."
    cp ksu_patched_*.zip /app/output/ 2>/dev/null
    cp *.csig /app/output/ 2>/dev/null
    cp *.json /app/output/ 2>/dev/null
    
    if [ "$(ls -A /app/output/)" ]; then
        # Fix permissions for host user (since we run as root inside Docker)
        chmod 777 /app/output/ksu_patched_*.zip 2>/dev/null
        chmod 777 /app/output/build_status.json 2>/dev/null
        echo "[ENTRYPOINT] ✅ Files copied successfully (permissions fixed)."
    else
        echo "[ENTRYPOINT] ℹ️  Info: No new output files found (Likely BUILD SKIPPED)."
    fi
else
    echo "[ENTRYPOINT] ❌ Python script returned an error."
fi

exit $EXIT_CODE