# # pixel_automator.py
import os
import sys
import json
import re
import hashlib
import requests
import subprocess
import time
import argparse
import shutil
from datetime import datetime
from playwright.sync_api import sync_playwright

# ================= KONFIGURACJA =================
DEVICE_CODENAME = os.environ.get('_DEVICE_CODENAME', 'frankel') 
OUTPUT_JSON = "build_status.json"
TARGET_URL = "https://developers.google.com/android/images"
DEFAULT_KEY_NAME = "cyber_rsa4096_private.pem"
DEFAULT_DOCKER_KEY_PATH = f"/app/{DEFAULT_KEY_NAME}"
OUTPUT_DIR = "/app/output"

def log(msg):
    print(f"[AUTOMATOR] {msg}", flush=True)

def log_error(msg):
    print(f"[AUTOMATOR_ERR] ❌ {msg}", flush=True)

def run_cmd(cmd):
    log(f"EXEC: {cmd}")
    subprocess.check_call(cmd, shell=True)

def calculate_sha256(filename):
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def verify_sha256(filename, expected_sha256):
    if not expected_sha256:
        log("⚠️  Brak wzorca SHA256 do weryfikacji.")
        return False

    log(f"Weryfikacja SHA256 dla {os.path.basename(filename)}...")
    calculated_hash = calculate_sha256(filename)
    
    if calculated_hash.lower() == expected_sha256.lower():
        log("✅ Suma kontrolna poprawna (MATCH).")
        return True
    else:
        log_error(f"BŁĄD SUMY KONTROLNEJ! Oczekiwano: {expected_sha256}, Obliczono: {calculated_hash}")
        return False

def format_size(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

def get_latest_factory_image_data_headless(device):
    log(f"Uruchamianie przeglądarki dla urządzenia: {device}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        log(f"Wchodzenie na: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            log_error(f"Nie udało się załadować strony: {e}")
            return None, None, None

        # 1. Weryfikacja
        page_title = page.title()
        if "Factory Images" not in page_title and "Android" not in page_title:
            log_error("Podejrzany tytuł strony! Możliwa blokada.")
            if os.path.exists(OUTPUT_DIR): page.screenshot(path=f"{OUTPUT_DIR}/access_denied.png")
            return None, None, None

        # === KROK A: Ciasteczka (COOKIE SWEEPER) ===
        # Google często blokuje interakcję dopóki nie klikniesz "Ok, got it"
        try:
            log("Szukanie banera ciasteczek ('Ok, got it')...")
            # Czekamy chwilę, bo baner często wjeżdża z animacją
            try:
                page.wait_for_selector("text=/Ok, got it|Accept all|Zgadzam się/i", timeout=5000)
            except: pass

            # Klikamy wszystko co wygląda jak zgoda na cookies
            cookie_btn = page.locator("text=/Ok, got it|Accept all|Zgadzam się/i")
            if cookie_btn.count() > 0:
                if cookie_btn.first.is_visible():
                    log(f"🍪 Znaleziono przycisk ciasteczek. Klikam...")
                    cookie_btn.first.click(force=True)
                    page.wait_for_timeout(1000) # Czekamy aż zniknie
                else:
                    log("Baner ciasteczek wykryty w DOM, ale niewidoczny.")
            else:
                log("Nie znaleziono banera ciasteczek. Przechodzę dalej.")
        except Exception as e:
            log(f"Info: Problem z ciasteczkami: {e}")

        # === KROK B: Licencja (Acknowledge - .devsite-acknowledgement-link) ===
        try:
            log("Szukanie przycisku Licencji (.devsite-acknowledgement-link)...")
            
            # Używamy dokładnie tej klasy, którą znalazłeś w HTMLu
            ack_selector = ".devsite-acknowledgement-link"
            ack_button = page.locator(ack_selector).first
            
            try: 
                ack_button.wait_for(state="visible", timeout=5000)
            except: pass

            if ack_button.is_visible():
                log("🟦 Znaleziono przycisk Licencji. Klikam (FORCE)...")
                ack_button.click(force=True)
                
                # Dodatkowe zabezpieczenie: jeśli przycisk nadal jest widoczny po 1s, klikamy jeszcze raz
                page.wait_for_timeout(1000)
                if ack_button.is_visible():
                    log("⚠️ Przycisk nadal widoczny. Klikam ponownie (Double Tap)...")
                    ack_button.click(force=True)

                log("Czekanie 10s na przeładowanie danych...")
                # Czekamy na zniknięcie przycisku LUB pojawienie się tabeli
                try:
                    ack_button.wait_for(state="hidden", timeout=10000)
                except: pass
            else:
                log("Przycisk licencji niewidoczny (może już zaakceptowano lub brak modala).")

        except Exception as e: 
            log(f"Wyjątek przy przycisku licencji: {e}")

        # === KROK C: Linki ===
        log(f"Szukanie linków dla {device}...")
        try:
            # Czekamy na link ZIP. Jeśli strona się przeładowuje po kliknięciu, to może chwilę potrwać.
            page.wait_for_selector("a[href*='.zip']", timeout=30000)
        except: 
            log("⚠️  Timeout: Tabela linków się nie pojawiła.")

        content = page.content()
        link_regex = f'href="([^"]*?{device}[^"]*?\\.zip)"'
        match = re.search(link_regex, content)
        
        if not match:
            log_error(f"Nie znaleziono obrazów dla '{device}' w kodzie strony.")
            
            # DEBUG: Zrzut tylko przy błędzie
            if os.path.exists(OUTPUT_DIR):
                log("📸 Zapisywanie zrzutu błędu...")
                page.screenshot(path=f"{OUTPUT_DIR}/error_screenshot.png")
                with open(f"{OUTPUT_DIR}/error_dump.html", "w", encoding="utf-8") as f:
                    f.write(content)
                log(f"   -> {OUTPUT_DIR}/error_screenshot.png")
            
            browser.close()
            return None, None, None
        
        latest_url = match.group(1)
        filename = latest_url.split('/')[-1]
        log(f"Znaleziono URL: {latest_url}")
        
        expected_sha = None
        try:
            row_handle = page.query_selector(f"//a[contains(@href, '{filename}')]/ancestor::tr")
            if row_handle:
                expected_sha = re.search(r'\b[a-f0-9]{64}\b', row_handle.inner_text()).group(0)
                log(f"Znaleziono SHA256: {expected_sha}")
        except: pass

        browser.close()
        return latest_url, filename, expected_sha

def download_file(url, filename):
    if os.path.exists(filename): return

    log(f"Rozpoczynanie pobierania {filename}...")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log_error(f"Błąd połączenia: {e}")
        sys.exit(1)

    total_size = int(response.headers.get('content-length', 0))
    block_size = 8192
    downloaded = 0
    start_time = time.time()

    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=block_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                
                if total_size > 0:
                    percent = downloaded * 100 / total_size
                    if percent > 100.0: percent = 100.0
                    bar_len = 30
                    filled = int(bar_len * percent // 100)
                    bar = '█' * filled + '-' * (bar_len - filled)
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    sys.stdout.write(f"\r⬇️  |{bar}| {percent:.1f}% | {format_size(downloaded)} / {format_size(total_size)} | {format_size(speed)}/s")
                sys.stdout.flush()
    print()
    log("Pobieranie zakończone.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-file', help='Lokalny plik ZIP')
    parser.add_argument('--local-key', help='Lokalny klucz')
    args = parser.parse_args()

    filename = None
    sha256 = None
    key_path = None
    used_cached_file = False
    
    if args.local_key:
        if os.path.exists(args.local_key): key_path = os.path.abspath(args.local_key)
        else: sys.exit(1)
    elif os.path.exists(DEFAULT_DOCKER_KEY_PATH): key_path = DEFAULT_DOCKER_KEY_PATH
    elif os.path.exists(DEFAULT_KEY_NAME): key_path = os.path.abspath(DEFAULT_KEY_NAME)
    else:
        log_error(f"Nie znaleziono klucza {DEFAULT_KEY_NAME}!")
        sys.exit(1)

    if args.local_file:
        log(f"🛠️  TRYB LOKALNY: {args.local_file}")
        if not os.path.exists(args.local_file): 
            log_error("Plik lokalny nie istnieje!")
            sys.exit(1)
        filename = args.local_file
    else:
        log("🌐 TRYB ONLINE...")
        url, scraped_filename, scraped_sha256 = get_latest_factory_image_data_headless(DEVICE_CODENAME)
        
        # Exit Code 1 jeśli brak URL
        if not url:
            log_error("KRYTYCZNE: Nie udało się pobrać linku. Sprawdź zrzuty w folderze output.")
            sys.exit(1)

        potential_cached_path = os.path.join(OUTPUT_DIR, scraped_filename)
        if os.path.exists(potential_cached_path):
            log(f"💾 Znaleziono w cache: {potential_cached_path}")
            if scraped_sha256:
                if verify_sha256(potential_cached_path, scraped_sha256):
                    log("⚡ CACHE HIT!")
                    filename = potential_cached_path
                    sha256 = scraped_sha256
                    used_cached_file = True
                else: log("⚠️  CACHE MISS.")
            else: log("⚠️  Brak SHA256.")
        
        if not used_cached_file:
            filename = scraped_filename
            download_file(url, filename)
            if scraped_sha256 and not verify_sha256(filename, scraped_sha256): sys.exit(1)
            
            if os.path.exists(OUTPUT_DIR):
                try:
                    dest_path = os.path.join(OUTPUT_DIR, os.path.basename(filename))
                    shutil.copy2(filename, dest_path)
                except: pass

    abs_filename = os.path.abspath(filename)

    log("🛡️  Weryfikacja podpisów Google...")
    try:
        subprocess.check_call(f"python3 google_verifier.py \"{abs_filename}\"", shell=True)
    except:
        log_error("BŁĄD WERYFIKACJI!"); sys.exit(1)

    log(f"Przekazywanie do patchera...")
    try:
        subprocess.check_call(f"/bin/bash ./patcher.sh \"{abs_filename}\" \"{key_path}\"", shell=True)
    except:
        log_error("Błąd patchowania."); sys.exit(1)

    output_filename = f"ksu_patched_{os.path.basename(filename)}"
    final_output_sha256 = None
    
    if os.path.exists("final_update.zip"):
        os.rename("final_update.zip", output_filename)
        status = "success"
        log("Obliczanie sumy kontrolnej pliku wynikowego...")
        final_output_sha256 = calculate_sha256(output_filename)
    else:
        status = "failed"
        output_filename = None

    now = datetime.now()
    
    build_info = {
        "build_meta": {
            "device": DEVICE_CODENAME,
            "date": datetime.utcnow().isoformat(),
            "status": status,
            "last_successful_build": now.strftime("%Y-%m-%d %H:%M:%S") if status == "success" else None,
            "mode": "Local File" if args.local_file else "Auto Download",
            "from_cache": used_cached_file
        },
        "input": {
            "filename": os.path.basename(filename),
            "sha256": sha256 if sha256 else "not_verified_or_local",
            "google_signature_verified": True
        },
        "output": {
            "filename": output_filename,
            "sha256": final_output_sha256,
            "modifications": ["KernelSU Injection", "AVB Custom Signing"],
            "signed_by": os.path.basename(key_path)
        }
    }
    
    with open(OUTPUT_JSON, "w") as f:
        json.dump(build_info, f, indent=4)
        
    log(f"✅ Gotowe. Raport zapisany w {OUTPUT_JSON}")

if __name__ == "__main__":
    main()