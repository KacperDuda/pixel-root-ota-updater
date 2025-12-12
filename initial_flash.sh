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

# 1. Find the# 3. Detect Firmware
ZIP_FILE=$(find "$OUTPUT_DIR" -maxdepth 1 -name "ksu_patched_*.zip" | head -n 1)

if [ -z "$ZIP_FILE" ]; then
    echo "No patched firmware found in $OUTPUT_DIR!"
    echo "Please run the builder first."
    exit 1
fi

FILENAME=$(basename "$ZIP_FILE")
BASENAME="${FILENAME%.*}"
EXTRACTED_DIR="$OUTPUT_DIR/$BASENAME"

echo "📁 Found Firmware: $ZIP_FILE"
if [ -d "$EXTRACTED_DIR" ]; then
    echo "📂 Found Extracted Images: $EXTRACTED_DIR"
else
    echo "⚠️  Extracted images directory not found: $EXTRACTED_DIR"
    # Fallback to output root just in case old build
    EXTRACTED_DIR="$OUTPUT_DIR"
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

# 6. Flash Selection & Execution
echo -e "${CYAN}--- READY TO FLASH ---${NC}"
echo "Target: $PRODUCT"

# Search for extracted images
INIT_BOOT_IMG=$(ls "$OUTPUT_DIR"/init_boot.img 2>/dev/null)
BOOT_IMG=$(ls "$OUTPUT_DIR"/boot.img 2>/dev/null)
AVB_KEY_BIN=$(ls "$OUTPUT_DIR"/avb_pkmd.bin 2>/dev/null)

# 6. Flash Strategy: Flash All Available Images
echo -e "\n${CYAN}--- FLASHING PROCESS ---${NC}"

# Helper function to flash if file exists
flash_if_exists() {
    local part=$1
    local file="$EXTRACTED_DIR/$1.img"
    if [ -f "$file" ]; then
        echo -e "Flashing ${GREEN}$part${NC}..."
        fastboot flash "$part" "$file"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Failed to flash $part${NC}"
            read -t 60 -p "Continue anyway? (y/N) " CONFIRM
            if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then exit 1; fi
        fi
    fi
}

# 6a. Flash Static Partitions (Bootloader Mode)
echo -e "${YELLOW}Phase 1: Static Partitions (Bootloader)${NC}"

# Priority: init_boot & boot (Rooted)
INIT_BOOT_IMG="$EXTRACTED_DIR/init_boot.img"
BOOT_IMG="$EXTRACTED_DIR/boot.img"
AVB_KEY_BIN="$EXTRACTED_DIR/avb_pkmd.bin"

# 6a. Flash AVB Key (Critical for Locking)
if [ -f "$AVB_KEY_BIN" ]; then
    echo -e "Found Custom AVB Key: ${YELLOW}$AVB_KEY_BIN${NC}"
    echo "This key is REQUIRED if you plan to LOCK the bootloader."
    
    if confirm_action "Flash Custom AVB Key (avb_custom_key)?" "N"; then
        echo -e "${GREEN}🚀 Flashing avb_custom_key...${NC}"
        
        # Erasing first improves reliability on some Pixels
        echo "Erasing old key..."
        fastboot erase avb_custom_key
        
        fastboot flash avb_custom_key "$AVB_KEY_BIN"
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Key Flash Failed!${NC}"
            # Don't exit, might still want to flash images for unlocked use
        else
            echo "Key flashed successfully."
        fi
    fi
    echo ""
fi

if [ -f "$INIT_BOOT_IMG" ]; then
    echo -e "Found patched: ${GREEN}init_boot.img${NC} (Root)"
    flash_if_exists "init_boot"
fi

# Flash other static images found in extraction
# Order matters less here, but usually:
flash_if_exists "boot"
flash_if_exists "vendor_boot"
flash_if_exists "dtbo"
flash_if_exists "pvmfw"
flash_if_exists "vbmeta"
flash_if_exists "vbmeta_system"
flash_if_exists "vbmeta_vendor"

# 6b. Flash Dynamic Partitions (FastbootD Mode)
# Check if dynamic partitions exist
SYSTEM_IMG="$EXTRACTED_DIR/system.img"
VENDOR_IMG="$EXTRACTED_DIR/vendor.img"

if [ -f "$SYSTEM_IMG" ] || [ -f "$VENDOR_IMG" ]; then
    echo -e "\n${YELLOW}Phase 2: Dynamic Partitions (System, Vendor, Product...)${NC}"
    echo "These partitions require Userspace Fastboot (FastbootD)."
    
    if confirm_action "Flash Dynamic Partitions? (Full OS Update)" "N"; then
        echo "Rebooting to FastbootD..."
        fastboot reboot fastboot
        echo "Waiting for FastbootD..."
        sleep 10
        
        # Verify we are in fastbootd?
        # fastboot getvar is-userspace should be yes
        
        flash_if_exists "system"
        flash_if_exists "system_ext"
        flash_if_exists "product"
        flash_if_exists "vendor"
        flash_if_exists "vendor_dlkm"
        flash_if_exists "system_dlkm"
        
        echo -e "${GREEN}Dynamic Partitions Flashed.${NC}"
        
        # Reboot back to bootloader for final checks or direct to system?
        # Usually direct to system is fine, but our script logic continues.
        # Let's stay in fastbootd or reboot?
        # If we reboot, we exit script flow.
        # But we haven't done "Post-Flash Action" (Locking check).
        # Locking verification logic expects us to ideally reboot to system.
        # So we can proceed.
    else
        echo "Skipping Dynamic Partitions."
    fi
fi

if [ ! -f "$INIT_BOOT_IMG" ] && [ ! -f "$BOOT_IMG" ]; then
    echo "No boot images found? Check output directory."
    exit 1
fi

echo -e "${GREEN}✅ Flashing Complete!${NC}"
echo "Waiting ${SLEEP_TIME}s..."
sleep $SLEEP_TIME

# 8. Post-Flash Action (Test vs Lock)
echo -e "${CYAN}--- POST-FLASH ACTION ---${NC}"
echo -e "You have two choices:"
echo -e "1. ${GREEN}REBOOT (Recommended)${NC} - Verify the system boots and works."
echo -e "2. ${RED}LOCK BOOTLOADER${NC} - Only do this if you have ALREADY verified a successful boot with this key."

echo -e "${YELLOW}Risk Warning:${NC} Locking without verifying boot can BRICK the device if the key is wrong."
echo -e "If this is your first time flashing this key/ROM, choose REBOOT."

echo -e "${CYAN}Choose Action:${NC}"
echo "  [R] Reboot to System (Default)"
echo "  [L] Lock Bootloader (Advanced)"
read -t 60 -p "Enter choice [R/L]: " ACTION
ACTION=${ACTION:-R} # Default to Reboot

if [[ "$ACTION" =~ ^[Ll]$ ]]; then
    # Locking Flow
    echo -e "${RED}🔒 You chose to LOCK the bootloader.${NC}"
    if confirm_action "CONFIRM: Have you already successfully booted this device with this AVB key?" "N"; then
        echo "Running: fastboot flashing lock"
        fastboot flashing lock
        echo -e "${CYAN}Please confirm on the device screen!${NC}"
        read -p "Press Enter after locking is done..."
        # Reboot after lock
        fastboot reboot
    else
        echo "Aborting lock for safety. Rebooting instead."
        fastboot reboot
    fi
else
    # Reboot Flow (Default)
    echo -e "Rebooting to System for verification..."
    echo -e "NOTE: You should see a YELLOW warning screen saying 'Your device is loading a different operating system'."
    echo -e "This is NORMAL and confirms your custom Key is working."
    fastboot reboot
fi

echo -e "${GREEN}Done.${NC}"
