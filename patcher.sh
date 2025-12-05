#!/bin/bash

ROOT_DIR=$(pwd)

# ================= KONFIGURACJA =================
INPUT_ZIP="$1"
KEY_PATH="${2:-cyber_rsa4096_private.pem}"

# Ścieżki
WORK_DIR="$ROOT_DIR/work_area"
CACHE_DIR="$ROOT_DIR/output/extracted_cache"
KSU_KO_PATH="$ROOT_DIR/kernelsu.ko"
CMD_LOG="$WORK_DIR/last_command.log"

# Narzędzia
MAGISKBOOT="/usr/local/bin/magiskboot"
ZIP_EXTRACTOR="python3 /app/zip_extractor.py"

# Inteligentne szukanie avbtool
if [ -f "/usr/local/bin/avbtool.py" ]; then
    AVBTOOL_EXEC="python3 /usr/local/bin/avbtool.py"
elif [ -f "$ROOT_DIR/avbtool.py" ]; then
    AVBTOOL_EXEC="python3 $ROOT_DIR/avbtool.py"
else
    echo "❌ KRYTYCZNY BŁĄD: Nie znaleziono avbtool!"
    exit 1
fi

# Kolory
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m'

# --- FUNKCJE LOGOWANIA ---
log_info() { echo -e "${GREEN}[PATCHER] $1${NC}"; }
log_step() { echo -e "${YELLOW}[KROK] $1${NC}"; }
log_sub()  { echo -e "${CYAN}   -> $1${NC}"; }
log_detail(){ echo -e "${BLUE}      * $1${NC}"; }
log_error() { echo -e "${RED}[BŁĄD] $1${NC}"; }

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

echo -e "${YELLOW}=== PIXEL AUTO-PATCHER (DETAILED REPORT) ===${NC}"

if [ ! -s "/usr/local/bin/avbtool.py" ]; then
    log_error "KRYTYCZNE: avbtool.py jest pusty! Przebuduj obraz Dockera."
    exit 1
fi

if [[ "$KEY_PATH" != /* ]]; then KEY_PATH="$ROOT_DIR/$KEY_PATH"; fi
if [ ! -f "$KEY_PATH" ]; then log_error "Brak klucza: $KEY_PATH"; exit 1; fi

# Lista zmodyfikowanych plików
declare -a MODIFIED_FILES=()

# 1. ROZPAKOWYWANIE
log_step "1/8 Przygotowanie obrazów..."
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR/images"

CACHE_HIT=false
# Sprawdzamy czy mamy gotowe pliki .img w cache
if [ -f "$CACHE_DIR/init_boot.img" ]; then
    log_info "⚡ Cache Hit! Używam gotowych plików .img"
    cp "$CACHE_DIR/"*.img "$WORK_DIR/images/" 2>/dev/null
    INNER_ZIP="FROM_CACHE"
    CACHE_HIT=true
fi

if [ "$CACHE_HIT" = false ]; then
    log_sub "Rozpakowywanie głównego archiwum..."
    $ZIP_EXTRACTOR "$INPUT_ZIP" "$WORK_DIR/extracted" > /dev/null
    
    INNER_ZIP=$(find "$WORK_DIR/extracted" -name "image-*.zip" | head -n 1)
    
    if [ -z "$INNER_ZIP" ]; then
        if [ -f "$WORK_DIR/extracted/init_boot.img" ] || [ -f "$WORK_DIR/extracted/boot.img" ]; then
            mv "$WORK_DIR/extracted"/*.img "$WORK_DIR/images/"
            INNER_ZIP="DIRECT_MODE"
        else
            log_error "Nieznana struktura ZIPa."
            exit 1
        fi
    else
        log_sub "Rozpakowywanie wewnętrznego archiwum..."
        $ZIP_EXTRACTOR "$INNER_ZIP" "$WORK_DIR/images" > /dev/null
    fi

    log_detail "Zapisywanie kopii do Cache..."
    mkdir -p "$CACHE_DIR"
    cp "$WORK_DIR/images/"*.img "$CACHE_DIR/" 2>/dev/null
fi

# 2. WYBÓR CELU
TARGET_IMG="init_boot.img"
TARGET_PATH="$WORK_DIR/images/$TARGET_IMG"
if [ ! -f "$TARGET_PATH" ]; then
    TARGET_IMG="boot.img"
    TARGET_PATH="$WORK_DIR/images/$TARGET_IMG"
    if [ ! -f "$TARGET_PATH" ]; then log_error "Brak obrazu!"; exit 1; fi
fi
log_info "Cel patchowania: $TARGET_IMG"

# 3. POBIERANIE KERNELSU
log_step "2/8 Pobieranie modułu KernelSU..."
KSU_MODULE_URL="https://github.com/tiann/KernelSU/releases/download/v0.9.5/android14-6.1_kernelsu.ko" 
if [ -f "$KSU_KO_PATH" ]; then rm "$KSU_KO_PATH"; fi
exec_cmd "Pobieranie pliku .ko z GitHub..." wget -q "$KSU_MODULE_URL" -O "$KSU_KO_PATH"

if [ ! -s "$KSU_KO_PATH" ]; then log_error "Plik .ko ma rozmiar 0!"; exit 1; fi

# 4. INIEKCJA
log_step "3/8 Modyfikacja Ramdisku (GKI Injection)..."
cd "$WORK_DIR/images" || exit 1

exec_cmd "Analiza struktury (Magiskboot Unpack)..." $MAGISKBOOT unpack "$TARGET_IMG"

if [ ! -f "ramdisk.cpio" ]; then log_error "Błąd unpack (brak ramdisk.cpio)"; exit 1; fi

exec_cmd "Wstrzykiwanie modułu (CPIO Add)..." \
    $MAGISKBOOT cpio ramdisk.cpio "add 0644 kernelsu.ko $KSU_KO_PATH"

exec_cmd "Pakowanie obrazu (Magiskboot Repack)..." \
    $MAGISKBOOT repack "$TARGET_IMG" new_image.img

mv new_image.img "$TARGET_IMG"
MODIFIED_FILES+=("$TARGET_IMG") # Rejestrujemy modyfikację
log_info "Obraz $TARGET_IMG został pomyślnie zmodyfikowany."

# 5. PODPISYWANIE
log_step "4/8 Procedura AVB (Android Verified Boot)..."

PARTITION_NAME="$(basename "$TARGET_IMG" .img)"
FILE_SIZE_BEFORE=$(stat -c %s "$TARGET_IMG")

log_detail "Partycja docelowa: $PARTITION_NAME"
log_detail "Rozmiar przed:    $((FILE_SIZE_BEFORE/1024)) KB"

exec_cmd "Usuwanie starego podpisu Google..." \
    $AVBTOOL_EXEC erase_footer --image "$TARGET_IMG"

log_sub "Generowanie i aplikowanie podpisu..."
# Uruchamiamy AVBTool i przechwytujemy wyjście, żeby sprawdzić błędy, ale nie wyświetlamy śmieci
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

# 6. OBSŁUGA VBMETA (Informacyjna)
log_step "5/8 Weryfikacja VBMeta..."
if [ -f "vbmeta.img" ]; then
    log_sub "Znaleziono: vbmeta.img"
    log_detail "Status: STOCK (Oryginalny od Google)"
    log_detail "Info: Ten plik zawiera hashe oryginalnych partycji."
    log_detail "      Ponieważ używamy Custom Key w Bootloaderze (Yellow State),"
    log_detail "      bootloader użyje podpisu w $TARGET_IMG zamiast hasha z vbmeta."
else
    log_sub "Nie znaleziono pliku vbmeta.img (Może być w innym archiwum)"
fi

# 7. SANITY CHECK
log_step "6/8 🛡️  SANITY CHECK..."
AVB_INFO=$($AVBTOOL_EXEC info_image --image "$TARGET_IMG" 2>&1)

if echo "$AVB_INFO" | grep -q -E "Footer version:|Footer info:|Algorithm:"; then
    SALT=$(echo "$AVB_INFO" | grep "Salt:" | head -n1 | awk '{print $2}' | cut -c 1-20)...
    ALGO=$(echo "$AVB_INFO" | grep "Algorithm:" | head -n1 | awk '{print $2}')
    log_info "✅ Weryfikacja pomyślna."
    log_detail "Algorytm: $ALGO"
    log_detail "Salt:     $SALT"
else
    log_error "❌ BŁĄD: Plik nie posiada poprawnej stopki AVB!"
    echo "$AVB_INFO"
    exit 1
fi

# 8. PAKOWANIE
log_step "7/8 Aktualizacja archiwum ZIP..."

if [ "$INNER_ZIP" = "FROM_CACHE" ] || [ "$INNER_ZIP" = "DIRECT_MODE" ]; then
    if [ "$INNER_ZIP" = "FROM_CACHE" ]; then
        log_info "Rekonstrukcja struktury ZIPa..."
        $ZIP_EXTRACTOR "$INPUT_ZIP" "$WORK_DIR/extracted" > /dev/null
        
        INNER_ZIP_REAL=$(find "$WORK_DIR/extracted" -name "image-*.zip" | head -n 1)
        if [ -z "$INNER_ZIP_REAL" ]; then
             exec_cmd "Pakowanie ZIP..." zip -r -q "$ROOT_DIR/final_update.zip" .
        else
             log_sub "Podmienianie pliku $TARGET_IMG w $(basename "$INNER_ZIP_REAL")..."
             zip -u "$INNER_ZIP_REAL" "$TARGET_IMG" > /dev/null
             
             mv "$INNER_ZIP_REAL" "../extracted/$(basename "$INNER_ZIP_REAL")"
             cd "$WORK_DIR/extracted" || exit 1
             
             exec_cmd "Pakowanie finalnego ZIPa..." zip -r -q "$ROOT_DIR/final_update.zip" .
        fi
    else
        exec_cmd "Pakowanie finalnego ZIPa..." zip -r -q "$ROOT_DIR/final_update.zip" .
    fi
else
    INNER_ZIP_NAME=$(basename "$INNER_ZIP")
    log_sub "Aktualizacja pliku $TARGET_IMG w $INNER_ZIP_NAME..."
    zip -u "$INNER_ZIP_NAME" "$TARGET_IMG" > /dev/null
    
    mv "$INNER_ZIP_NAME" "../extracted/$INNER_ZIP_NAME"
    cd "$WORK_DIR/extracted" || exit 1
    
    exec_cmd "Tworzenie finalnego archiwum..." zip -r -q "$ROOT_DIR/final_update.zip" .
fi

# 9. RAPORT KOŃCOWY
log_step "8/8 Podsumowanie Modyfikacji"
echo "---------------------------------------------------"
printf "${GRAY}%-20s %-15s %-10s${NC}\n" "PLIK" "STATUS" "AKCJA"
echo "---------------------------------------------------"

# Lista wszystkich img w katalogu extracted/images (gdzie byliśmy przed chwilą)
# Musimy wrócić do $WORK_DIR/images (lub sprawdzić cache)
# Najlepiej po prostu sprawdzić co mamy w folderze images (bo tam pracowaliśmy)
cd "$WORK_DIR/images" 2>/dev/null

for img in *.img; do
    [ -e "$img" ] || continue
    STATUS="${GRAY}STOCK${NC}"
    ACTION="-"
    
    # Sprawdź czy plik jest na liście zmodyfikowanych
    for mod in "${MODIFIED_FILES[@]}"; do
        if [ "$mod" == "$img" ]; then
            STATUS="${GREEN}MODIFIED${NC}"
            ACTION="Inject+Sign"
            break
        fi
    done
    
    printf "%-20s %-25s %-10s\n" "$img" "$STATUS" "$ACTION"
done
echo "---------------------------------------------------"

cd "$ROOT_DIR"
rm -rf "$WORK_DIR"
rm -f "$KSU_KO_PATH"

log_info "Plik wynikowy: final_update.zip"