#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=== PIXEL UNIVERSAL SAFETY FLASHER v5.0 ===${NC}"
echo -e "${YELLOW}Operating in PARANOID SAFETY MODE.${NC}"

OUTPUT_DIR="output"

ZIP_FILE=$(find "$OUTPUT_DIR" -name "ksu_patched_*.zip" | head -n 1)

if [ -z "$ZIP_FILE" ]; then
     ZIP_FILE=$(find "$OUTPUT_DIR" -name "image-*.zip" | head -n 1)
fi
if [ -z "$ZIP_FILE" ]; then
     ZIP_FILE=$(find "$OUTPUT_DIR" -name "frankel-ota-*.zip" | head -n 1)
fi

if [ -z "$ZIP_FILE" ]; then
    echo -e "${RED}❌ FATAL: No Image found in $OUTPUT_DIR!${NC}"
    exit 1
fi
echo -e "Target Image: ${CYAN}$ZIP_FILE${NC}"

if unzip -l "$ZIP_FILE" | grep -q "payload.bin"; then
    MODE="OTA"
    echo -e "Detected Type: ${GREEN}OTA IMAGE (Recovery Sideload)${NC}"
elif unzip -l "$ZIP_FILE" | grep -q "android-info.txt"; then
    MODE="FACTORY"
    echo -e "Detected Type: ${GREEN}FACTORY IMAGE (Fastboot Update)${NC}"
else
    echo -e "${RED}❌ FATAL: Unknown ZIP format. Cannot flash safely.${NC}"
    exit 1
fi

echo -e "\n${CYAN}--- PHASE 1: CONFIRMATION ---${NC}"
echo -e "You are about to flash: $ZIP_FILE"
echo -e "Mode: $MODE"
if [ "$MODE" == "FACTORY" ]; then
    echo -e "${RED}WARNING: This mode (Factory) will WIPE DATA (-w).${NC}"
else
    echo -e "${GREEN}Info: OTA Sideload preserves data (usually).${NC}"
fi

echo -e "\nType ${GREEN}YES${NC} (all caps) to continue:"
read -r CONFIRM
if [ "$CONFIRM" != "YES" ]; then
    echo "Aborting."
    exit 1
fi

echo -e "\n${CYAN}--- PHASE 2: PREPARATION & FLASH ---${NC}"

if [ "$MODE" == "OTA" ]; then
    echo -e "${YELLOW}INSTRUCTIONS FOR OTA SIDELOAD:${NC}"
    echo "1. Ensure device is in 'Recovery Mode'."
    echo "2. If you are in Fastboot, enter Recovery NOW."
    
    echo -ne "\nPress ENTER when device is in 'Apply update from ADB' mode..."
    read
    
    echo "Checking ADB connection..."
    ADB_STATUS=$(adb devices | grep -v "List" | grep -v "^$" | awk '{print $2}')
    if [[ "$ADB_STATUS" == "sideload" ]] || [[ "$ADB_STATUS" == "device" ]]; then
        echo -e "${GREEN}Device Connected via ADB ($ADB_STATUS).${NC}"
        echo "Starting Sideload..."
        adb sideload "$ZIP_FILE"
    else
        echo -e "${RED}❌ Device not found in ADB Sideload mode!${NC}"
        exit 1
    fi

elif [ "$MODE" == "FACTORY" ]; then
    echo -e "${YELLOW}INSTRUCTIONS FOR FACTORY FLASH (SAFE MODE):${NC}"
    echo "1. Ensure device is in 'Fastboot Mode' (Bootloader)."
    
    echo "Waiting for Fastboot device..."
    while ! fastboot devices | grep -iq "fastboot"; do sleep 1; done
    echo -e "${GREEN}Device Connected.${NC}"

    PRODUCT=$(fastboot getvar product 2>&1 | grep "product" | awk '{print $2}')
    if [ "$PRODUCT" != "frankel" ]; then
        echo -e "${RED}⛔ STOP: Wrong device or Crash Mode ($PRODUCT). Expected 'frankel'.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Identity Verified: $PRODUCT${NC}"

    echo -e "${YELLOW}Unpacking Firmware...${NC}"
    WORK_DIR="tmp_flash_extract"
    rm -rf "$WORK_DIR"
    mkdir -p "$WORK_DIR"
    
    unzip -o "$ZIP_FILE" -d "$WORK_DIR" > /dev/null
    
    NESTED_ZIP=$(find "$WORK_DIR" -name "image-*.zip" | head -n 1)
    if [ -n "$NESTED_ZIP" ]; then
        echo "Unpacking nested images..."
        unzip -o "$NESTED_ZIP" -d "$WORK_DIR" > /dev/null
    fi
    
    cd "$WORK_DIR" || exit 1
    
    echo -e "${CYAN}Starting Safe Flash Sequence...${NC}"
    echo -e "${RED}SKIPPING BOOTLOADER AND RADIO FLASH FOR SAFETY.${NC}"

    echo "Flashing static partitions..."
    for IMG in boot.img dtbo.img vbmeta.img vbmeta_system.img vbmeta_vendor.img vendor_boot.img init_boot.img; do
        if [ -f "$IMG" ]; then
            echo " - Flashing $IMG..."
            fastboot flash "${IMG%.*}" "$IMG"
        fi
    done
    
    echo -e "${YELLOW}Rebooting to FastbootD (Userspace) for generic partitions...${NC}"
    fastboot reboot fastboot
    
    echo "Waiting for FastbootD..."
    sleep 5
    while ! fastboot devices | grep -iq "fastboot"; do sleep 1; done
    
    echo "Flashing dynamic partitions..."
    for IMG in system.img system_ext.img product.img vendor.img vendor_dlkm.img system_dlkm.img; do
         if [ -f "$IMG" ]; then
            echo " - Flashing $IMG..."
            fastboot flash "${IMG%.*}" "$IMG"
        fi
    done

    echo -e "\n${YELLOW}Do you want to WIPE USER DATA? (Recommended for clean flash)${NC}"
    echo "Type YES to wipe, any other key to keep data:"
    read -r DO_WIPE
    if [ "$DO_WIPE" == "YES" ]; then
        echo "Wiping User Data..."
        fastboot erase userdata
        fastboot erase metadata
    else
        echo "Skipping Data Wipe."
    fi

    echo "Rebooting to Bootloader..."
    fastboot reboot bootloader
    
    cd ..
    rm -rf "$WORK_DIR"

if [ $? -ne 0 ]; then
    echo -e "\n${RED}❌ Flash Failed!${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ SUCCESS! Operation Complete.${NC}"

echo -e "\n${CYAN}--- PHASE 4: POST-FLASH SETUP ---${NC}"
echo -e "${YELLOW}Do you want to install the Wireless Updater (Custota) now?${NC}"
echo "1. The device will reboot."
echo "2. You must complete Android Setup (skip Wi-Fi/Account)."
echo "3. You must keep USB Debugging enabled."

echo -e "\nType ${GREEN}Y${NC} to wait for boot and install, or ENTER to skip:"
read -r INSTALL_OTA

if [[ "$INSTALL_OTA" == "Y" || "$INSTALL_OTA" == "y" ]]; then
    echo -e "\n${CYAN}Waiting for device to boot into Android...${NC}"
    echo "(This takes 1-2 minutes. Stay plugged in.)"
    
    while ! adb devices | grep -w "device" > /dev/null; do
        sleep 3
    done
    
    echo -e "${GREEN}Device Detected!${NC}"
    echo "Running Wireless Setup..."
    
    echo "Downloading Custota..."
    CUSTOTA_APK="Custota.apk"
    curl -L -o "$CUSTOTA_APK" https://github.com/chenxiaolong/Custota/releases/latest/download/app-release.apk
    
    if [ -f "$CUSTOTA_APK" ]; then
        echo "Installing..."
        adb install "$CUSTOTA_APK"
        rm "$CUSTOTA_APK"
        
        echo "---------------------------------------------------"
        echo "✅ Custota Installed."
        echo ""
        echo "CONFIGURATION STEPS:"
        echo "1. Open Custota on phone."
        echo "2. Grant SuperUser (Root) rights when asked."
        echo "3. Go to Settings -> OTA URL."
        echo "4. Enter your server URL (e.g., http://your-ip:8000/builds_index.json)"
        echo "---------------------------------------------------"
    else
        echo -e "${RED}Failed to download Custota.apk${NC}"
    fi
else
    echo "Skipping Wireless Setup."
fi

echo -e "${GREEN}All Done. Enjoy your Pixel 10.${NC}"
