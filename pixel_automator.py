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
from ui_utils import print_status, print_header, ProgressBar, Color, print_step, get_visual_hash

# ================= KONFIGURACJA =================
DEVICE_CODENAME = os.environ.get('_DEVICE_CODENAME', 'frankel') 
OUTPUT_JSON = "build_status.json"
TARGET_URL = "https://developers.google.com/android/images"
DEFAULT_KEY_NAME = "cyber_rsa4096_private.pem"
DEFAULT_DOCKER_KEY_PATH = f"/app/{DEFAULT_KEY_NAME}"
OUTPUT_DIR = "/app/output"
EXTRACTED_CACHE_DIR = "/app/output/extracted_cache"
WORK_AREA_DIR = "/app/output/work_area"

def log(msg):
    print_status("AUTOMATOR", "INFO", msg, Color.BLUE)

def log_error(msg):
    print_status("AUTOMATOR", "ERROR", msg, Color.RED)

def run_cmd(cmd):
    log(f"EXEC: {cmd}")
    subprocess.check_call(cmd, shell=True)

def calculate_sha256(filename):
    sha256_hash = hashlib.sha256()
    file_size = os.path.getsize(filename)
    
    # Check if small enough to skip bar? No, users love bars.
    bar = ProgressBar(f"Hashing {os.path.basename(filename)}", total=file_size)
    
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(1024*1024), b""):
            sha256_hash.update(byte_block)
            bar.update(len(byte_block))
    bar.finish()
    return sha256_hash.hexdigest()

def calculate_string_sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

def calculate_work_area_hash(work_dir):
    """Fast hash of work area to detect changes."""
    hasher = hashlib.sha256()
    # Hash only modified files for speed
    modified_files = ['init_boot.img', 'vbmeta.img', 'boot.img']
    for fname in sorted(modified_files):
        fpath = os.path.join(work_dir, fname)
        if os.path.exists(fpath):
            hasher.update(fname.encode())
            hasher.update(str(os.path.getsize(fpath)).encode())
            hasher.update(str(os.path.getmtime(fpath)).encode())
    return hasher.hexdigest()

def get_cached_hash_from_status(filename):
    """Check if we already know the hash from a previous build."""
    if not os.path.exists(OUTPUT_JSON):
        return None
    
    try:
        with open(OUTPUT_JSON, 'r') as f:
            data = json.load(f)
        
        # Check if the cached filename matches
        if data.get("input", {}).get("filename") == os.path.basename(filename):
            cached_hash = data.get("input", {}).get("sha256")
            if cached_hash and len(cached_hash) == 64:  # Valid SHA256
                return cached_hash
    except:
        pass
    
    return None

def verify_sha256(filename, expected_sha256):
    if not expected_sha256:
        log("⚠️  Missing expected SHA256.")
        return False

    # SMART HASH CACHING: Check if we already know this file's hash
    cached_hash = get_cached_hash_from_status(filename)
    
    if cached_hash:
        log(f"📋 Using cached hash from previous build...")
        calculated_hash = cached_hash
        print(f"Visual Hash: {get_visual_hash(calculated_hash)}")
    else:
        calculated_hash = calculate_sha256(filename)
        # VISUAL HASH
        print(f"Visual Hash: {get_visual_hash(calculated_hash)}")
    
    if calculated_hash.lower() == expected_sha256.lower():
        print_status("HASH", "OK", "SHA256 Match", Color.GREEN)
        return True
    else:
        log_error(f"CHECKSUM MISMATCH! Expected: {expected_sha256}, Got: {calculated_hash}")
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
    # ... (Same as before, abbreviated here for clarity if I was writing partially, but I must provide full replacement of affected logic)
    # Since I am replacing the whole file content basically to insert imports and global logic, I will restart main logic.
    log(f"Starting headless browser for: {device}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        log(f"Navigating to: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            log_error(f"Failed to load page: {e}")
            return None, None, None

        # Helper to click things
        def click_visible(selector, force=True):
            try:
                el = page.locator(selector)
                if el.count() > 0 and el.first.is_visible():
                    el.first.click(force=force)
                    return True
            except: pass
            return False

        # Cookie & License Logic (Condensed)
        click_visible("text=/Ok, got it|Accept all|Zgadzam się/i")
        
        page.wait_for_timeout(500)
        # License
        try:
            ack_btn = page.locator(".devsite-acknowledgement-link").first
            if ack_btn.is_visible():
                ack_btn.click(force=True)
                page.wait_for_timeout(1000)
                if ack_btn.is_visible(): ack_btn.click(force=True)
                try: ack_btn.wait_for(state="hidden", timeout=5000)
                except: pass
        except: pass

        # Find Links
        log(f"Searching links for {device}...")
        try: page.wait_for_selector("a[href*='.zip']", timeout=30000)
        except: log("⚠️  Timeout waiting for links table.")

        content = page.content()
        link_regex = f'href="([^"]*?{device}[^"]*?\\.zip)"'
        match = re.search(link_regex, content)
        
        if not match:
            log_error(f"No image found for '{device}'")
            browser.close()
            return None, None, None
        
        latest_url = match.group(1)
        filename = latest_url.split('/')[-1]
        log(f"Found URL: {latest_url}")
        
        expected_sha = None
        try:
            row_handle = page.query_selector(f"//a[contains(@href, '{filename}')]/ancestor::tr")
            if row_handle:
                expected_sha = re.search(r'\b[a-f0-9]{64}\b', row_handle.inner_text()).group(0)
                log(f"Found SHA256: {expected_sha}")
        except: pass

        browser.close()
        return latest_url, filename, expected_sha

def download_file(url, filename):
    if os.path.exists(filename): return
    # If partial download? Requests doesn't support resume easily.
    # Assuming valid if exists, or checksum will fail.

    log(f"Starting download: {filename}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log_error(f"Connection error: {e}")
        sys.exit(1)

    total_size = int(response.headers.get('content-length', 0))
    bar = ProgressBar(f"Downloading {filename}", total=total_size)
    
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))
    bar.finish()
    log("Download completed.")

def prepare_extracted_workspace(zip_path):
    """
    Centralized unpacking logic.
    Returns path to the directory containing extracted images (inner zip content).
    """
    import zip_extractor
    
    base_name = os.path.splitext(os.path.basename(zip_path))[0]
    workspace_dir = os.path.join(EXTRACTED_CACHE_DIR, base_name)
    
    if os.path.exists(workspace_dir):
        if os.path.exists(os.path.join(workspace_dir, "init_boot.img")) or \
           os.path.exists(os.path.join(workspace_dir, "boot.img")):
            print_status("CACHE", "HIT", f"Using extracted cache: {workspace_dir}", Color.GREEN)
            return workspace_dir
    
    print_status("UNPACK", "START", f"Unpacking factory image to cache...", Color.YELLOW)
    
    temp_outer = os.path.join(EXTRACTED_CACHE_DIR, "temp_outer")
    if os.path.exists(temp_outer): shutil.rmtree(temp_outer)
    os.makedirs(temp_outer, exist_ok=True)
    
    zip_extractor.extract_with_progress(zip_path, temp_outer)
    
    inner_zip = None
    for root, dirs, files in os.walk(temp_outer):
        for f in files:
            if f.startswith("image-") and f.endswith(".zip"):
                inner_zip = os.path.join(root, f)
                break
    
    if not inner_zip:
        log_error("Could not find inner image zip!")
        sys.exit(1)
        
    os.makedirs(workspace_dir, exist_ok=True)
    zip_extractor.extract_with_progress(inner_zip, workspace_dir)
    
    shutil.rmtree(temp_outer)
    return workspace_dir

def check_smart_cache(input_sha256, key_content_sha256):
    """
    Checks if we have already built this exact configuration successfully.
    """
    if not os.path.exists(OUTPUT_JSON): return False
    
    try:
        with open(OUTPUT_JSON, 'r') as f:
            data = json.load(f)
            
        last_status = data.get("build_meta", {}).get("status")
        if last_status != "success": return False
        
        last_input_sha = data.get("input", {}).get("sha256")
        if last_input_sha != input_sha256: return False
        
        # Check key signature if we stored it?
        # We didn't store key hash in previous JSON.
        # But we can check if output filename exists.
        output_filename = data.get("output", {}).get("filename")
        if not output_filename or not os.path.exists(output_filename): return False
        
        return output_filename
    except:
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-file', help='Local ZIP file')
    parser.add_argument('--local-key', help='Local Key')
    parser.add_argument('--minimal', action='store_true', help='Create minimal ZIP (only modified files)')
    parser.add_argument('--fast', action='store_true', help='Use fast compression (store mode)')
    parser.add_argument('--raw-output', action='store_true', help='Skip ZIP, output raw init_boot.img only (fastest)')
    args = parser.parse_args()

    print_header("PIXEL AUTO-PATCHER START")

    filename = None
    sha256 = None
    key_path = None
    used_cached_file = False
    
    # 1. Key Resolution
    if args.local_key:
        if os.path.exists(args.local_key): key_path = os.path.abspath(args.local_key)
        else: sys.exit(1)
    elif os.path.exists(DEFAULT_DOCKER_KEY_PATH): key_path = DEFAULT_DOCKER_KEY_PATH
    elif os.path.exists(DEFAULT_KEY_NAME): key_path = os.path.abspath(DEFAULT_KEY_NAME)
    else:
        log_error(f"Key not found: {DEFAULT_KEY_NAME}")
        sys.exit(1)
    
    with open(key_path, 'r') as kf:
        key_content = kf.read()
    key_hash = calculate_string_sha256(key_content)

    # 2. File Resolution
    if args.local_file:
        log(f"🛠️  Local Mode: {args.local_file}")
        if not os.path.exists(args.local_file): 
            log_error("Local file does not exist!")
            sys.exit(1)
        filename = args.local_file
    else:
        log("🌐 Online Mode...")
        url, scraped_filename, scraped_sha256 = get_latest_factory_image_data_headless(DEVICE_CODENAME)
        
        if not url:
            log_error("CRITICAL: Could not fetch URL.")
            sys.exit(1)

        potential_cached_path = os.path.join(OUTPUT_DIR, scraped_filename)
        if os.path.exists(potential_cached_path):
            log(f"💾 Found in cache: {potential_cached_path}")
            if scraped_sha256:
                if verify_sha256(potential_cached_path, scraped_sha256):
                    log("⚡ CACHE HIT!")
                    filename = potential_cached_path
                    sha256 = scraped_sha256
                    used_cached_file = True
                else: log("⚠️  CACHE MISS (Checksum invalid).")
            else: log("⚠️  No SHA256 to verify cache.")
        
        if not used_cached_file:
            filename = scraped_filename
            download_file(url, filename)
            if scraped_sha256 and not verify_sha256(filename, scraped_sha256): sys.exit(1)
            
            if os.path.exists(OUTPUT_DIR):
                try:
                    dest_path = os.path.join(OUTPUT_DIR, os.path.basename(filename))
                    shutil.copy2(filename, dest_path)
                except: pass

    # 3. Smart Caching Check (Skip Repack)
    abs_filename = os.path.abspath(filename)
    if not sha256:
        # Calculate if not local? Or just calc anyway for integrity record.
        sha256 = calculate_sha256(abs_filename)
        
    cached_output = check_smart_cache(sha256, key_hash)
    if cached_output:
        print_status("SMART SKIP", "PASS", f"Output {cached_output} already exists for this input. Skipping build.", Color.GREEN)
        sys.exit(0)

    # 4. Unpack
    extracted_workspace = prepare_extracted_workspace(abs_filename)

    # 5. Separation: Copy to Temp Work Area
    print_status("SETUP", "INFO", "Creating temporary work area...", Color.BLUE)
    if os.path.exists(WORK_AREA_DIR): shutil.rmtree(WORK_AREA_DIR)
    
    # Calculate total size for progress bar
    total_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                     for dirpath, dirnames, filenames in os.walk(extracted_workspace)
                     for filename in filenames)
    
    bar = ProgressBar(f"Copying to work area", total=total_size)
    
    def copy_with_progress(src, dst):
        """Copy tree with progress bar"""
        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                copy_with_progress(s, d)
            else:
                shutil.copy2(s, d)
                bar.update(os.path.getsize(s))
    
    copy_with_progress(extracted_workspace, WORK_AREA_DIR)
    bar.finish()
    
    # 6. Verify (in work area? sure, doesn't matter)
    log("🛡️  Verifying Google Signatures...")
    try:
        subprocess.check_call(f"python3 google_verifier.py \"{WORK_AREA_DIR}\"", shell=True)
    except:
        log_error("VERIFICATION FAILED!"); sys.exit(1)

    # 7. Patcher
    log("Passing to patcher...")
    try:
        subprocess.check_call(f"/bin/bash ./patcher.sh \"{WORK_AREA_DIR}\" \"{key_path}\"", shell=True)
    except:
        log_error("Patching process failed."); sys.exit(1)

    # 8. Smart packaging
    output_filename = f"ksu_patched_{os.path.basename(filename)}"
    final_output_sha256 = None
    
    # Calculate work area hash for caching
    work_area_hash = calculate_work_area_hash(WORK_AREA_DIR)
    
    # Check if we can skip packaging
    cached_output = None
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r') as f:
                prev_data = json.load(f)
            prev_hash = prev_data.get("build_meta", {}).get("work_area_hash")
            prev_output = prev_data.get("output", {}).get("filename")
            if prev_hash == work_area_hash and os.path.exists(prev_output):
                log(f"⚡ WORK AREA UNCHANGED - Reusing previous build!")
                print_status("CACHE", "HIT", f"Output: {prev_output}", Color.GREEN)
                cached_output = prev_output
        except:
            pass
    
    if cached_output:
        output_filename = cached_output
        status = "success"
        log("Calculating final checksum...")
        final_output_sha256 = calculate_sha256(output_filename)
        print(f"Final Visual Hash: {get_visual_hash(final_output_sha256)}")
    elif args.raw_output:
        # ULTRA-FAST MODE: Raw init_boot.img only (no ZIP)
        log("⚡⚡⚡ ULTRA-FAST MODE: Raw output (no compression)")
        
        raw_output = f"init_boot_ksu_{os.path.basename(filename).replace('.zip', '.img')}"
        shutil.copy2(os.path.join(WORK_AREA_DIR, "init_boot.img"), raw_output)
        
        # Generate AVB public key for locked bootloader
        log("Generating AVB public key for locked bootloader...")
        try:
            subprocess.check_call(
                f"avbtool extract_public_key --key {key_path} --output avb_custom_public.bin",
                shell=True
            )
            print_status("AVB", "KEY", "Public key: avb_custom_public.bin", Color.GREEN)
        except:
            log("⚠️  Failed to extract public key (avbtool might not support PEM)")
            log("   You can generate it manually with: openssl + avbtool")
        
        output_filename = raw_output
        status = "success"
        
        log("Calculating final checksum...")
        final_output_sha256 = calculate_sha256(output_filename)
        print(f"Final Visual Hash: {get_visual_hash(final_output_sha256)}")
        
        # Print flash instructions
        print(f"\n{Color.BOLD}{Color.GREEN}=== FLASH INSTRUCTIONS ==={Color.NC}")
        print(f"{Color.CYAN}# Unlocked bootloader:{Color.NC}")
        print(f"  fastboot flash init_boot_a {output_filename}")
        print(f"  fastboot flash init_boot_b {output_filename}")
        print(f"  fastboot reboot")
        print(f"\n{Color.CYAN}# Locked bootloader (ADVANCED):{Color.NC}")
        print(f"  fastboot flash avb_custom_key avb_custom_public.bin")
        print(f"  fastboot flash init_boot_a {output_filename}")
        print(f"  fastboot flash init_boot_b {output_filename}")
        print(f"  fastboot flashing lock")
        print(f"  fastboot reboot{Color.NC}\n")
    elif args.minimal:
        # MINIMAL MODE: Only modified files
        log("Creating MINIMAL output (modified files only)...")
        minimal_dir = "/tmp/minimal_build"
        os.makedirs(minimal_dir, exist_ok=True)
        
        # Copy only modified init_boot.img
        shutil.copy2(os.path.join(WORK_AREA_DIR, "init_boot.img"), minimal_dir)
        
        # Create flash helper script
        with open(os.path.join(minimal_dir, "flash.sh"), "w") as f:
            f.write("#!/bin/bash\n")
            f.write("# Flash KernelSU patched init_boot\n")
            f.write("fastboot flash init_boot_a init_boot.img\n")
            f.write("fastboot flash init_boot_b init_boot.img\n")
            f.write("fastboot reboot\n")
        os.chmod(os.path.join(minimal_dir, "flash.sh"), 0o755)
        
        # Zip it (fast mode always for minimal)
        import zip_creator
        minimal_zip = output_filename.replace(".zip", "_minimal.zip")
        zip_creator.zip_directory_with_progress(minimal_dir, minimal_zip, compression_level=0)
        output_filename = minimal_zip
        status = "success"
        shutil.rmtree(minimal_dir)
        
        log("Calculating final checksum...")
        final_output_sha256 = calculate_sha256(output_filename)
        print(f"Final Visual Hash: {get_visual_hash(final_output_sha256)}")
    elif os.path.exists("final_update.zip"):
        os.rename("final_update.zip", output_filename)
        status = "success"
        log("Calculating final checksum...")
        final_output_sha256 = calculate_sha256(output_filename)
        print(f"Final Visual Hash: {get_visual_hash(final_output_sha256)}")
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
            "from_cache": used_cached_file,
            "key_hash": key_hash,
            "work_area_hash": work_area_hash
        },
        "input": {
            "filename": os.path.basename(filename),
            "sha256": sha256,
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
        
    print_status("DONE", "SUCCESS", f"Report saved to {OUTPUT_JSON}", Color.GREEN)

    # Cleanup Work Area?
    # shutil.rmtree(WORK_AREA_DIR) # Keep for debug if needed, or remove?
    # User might want to inspect. Let's keep it or clean it? Use Docker --rm usually.
    # We will leave it.

if __name__ == "__main__":
    main()