#!/bin/bash
# Verify A/B Slot Status
set -e

echo "=== A/B SLOT STATUS CHECKER ==="
echo ""

# Check if device in fastboot
if ! fastboot devices | grep -q "fastboot"; then
    echo "⚠️  Device not in fastboot mode"
    echo "   Trying to reboot to bootloader..."
    adb reboot bootloader 2>/dev/null || echo "   Connect phone and boot to bootloader manually"
    sleep 10
fi

echo "📋 Current slot information:"
echo ""

# Get current slot
CURRENT=$(fastboot getvar current-slot 2>&1 | grep "current-slot:" | awk '{print $2}')
echo "Current active slot: $CURRENT"
echo ""

# Slot A info
echo "=== Slot A ==="
fastboot getvar slot-retry-count:a 2>&1 | grep "slot-retry-count"
fastboot getvar slot-successful:a 2>&1 | grep "slot-successful"
fastboot getvar slot-unbootable:a 2>&1 | grep "slot-unbootable"
echo ""

# Slot B info
echo "=== Slot B ==="
fastboot getvar slot-retry-count:b 2>&1 | grep "slot-retry-count"
fastboot getvar slot-successful:b 2>&1 | grep "slot-successful"
fastboot getvar slot-unbootable:b 2>&1 | grep "slot-unbootable"
echo ""

echo "ℹ️  Understanding the values:"
echo "   - retry-count: Remaining boot attempts (default 7)"
echo "   - successful: yes = stable boot, no = needs verification"
echo "   - unbootable: yes = won't boot, no = bootable"
echo ""
echo "🔄 Auto-rollback triggers when:"
echo "   - retry-count reaches 0 (after 7 failed boots)"
echo "   - Bootloader auto-switches to other slot"
