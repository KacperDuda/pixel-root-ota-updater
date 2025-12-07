#!/bin/bash
# Pixel User Data Backup (No Root Required)
# Quick backup of apps, settings, and device info

set -e

BACKUP_DIR="pixel_userdata_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "=== PIXEL USER DATA BACKUP ==="
echo "Backup dir: $BACKUP_DIR"
echo ""
echo "📱 What will be backed up:"
echo "   ✅ Apps and app data"
echo "   ✅ Device settings"
echo "   ✅ System info"
echo "   ❌ Partitions (you already have them!)"
echo ""
echo "⏱️  Time: ~5-15 minutes (depends on data size)"
echo "Press Enter to continue, CTRL+C to cancel..."
read

# Check ADB
if ! adb devices | grep -q "device$"; then
    echo "❌ No device connected via ADB"
    echo "   Enable USB debugging in Developer Options"
    exit 1
fi

echo "📱 Device connected!"
DEVICE=$(adb shell getprop ro.product.model | tr -d '\r')
echo "   Model: $DEVICE"
echo ""

# 1. Device info
echo "📋 Step 1/3: Saving device info..."
adb shell getprop > "$BACKUP_DIR/device_props.txt"
adb shell dumpsys package > "$BACKUP_DIR/packages.txt"
adb shell dumpsys battery > "$BACKUP_DIR/battery_info.txt"
adb shell df -h > "$BACKUP_DIR/storage_info.txt"
echo "   ✅ Done"
echo ""

# 2. Installed apps list
echo "📦 Step 2/3: Saving installed apps list..."
adb shell pm list packages -f > "$BACKUP_DIR/installed_packages.txt"
adb shell pm list packages -3 > "$BACKUP_DIR/user_apps.txt"  # Only user apps
echo "   ✅ Done"
echo ""

# 3. User data backup
echo "📱 Step 3/3: Backing up user data..."
echo ""
echo "⚠️  IMPORTANT: On your phone:"
echo "   1. A backup prompt will appear"
echo "   2. You can set a password (optional)"
echo "   3. TAP 'BACK UP MY DATA'"
echo ""
echo "Starting backup in 5 seconds..."
sleep 5

adb backup -f "$BACKUP_DIR/userdata.ab" -apk -shared -all -system

echo ""
echo "=== BACKUP COMPLETE ==="
echo ""
echo "📁 Location: $BACKUP_DIR"
echo "💾 Size:"
du -sh "$BACKUP_DIR"
echo ""
echo "📄 Files:"
ls -lh "$BACKUP_DIR/"
echo ""
echo "✅ Backup saved!"
echo ""
echo "To restore:"
echo "  adb restore $BACKUP_DIR/userdata.ab"
echo ""
echo "⚠️  Store this backup safely:"
echo "   - Copy to external drive"
echo "   - Upload to cloud (it's already encrypted!)"
