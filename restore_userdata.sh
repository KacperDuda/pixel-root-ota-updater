#!/bin/bash
# Restore User Data Backup

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_directory>"
    echo ""
    echo "Available backups:"
    ls -d pixel_userdata_* 2>/dev/null || echo "  (none found)"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "❌ Backup not found: $BACKUP_DIR"
    exit 1
fi

if [ ! -f "$BACKUP_DIR/userdata.ab" ]; then
    echo "❌ userdata.ab not found in $BACKUP_DIR"
    exit 1
fi

echo "=== PIXEL USER DATA RESTORE ==="
echo "Restoring from: $BACKUP_DIR"
echo ""

# Check ADB
if ! adb devices | grep -q "device$"; then
    echo "❌ No device connected"
    echo "   Enable USB debugging and connect phone"
    exit 1
fi

echo "📱 Device connected!"
echo ""
echo "⚠️  IMPORTANT:"
echo "   1. Restore prompt will appear on phone"
echo "   2. Enter backup password (if you set one)"
echo "   3. TAP 'RESTORE MY DATA'"
echo ""
echo "Press Enter to start restore..."
read

adb restore "$BACKUP_DIR/userdata.ab"

echo ""
echo "✅ Restore complete!"
echo ""
echo "Your apps and data should be restored."
echo "Some apps may need to re-login."
