#!/bin/bash
# Refactored Pixel Flasher - Mimics flash-all.sh but SAFE (No Wipe)
set -e

WORK_AREA="output/work_area"
FACTORY_ZIP=$(find output -maxdepth 1 -name "*-factory-*.zip" ! -name "ksu_patched*" | head -n 1)

echo "=== PIXEL REPAIR FLASHER (Safe Mode) ==="
echo "   Mimics flash-all.sh logic:"
echo "   1. Flash Bootloader"
echo "   2. Flash Radio"
echo "   3. Update System (Preserving User Data)"
echo ""

if [ -z "$FACTORY_ZIP" ]; then
    echo "❌ Factory zip not found in output/"
    exit 1
fi

echo "📦 Found factory zip: $FACTORY_ZIP"
echo "📂 Work area: $WORK_AREA"
echo ""
echo "⚠️  This will flash potentially dangerous partitions (bootloader, radio)."
echo "   Ensure you are in FASTBOOT mode."
echo ""
echo "Press ENTER to continue or CTRL+C to cancel..."
read

# 1. Extract Bootloader & Radio if needed
echo "🔍 Checking for bootloader/radio..."
unzip -j -n "$FACTORY_ZIP" "*/bootloader*.img" "*/radio*.img" -d "$WORK_AREA" > /dev/null 2>&1 || sudo unzip -j -n "$FACTORY_ZIP" "*/bootloader*.img" "*/radio*.img" -d "$WORK_AREA" > /dev/null 2>&1 || true

BOOTLOADER_IMG=$(find "$WORK_AREA" -name "bootloader-*.img" | head -n 1)
RADIO_IMG=$(find "$WORK_AREA" -name "radio-*.img" | head -n 1)

if [ -z "$BOOTLOADER_IMG" ]; then echo "❌ Bootloader image not found!"; exit 1; fi
if [ -z "$RADIO_IMG" ]; then echo "❌ Radio image not found!"; exit 1; fi

# 2. Flash Bootloader
echo "⚡ Flashing Bootloader: $(basename "$BOOTLOADER_IMG")"
fastboot flash bootloader "$BOOTLOADER_IMG"
echo "   Rebooting bootloader..."
fastboot reboot-bootloader
sleep 5

# 3. Flash Radio
echo "⚡ Flashing Radio: $(basename "$RADIO_IMG")"
fastboot flash radio "$RADIO_IMG"
echo "   Rebooting bootloader..."
fastboot reboot-bootloader
sleep 5

# 4. Create Update Package
echo "📦 Creating update package (no wipe)..."
UPDATE_ZIP="update_safe.zip"
rm -f "$UPDATE_ZIP"

# We need everything from WORK_AREA except userdata
# Also android-info.txt might be in WORK_AREA
# The previous script modified android-info.txt to remove strict version checks.
# If we want to be "like flash-all", we should KEEP strict checks usually?
# But user has newer bootloader possibly? No, we just flashed it. So strict checks are fine!
# EXCEPT if user is downgraded.
# Let's keep the user's logic of relaxing checks just in case, or stick to strict?
# User said "Can't you be simple?". Simple = use what's there.
# But if it fails due to version mismatch, that's annoying. 
# However, we just flashed the bootloader FROM the zip, so version MUST match.
# So we can use the original android-info.txt.

pushd "$WORK_AREA" > /dev/null
# Use original android-info (it's in the dir)
# Zip everything except userdata
zip -0 -j "../../$UPDATE_ZIP" * -x "userdata*.img" -x "userdata_exp.ai.img" -x "bootloader*.img" -x "radio*.img"
popd > /dev/null

echo "✅ Package created: $UPDATE_ZIP"

# 5. Fastboot Update
echo "🚀 Flashing system (Update)..."
# --skip-reboot allows user to see output or flash KSU after
echo "   (User data will be preserved)"
fastboot update --skip-reboot "$UPDATE_ZIP"

echo ""
echo "=== DONE ==="
echo "If no errors above, you can now:"
echo "1. 'fastboot reboot' to system"
echo "2. OR flash KSU/Magisk if needed."
