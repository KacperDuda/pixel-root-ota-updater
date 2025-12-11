#!/bin/bash
# Flash KernelSU to Pixel (TEST MODE - Unlocked Bootloader)
set -e

AVB_PUBLIC_KEY="cyber_rsa4096_public.bin"
INIT_BOOT_DIR="output"

echo "=== PIXEL KERNELSU FLASHER (TEST MODE) ==="
echo ""
echo "🔓 This script will:"
echo "   ✅ Flash AVB custom public key"
echo "   ✅ Flash init_boot_a (KernelSU)"
echo "   ✅ Flash init_boot_b (KernelSU)"
echo "   ✅ Reboot with UNLOCKED bootloader"
echo ""
echo "⚠️  Requirements:"
echo "   - Bootloader MUST be unlocked"
echo "   - Backup recommended!"
echo ""
echo "Press CTRL+C to cancel, Enter to continue..."
read

# Check if AVB key exists
if [ ! -f "$AVB_PUBLIC_KEY" ]; then
    echo "❌ AVB public key not found: $AVB_PUBLIC_KEY"
    echo "   Run: ./generate_avb_key.sh first"
    exit 1
fi

# Find patched init_boot
INIT_BOOT=$(find "$INIT_BOOT_DIR" -name "init_boot_ksu_*.img" -o -name "init_boot.img" | head -1)

if [ -z "$INIT_BOOT" ]; then
    echo "❌ Patched init_boot not found in $INIT_BOOT_DIR"
    echo "   Build it first with:"
    echo "   docker run ... pixel_builder --raw-output"
    exit 1
fi

echo "✅ Found patched init_boot: $INIT_BOOT"
echo ""

# Check fastboot
if ! command -v fastboot &> /dev/null; then
    echo "❌ fastboot not found in PATH"
    exit 1
fi

# Check device connection
echo "🔍 Checking device connection..."
if adb devices | grep -q "device$"; then
    echo "📱 Device connected via ADB"
    echo "   Rebooting to bootloader..."
    adb reboot bootloader
    sleep 10
elif ! fastboot devices | grep -q "fastboot"; then
    echo "❌ No device found!"
    echo "   Connect phone and enable USB debugging"
    echo "   Or boot to bootloader: Power + Vol Down"
    exit 1
fi

echo "✅ Device in fastboot mode"
echo ""

# Verify bootloader is unlocked
echo "🔓 Verifying bootloader status..."
BL_STATUS=$(fastboot getvar unlocked 2>&1 | grep "unlocked:" | awk '{print $2}')

if [ "$BL_STATUS" != "yes" ]; then
    echo "❌ Bootloader is LOCKED!"
    echo "   This script requires unlocked bootloader"
    echo "   Unlock: fastboot flashing unlock (WIPES DATA!)"
    exit 1
fi

echo "✅ Bootloader unlocked - safe to flash"
echo ""

# Detect current active slot
echo "🔍 Detecting active slot..."
ACTIVE_SLOT=$(fastboot getvar current-slot 2>&1 | grep "current-slot:" | awk '{print $2}')

if [ -z "$ACTIVE_SLOT" ]; then
    echo "⚠️  Could not detect active slot, defaulting to flash both"
    FLASH_MODE="both"
else
    echo "✅ Active slot: $ACTIVE_SLOT"
    
    if [ "$ACTIVE_SLOT" = "a" ]; then
        INACTIVE_SLOT="b"
    else
        INACTIVE_SLOT="a"
    fi
    
    echo "   Inactive slot: $INACTIVE_SLOT"
    echo ""
    echo "📋 Flash options:"
    echo "   1) Flash ONLY inactive slot ($INACTIVE_SLOT) - RECOMMENDED for testing"
    echo "      → Faster, safer (active slot untouched)"
    echo "      → Auto-rollback if boot fails"
    echo ""
    echo "   2) Flash BOTH slots (a + b)"
    echo "      → Slower, but consistent across updates"
    echo "      → No rollback to stock"
    echo ""
    echo "Choose (1=inactive only, 2=both): "
    read -r CHOICE
    
    case $CHOICE in
        1)
            FLASH_MODE="inactive"
            echo "✅ Will flash ONLY slot $INACTIVE_SLOT"
            ;;
        2)
            FLASH_MODE="both"
            echo "✅ Will flash BOTH slots"
            ;;
        *)
            echo "Invalid choice, defaulting to inactive only"
            FLASH_MODE="inactive"
            ;;
    esac
fi

echo ""

# Flash sequence
echo "=== FLASH SEQUENCE START ==="
echo ""

# 1. Flash AVB custom key
echo "🔑 Step 1: Flashing AVB custom public key..."
fastboot flash avb_custom_key "$AVB_PUBLIC_KEY"
echo "   ✅ AVB key flashed"
echo ""

# 2. Flash init_boot based on mode
if [ "$FLASH_MODE" = "inactive" ]; then
    echo "📦 Step 2: Flashing init_boot_$INACTIVE_SLOT (KernelSU - inactive slot)..."
    fastboot flash init_boot_$INACTIVE_SLOT "$INIT_BOOT"
    echo "   ✅ init_boot_$INACTIVE_SLOT flashed"
    echo ""
    
    echo "🔄 Step 3: Setting slot $INACTIVE_SLOT as active..."
    fastboot set_active $INACTIVE_SLOT
    echo "   ✅ Active slot changed: $ACTIVE_SLOT → $INACTIVE_SLOT"
else
    echo "📦 Step 2/3: Flashing init_boot_a (KernelSU)..."
    fastboot flash init_boot_a "$INIT_BOOT"
    echo "   ✅ init_boot_a flashed"
    echo ""
    
    echo "📦 Step 3/3: Flashing init_boot_b (KernelSU)..."
    fastboot flash init_boot_b "$INIT_BOOT"
    echo "   ✅ init_boot_b flashed"
fi

echo ""
echo "=== FLASH COMPLETE ==="
echo ""
echo "✅ All partitions flashed successfully!"
echo ""

if [ "$FLASH_MODE" = "inactive" ]; then
    echo "📋 What was flashed:"
    echo "   ✅ AVB custom key    → $AVB_PUBLIC_KEY"
    echo "   ✅ init_boot_$INACTIVE_SLOT     → KernelSU (NEW active slot)"
    echo "   ℹ️  init_boot_$ACTIVE_SLOT     → Stock (backup rollback)"
    echo ""
    echo "🛡️  SAFETY:"
    echo "   Your OLD slot ($ACTIVE_SLOT) is untouched with stock boot"
    echo "   If KernelSU fails → phone auto-rollback to slot $ACTIVE_SLOT"
else
    echo "📋 What was flashed:"
    echo "   ✅ AVB custom key    → $AVB_PUBLIC_KEY"
    echo "   ✅ init_boot_a       → KernelSU (slot A)"
    echo "   ✅ init_boot_b       → KernelSU (slot B)"
    echo ""
    echo "ℹ️  Both slots now have KernelSU"
fi
echo ""
echo "🚀 Rebooting phone (unlocked bootloader)..."
fastboot reboot

echo ""
echo "✅ Done! Phone is booting with KernelSU"
echo ""
echo "📱 Next steps:"
echo "   1. Wait for boot (~1 minute)"
echo "   2. Install KernelSU Manager app"
echo "   3. Test root access"
echo "   4. Check SafetyNet (will likely fail - expected)"
echo ""
echo "🔒 To lock bootloader later (AFTER testing!):"
echo "   Create separate script or do manually"
echo ""
echo "⚠️  Keep OEM unlock ENABLED in Developer Settings!"

