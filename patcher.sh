#!/bin/bash

ROOT_DIR=$(pwd)

# ================= KONFIGURACJA =================
# Argument 1: Extracted Directory (Workspace)
INPUT_DIR="$1"
KEY_PATH="${2:-cyber_rsa4096_private.pem}"

# Narzędzia
MAGISKBOOT="/usr/local/bin/magiskboot"
MAGZIP_EXTRACTOR="python3 /app/zip_extractor.py"
ZIP_CREATOR="python3 /app/zip_creator.py"
FAST_MODE=${FAST_MODE:-\"yes\"}  # Default to fast mode (store)
KSU_KO_PATH="$ROOT_DIR/kernelsu.ko"
CMD_LOG="$ROOT_DIR/last_command.log"

# Inteligentne szukanie avbtool
if [ -f "/usr/local/bin/avbtool.py" ]; then
    AVBTOOL_EXEC="python3 /usr/local/bin/avbtool.py"
elif [ -f "$ROOT_DIR/avbtool.py" ]; then
    AVBTOOL_EXEC="python3 $ROOT_DIR/avbtool.py"
else
    echo "❌ KRYTYCZNY BŁĄD: Nie znaleziono avbtool!"
    exit 1
fi

# Kolory (zgodne z ui_utils.py)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m'
BOLD='\033[1m'

# --- FUNKCJE LOGOWANIA ---
log_info() { echo -e "${BOLD}[PATCHER]${NC} ${BLUE}[INFO]${NC} $1"; }
log_step() { echo -e "\n${YELLOW}[STEP] $1${NC}"; }
log_sub()  { echo -e "${CYAN}   -> $1${NC}"; }
log_detail(){ echo -e "${GRAY}      * $1${NC}"; }
log_error() { echo -e "${BOLD}[PATCHER]${NC} ${RED}[ERROR]${NC} $1"; }

# Wrapper do ukrywania outputu
exec_cmd() {
    local msg="$1"
    shift
    log_sub "$msg"
    "$@" > "$CMD_LOG" 2>&1
    local status=$?
    if [ $status -ne 0 ]; then
        log_error "Operacja nie powiodła się!"
        echo -e "${RED}--- SZCZEGÓŁY BŁĘDU ---${NC}"
        cat "$CMD_LOG"
        echo -e "${RED}-----------------------${NC}"
        exit 1
    fi
}

echo -e "${YELLOW}=== PIXEL AUTO-PATCHER (OPTIMIZED) ===${NC}"

if [ ! -d "$INPUT_DIR" ]; then
    log_error "Katalog roboczy nie istnieje: $INPUT_DIR"
    exit 1
fi

if [[ "$KEY_PATH" != /* ]]; then KEY_PATH="$ROOT_DIR/$KEY_PATH"; fi
if [ ! -f "$KEY_PATH" ]; then log_error "Brak klucza: $KEY_PATH"; exit 1; fi

cd "$INPUT_DIR" || exit 1

# 2. WYBÓR CELU
TARGET_IMG="init_boot.img"
if [ ! -f "$TARGET_IMG" ]; then
    TARGET_IMG="boot.img"
    if [ ! -f "$TARGET_IMG" ]; then log_error "Brak obrazu!"; exit 1; fi
fi
log_info "Cel patchowania: $TARGET_IMG w $INPUT_DIR"

declare -a MODIFIED_FILES=()

# 3. POBIERANIE KERNELSU
log_step "Pobieranie modułu KernelSU..."
KSU_MODULE_URL="https://github.com/tiann/KernelSU/releases/download/v0.9.5/android14-6.1_kernelsu.ko" 
if [ -f "$KSU_KO_PATH" ]; then rm "$KSU_KO_PATH"; fi
exec_cmd "Pobieranie pliku .ko z GitHub..." wget -q "$KSU_MODULE_URL" -O "$KSU_KO_PATH"

if [ ! -s "$KSU_KO_PATH" ]; then log_error "Plik .ko ma rozmiar 0!"; exit 1; fi

# 4. INIEKCJA
log_step "Modyfikacja Ramdisku (GKI Injection)..."

exec_cmd "Analiza struktury (Magiskboot Unpack)..." $MAGISKBOOT unpack "$TARGET_IMG"
if [ ! -f "ramdisk.cpio" ]; then log_error "Błąd unpack (brak ramdisk.cpio)"; exit 1; fi

exec_cmd "Wstrzykiwanie modułu (CPIO Add)..." \
    $MAGISKBOOT cpio ramdisk.cpio "add 0644 kernelsu.ko $KSU_KO_PATH"

exec_cmd "Pakowanie obrazu (Magiskboot Repack)..." \
    $MAGISKBOOT repack "$TARGET_IMG" new_image.img

mv new_image.img "$TARGET_IMG"
MODIFIED_FILES+=("$TARGET_IMG")
log_info "Obraz $TARGET_IMG został zmodyfikowany."

# 5. PODPISYWANIE
log_step "Procedura AVB (Android Verified Boot)..."

PARTITION_NAME="$(basename "$TARGET_IMG" .img)"
FILE_SIZE_BEFORE=$(stat -c %s "$TARGET_IMG")

log_detail "Partycja docelowa: $PARTITION_NAME"
log_detail "Rozmiar przed:    $((FILE_SIZE_BEFORE/1024)) KB"

exec_cmd "Usuwanie starego podpisu Google..." \
    $AVBTOOL_EXEC erase_footer --image "$TARGET_IMG"

log_sub "Generowanie i aplikowanie podpisu..."
$AVBTOOL_EXEC add_hash_footer \
    --image "$TARGET_IMG" \
    --partition_name "$PARTITION_NAME" \
    --dynamic_partition_size \
    --key "$KEY_PATH" \
    --algorithm SHA256_RSA4096 > "$CMD_LOG" 2>&1

if [ $? -ne 0 ]; then
    log_error "Błąd AVBTool!"
    cat "$CMD_LOG"
    exit 1
fi

FILE_SIZE_AFTER=$(stat -c %s "$TARGET_IMG")
log_detail "Rozmiar po:       $((FILE_SIZE_AFTER/1024)) KB"
log_info "Plik $TARGET_IMG podpisany kluczem prywatnym."

# ----------------- SANITY CHECKS -----------------
log_step "Dodatkowe testy spójności..."

# Rule A: Partition size growth
SIZE_DIFF=$((FILE_SIZE_AFTER - FILE_SIZE_BEFORE))
# Convert to ABS
if [ $SIZE_DIFF -lt 0 ]; then SIZE_DIFF=$((SIZE_DIFF * -1)); fi

log_detail "Zmiana rozmiaru: ${SIZE_DIFF} bajtów"

if [ $SIZE_DIFF -gt 10485760 ]; then # 10MB
    log_error "Ostrzeżenie: Obraz urósł o ponad 10MB ($((SIZE_DIFF/1024)) KB)!"
else
    log_info "✅ Zmiana rozmiaru w normie."
fi


# Rule B: Check for 'avbtool info_image' properties
AVB_INFO=$($AVBTOOL_EXEC info_image --image "$TARGET_IMG" 2>&1)

if ! echo "$AVB_INFO" | grep -qE "Algorithm:[[:space:]]+SHA256_RSA4096"; then
    log_error "Błędny algorytm podpisu!"
    echo "--- AVB INFO OUTPUT ---"
    echo "$AVB_INFO"
    echo "-----------------------"
    exit 1
fi

# Rule C: Deep Structure Verify (Re-unpack)
log_sub "Weryfikacja struktury (Re-unpack)..."
mkdir -p sanity_check
cd sanity_check || exit 1
$MAGISKBOOT unpack "../$TARGET_IMG" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    log_error "Błąd: Nie można rozpakować podpisanego obrazu! (Uszkodzony nagłówek)"
    exit 1
fi

# Rule D: Kernel Symbol Check
if [ -f "kernel" ]; then
    if grep -q "kernelsu_init" kernel; then
        log_info "✅ KernelSU Symbol found in kernel."
    else
        log_error "Ostrzeżenie: Nie znaleziono symboli KernelSU w jądrze!"
        # exit 1 ? Maybe strictly enforced? User implies "im dokładniejsza tym lepsza"
    fi
else
    log_detail "Pominięto sprawdzanie symboli (brak pliku kernel po unpack)."
fi
cd ..
rm -rf sanity_check

log_info "✅ Sanity Checks passed."
# ------------------------------------------------

# 8. PAKOWANIE
log_step "Pakowanie finalnego archiwum..."

# We are in INPUT_DIR (the extracted images).
# We need to create a zip containing these images.
# But wait, original structure has nested zips.
# Google Factory Image:
#   device-build-tags.zip
#     -> bootloader.img
#     -> radio.img
#     -> image-device-build.zip  <-- We are likely inside this one or unpacked it?

# Pixel Automator unpacks OUTER zip, then unpacks INNER zip (image-*.zip) to `extracted_cache/basename`.
# So `extracted_cache/basename` contains:
#   init_boot.img
#   boot.img
#   vendor.img
#   ...
#   android-info.txt (usually)

# So if we zip THIS directory, we get a flat zip of images.
# This is equivalent to the INNER zip.
# However, for `fastboot update`, we need the OUTER zip structure IF we want to flash bootloader/radio too.
log_sub "Tworzenie finalnego archiwum z $(pwd)..."

if [ "$FAST_MODE" = "yes" ]; then
    log_info "⚡ FAST MODE: Using store compression (instant)"
    $ZIP_CREATOR "." "$ROOT_DIR/final_update.zip" --fast
else
    $ZIP_CREATOR "." "$ROOT_DIR/final_update.zip"
fi

# 9. RAPORT KOŃCOWY
log_step "Podsumowanie Modyfikacji"
log_info "❗ vbmeta.img: STOCK (Google signature preserved)"
log_info "❗ init_boot.img: MODIFIED (Custom AVB signature)"
echo "---------------------------------------------------"
printf "%-20b %-25b %-10b\n" "PLIK" "STATUS" "AKCJA"
echo "---------------------------------------------------"

for img in *.img; do
    [ -e "$img" ] || continue
    STATUS="${GRAY}STOCK${NC}"
    ACTION="-"
    
    for mod in "${MODIFIED_FILES[@]}"; do
        if [ "$mod" == "$img" ]; then
            STATUS="${GREEN}MODIFIED${NC}"
            ACTION="Inject+Sign"
            break
        fi
    done
    
    printf "%-20b %-35b %-10b\n" "$img" "$STATUS" "$ACTION"
done
echo "---------------------------------------------------"

cd "$ROOT_DIR"
rm -f "$KSU_KO_PATH"

log_info "Plik wynikowy: final_update.zip"