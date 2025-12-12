#!/bin/bash

# Configuration
OUTPUT_DIR="output"
TIMEOUT_SEC=30
SLEEP_TIME=10

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== Pixel Initial Flash Helper ===${NC}"

# 1. Find the patched file
ZIP_FILE=$(ls -t "$OUTPUT_DIR"/ksu_patched_*.zip 2>/dev/null | head -n 1)

if [ -z "$ZIP_FILE" ]; then
    echo -e "${RED}❌ Error: No patched file found in $OUTPUT_DIR!${NC}"
    echo "Please run the builder first."
    exit 1
fi

echo -e "${GREEN}📁 Found Firmware: $ZIP_FILE${NC}"

# Check for ADB/Fastboot
if ! command -v fastboot &> /dev/null; then
    echo -e "${RED}❌ Error: fastboot tool not found!${NC}"
    exit 1
fi

# Function for Timed Confirmation
confirm_action() {
    local prompt="$1"
    local default_action="${2:-N}" # Default is No
    local timeout="$TIMEOUT_SEC"
    
    echo -e "${YELLOW}$prompt${NC}"
    echo -n "Type Y/N (Default: $default_action, Timeout: ${timeout}s): "
    
    read -t "$timeout" -r response
    
    # If timed out
    if [ $? -gt 128 ]; then
        echo ""
        echo -e "${RED}⏰ Timeout reached. Defaulting to $default_action.${NC}"
        response="$default_action"
    fi
    
    # If empty (user just pressed enter)
    if [ -z "$response" ]; then
        response="$default_action"
    fi
    
    echo ""
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        return 0 # True (Yes)
    else
        return 1 # False (No)
    fi
}

# 2. Check Device Connection (ADB)
echo "Checking ADB devices..."
ADB_STATUS=$(adb get-state 2>/dev/null)

if [ "$ADB_STATUS" == "device" ]; then
    echo -e "${GREEN}✅ Device connected via ADB.${NC}"
    echo "Rebooting to Bootloader..."
    adb reboot bootloader
    echo "Waiting ${SLEEP_TIME}s..."
    sleep $SLEEP_TIME
else
    echo -e "${YELLOW}⚠️  Device not detected in ADB. Assuming it might be in Fastboot mode...${NC}"
fi

# 3. Check Fastboot Connection
FASTBOOT_DEVICE=$(fastboot devices | head -n 1 | awk '{print $1}')
if [ -z "$FASTBOOT_DEVICE" ]; then
    echo -e "${RED}❌ Error: No device detected in Fastboot mode.${NC}"
    echo "Please connect your device and boot into Bootloader (Power + Volume Down)."
    exit 1
fi
echo -e "${GREEN}✅ Device detected in Fastboot: $FASTBOOT_DEVICE${NC}"

# 4. Verify Model
echo "Verifying Device Model..."
PRODUCT=$(fastboot getvar product 2>&1 | grep "product:" | awk '{print $2}')

# Extract codename from filename (e.g., frankel inside ksu_patched_frankel...)
FILENAME_CODENAME=$(basename "$ZIP_FILE" | grep -oP "(?<=ksu_patched_)[a-z]+")

if [[ "$ZIP_FILE" == *"$PRODUCT"* ]]; then
    echo -e "${GREEN}✅ Model Match: Device ($PRODUCT) matches File ($FILENAME_CODENAME)${NC}"
else
    echo -e "${RED}❌ Mismatch Warning!${NC}"
    echo -e "Device reports: ${YELLOW}$PRODUCT${NC}"
    echo -e "File appears to be for: ${YELLOW}$FILENAME_CODENAME${NC}"
    
    if ! confirm_action "⚠️  RISK OF BRICK. Models do not match. Continue anyway?" "N"; then
        echo "Aborting."
        exit 1
    fi
fi

# 5. Check Bootloader Status
UNLOCKED=$(fastboot getvar unlocked 2>&1 | grep "unlocked:" | awk '{print $2}')
echo "Bootloader Status: $UNLOCKED"

if [ "$UNLOCKED" == "no" ]; then
    echo -e "${RED}🔒 Bootloader is LOCKED.${NC}"
    echo -e "${YELLOW}WARNING: Unlocking the bootloader WIPES ALL DATA.${NC}"
    
    if confirm_action "Do you want to UNLOCK the bootloader now?" "N"; then
        echo "Running: fastboot flashing unlock"
        fastboot flashing unlock
        echo -e "${CYAN}Please confirm on the device screen!${NC}"
        read -p "Press Enter after unlocking is done on device..."
        
        # Verify again
        sleep 5
        UNLOCKED_CHECK=$(fastboot getvar unlocked 2>&1 | grep "unlocked:" | awk '{print $2}')
        if [ "$UNLOCKED_CHECK" == "no" ]; then
             echo -e "${RED}❌ Unlock failed or cancelled.${NC}"
             exit 1
        fi
    else
        echo -e "${RED}Cannot proceed with locked bootloader. Aborting.${NC}"
        exit 1
    fi
fi

# 6. Flash Warning
echo -e "${CYAN}--- READY TO FLASH ---${NC}"
echo "File: $ZIP_FILE"
echo "Target: $PRODUCT"

if ! confirm_action "Start Flashing (fastboot update)? This process modifies your boot partition." "N"; then
    echo "Aborted by user."
    exit 0
fi

# 7. Flash
echo -e "${GREEN}🚀 Flashing started...${NC}"
fastboot update "$ZIP_FILE" --skip-reboot

FLASH_STATUS=$?
if [ $FLASH_STATUS -ne 0 ]; then
    echo -e "${RED}❌ Flashing Failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Flashing Complete!${NC}"
echo "Waiting ${SLEEP_TIME}s..."
sleep $SLEEP_TIME

# 8. Lock Bootloader Prompt (Only if custom AVB key is involved)
# Note: For custom keys, locking is safe ONLY if the custom key is verified. 
# Since we just verified and flashed, it generally should be fine IF the user flashed the avb_custom_key before (which avbroot ota usually handles or requires separate step).
# WARNING: avbroot ota update zip does NOT flash the AVB Public Key to the device's vbmeta public key partition usually?
# Actually, 'fastboot update' updates the images. 
# BUT: To lock bootloader with custom keys, you must have flashed the custom public key to the device first!
# Since this script assumes 'fastboot update', checking if we need to warn about AVB key.

echo -e "${YELLOW}🔒 Bootloader Locking Check${NC}"
echo -e "IMPORTANT: You should ONLY lock the bootloader if you have accurately flashed the AVB Custom Key previously."
echo -e "If you lock without the correct key, you will BRICK the device."

if confirm_action "Do you want to LOCK the bootloader now?" "N"; then
    echo "Running: fastboot flashing lock"
    fastboot flashing lock
    echo -e "${CYAN}Please confirm on the device screen!${NC}"
    read -p "Press Enter after locking is done..."
else
    echo "Skipping Lock. Your bootloader remains unlocked."
fi

# 9. Final Reboot
echo "Rebooting System..."
fastboot reboot
echo -e "${GREEN}Done.${NC}"
