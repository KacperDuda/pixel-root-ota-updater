#!/bin/bash

# ================= KONFIGURACJA =================
# Ścieżka do pliku avbtool.py
AVBTOOL_PATH="./avbtool.py"

# Używamy python3 do wywołania (omija problem Permission denied)
AVBTOOL="python3 $AVBTOOL_PATH"

# Twój klucz prywatny
KEY_NAME="custom_key.pem"
ALGO="SHA256_RSA4096"
ROLLBACK_INDEX="1759622400"

# Pliki we/wy
INPUT_ZIP="$1"
OUTPUT_ZIP="signed_images_update.zip"
WORK_DIR="./temp_work_dir"
PKMD="$WORK_DIR/pkmd.bin"

# Kolory
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}=== REPACKER & SIGNER (Pixel 10 Logic) ===${NC}"

# ================= FUNKCJE POMOCNICZE =================

check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ BŁĄD: $1${NC}"
        # Nie usuwamy WORK_DIR przy błędzie, żebyś mógł zobaczyć co poszło nie tak
        exit 1
    fi
}

trim_padding() {
    local FILE=$1
    local ORIG_SIZE=$2
    local TRIM_AMOUNT=$3 
    
    local CURR_SIZE=$(stat -c %s "$FILE")

    if [ "$CURR_SIZE" -eq "$ORIG_SIZE" ]; then
        echo "✂️  Przycinanie $TRIM_AMOUNT bajtów paddingu w $(basename $FILE)..."
        local NEW_SIZE=$((CURR_SIZE - TRIM_AMOUNT))
        truncate -s "$NEW_SIZE" "$FILE"
    else
        local SPACE_AVAILABLE=$((ORIG_SIZE - CURR_SIZE))
        if [ "$SPACE_AVAILABLE" -lt "$TRIM_AMOUNT" ]; then
             echo "✂️  Docinanie paddingu w $(basename $FILE)..."
             local NEW_SIZE=$((ORIG_SIZE - TRIM_AMOUNT))
             truncate -s "$NEW_SIZE" "$FILE"
        fi
    fi
}

# ================= GŁÓWNA LOGIKA =================

# 1. Weryfikacja wstępna
if [ -z "$INPUT_ZIP" ]; then
    echo "Użycie: ./repack_signer.sh <images.zip>"
    exit 1
fi

if [ ! -f "$KEY_NAME" ]; then
    echo -e "${RED}Błąd: Nie znaleziono klucza $KEY_NAME${NC}"
    exit 1
fi

if [ ! -f "$AVBTOOL_PATH" ]; then
    echo -e "${RED}Błąd: Nie znaleziono narzędzia $AVBTOOL_PATH${NC}"
    exit 1
fi

# 2. Rozpakowywanie
echo -e "\n${YELLOW}[1/5] Rozpakowywanie $INPUT_ZIP...${NC}"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
unzip -q "$INPUT_ZIP" -d "$WORK_DIR"
check_error "Rozpakowywanie zipa"

# 3. Generowanie PKMD
echo -e "\n${YELLOW}[2/5] Generowanie pkmd.bin...${NC}"
$AVBTOOL extract_public_key --key "$KEY_NAME" --output "$PKMD"
check_error "Generowanie pkmd.bin"


# 4. Przetwarzanie obrazów
echo -e "\n${YELLOW}[3/5] Podpisywanie obrazów...${NC}"

process_image() {
    local TYPE=$1 
    local FILE_NAME=$2
    local PART_NAME=$3
    local IS_CHAIN=$4 

    local FILE_PATH="$WORK_DIR/$FILE_NAME"
    
    if [ ! -f "$FILE_PATH" ]; then
        return
    fi

    local ORIGINAL_SIZE=$(stat -c %s "$FILE_PATH")
    echo "Processing $FILE_NAME ($TYPE)..."

    # Kontenery vbmeta (tylko resign)
    if [ "$TYPE" == "VBMETA_CONTAINER" ]; then
        local TEMP_NAME="$WORK_DIR/temp_$FILE_NAME"
        $AVBTOOL make_vbmeta_image \
            --output "$TEMP_NAME" \
            --key "$KEY_NAME" \
            --algorithm "$ALGO" \
            --rollback_index "$ROLLBACK_INDEX" \
            --include_descriptors_from_image "$FILE_PATH" \
            --padding_size 4096
        mv "$TEMP_NAME" "$FILE_PATH"
        return
    fi

    # Hash i Hashtree - czyścimy stopkę
    $AVBTOOL erase_footer --image "$FILE_PATH" > /dev/null 2>&1

    if [ "$TYPE" == "HASHTREE" ]; then
        # Logika dla vendor_dlkm (duży trim 512KB, brak FEC)
        trim_padding "$FILE_PATH" "$ORIGINAL_SIZE" 524288
        
        $AVBTOOL add_hashtree_footer \
            --image "$FILE_PATH" \
            --partition_name "$PART_NAME" \
            --partition_size "$ORIGINAL_SIZE" \
            --key "$KEY_NAME" \
            --algorithm "$ALGO" \
            --do_not_generate_fec \
            --hash_algorithm sha256
            
    elif [ "$TYPE" == "HASH" ]; then
        # Logika dla boot, dtbo itp (mały trim 68KB)
        trim_padding "$FILE_PATH" "$ORIGINAL_SIZE" 69632
        
        local CMD="$AVBTOOL add_hash_footer --image $FILE_PATH --partition_name $PART_NAME --partition_size $ORIGINAL_SIZE --key $KEY_NAME --algorithm $ALGO"
        if [ "$IS_CHAIN" == "yes" ]; then CMD="$CMD --rollback_index $ROLLBACK_INDEX"; fi
        $CMD
    fi
    check_error "Błąd przy pliku $FILE_NAME"
}

# A. Chain Partitions
process_image "HASH" "boot.img" "boot" "yes"
process_image "HASH" "init_boot.img" "init_boot" "yes"

# B. Vbmeta Containers
process_image "VBMETA_CONTAINER" "vbmeta_system.img" "" ""
process_image "VBMETA_CONTAINER" "vbmeta_vendor.img" "" ""

# C. Standard Hash Images
process_image "HASH" "vendor_boot.img" "vendor_boot" "no"
process_image "HASH" "vendor_kernel_boot.img" "vendor_kernel_boot" "no"
process_image "HASH" "dtbo.img" "dtbo" "no"
process_image "HASH" "pvmfw.img" "pvmfw" "no"

# D. Hashtree Images
process_image "HASHTREE" "vendor_dlkm.img" "vendor_dlkm" ""


# 5. Generowanie Głównego Vbmeta
echo -e "\n${YELLOW}[4/5] Generowanie głównego vbmeta.img...${NC}"

VBMETA_CMD="$AVBTOOL make_vbmeta_image \
    --output $WORK_DIR/vbmeta.img \
    --key $KEY_NAME \
    --algorithm $ALGO \
    --rollback_index $ROLLBACK_INDEX \
    --padding_size 4096"

# Chain
if [ -f "$WORK_DIR/vbmeta_system.img" ]; then VBMETA_CMD="$VBMETA_CMD --chain_partition vbmeta_system:1:$PKMD"; fi
if [ -f "$WORK_DIR/boot.img" ]; then VBMETA_CMD="$VBMETA_CMD --chain_partition boot:2:$PKMD"; fi
if [ -f "$WORK_DIR/vbmeta_vendor.img" ]; then VBMETA_CMD="$VBMETA_CMD --chain_partition vbmeta_vendor:3:$PKMD"; fi
if [ -f "$WORK_DIR/init_boot.img" ]; then VBMETA_CMD="$VBMETA_CMD --chain_partition init_boot:4:$PKMD"; fi

# Include
for IMG in vendor_boot.img vendor_kernel_boot.img dtbo.img pvmfw.img vendor_dlkm.img; do
    if [ -f "$WORK_DIR/$IMG" ]; then
        VBMETA_CMD="$VBMETA_CMD --include_descriptors_from_image $WORK_DIR/$IMG"
    fi
done

echo "Wykonywanie: $VBMETA_CMD"
$VBMETA_CMD
check_error "Generowanie vbmeta.img"


# 6. Pakowanie
echo -e "\n${YELLOW}[5/5] Pakowanie do $OUTPUT_ZIP...${NC}"
cd "$WORK_DIR"
rm -f pkmd.bin temp_*
zip -r -q "../$OUTPUT_ZIP" .
cd ..
rm -rf "$WORK_DIR"

echo -e "\n${GREEN}✅ SUKCES! Plik gotowy: $OUTPUT_ZIP${NC}"
echo "Wgraj komendą: fastboot update $OUTPUT_ZIP"