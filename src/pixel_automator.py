import os
import sys
import json
import argparse
import shutil
from datetime import datetime

try:
    from google.cloud import storage
except ImportError:
    storage = None

# Local modules
from ui_utils import print_header, print_status, log, log_error, Color, get_visual_hash
import downloader
import downloader
import verifier
import avb_patcher

# ================= KONFIGURACJA =================
DEVICE_CODENAME = os.environ.get('_DEVICE_CODENAME', 'frankel') 
OUTPUT_JSON = "build_status.json"
DEFAULT_KEY_NAME = "cyber_rsa4096_private.pem"
DEFAULT_DOCKER_KEY_PATH = f"/app/{DEFAULT_KEY_NAME}"
OUTPUT_DIR = "/app/output"

def download_gcs_file(bucket_name, blob_name, destination):
    log(f"☁️  Downloading from GCS: gs://{bucket_name}/{blob_name}")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(destination)
        log("✅ Download success")
        return True
    except Exception as e:
        log_error(f"GCS Download Failed: {e}")
        return False

def upload_gcs_file(bucket_name, source_file, destination_blob_name):
    log(f"☁️  Uploading to GCS: {source_file} -> gs://{bucket_name}/{destination_blob_name}")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file)
        log("✅ Upload success")
        return True
    except Exception as e:
        log_error(f"GCS Upload Failed: {e}")
        return False


def upload_gcs_file(bucket_name, source_file, destination_blob_name):
    log(f"☁️  Uploading to GCS: {source_file} -> gs://{bucket_name}/{destination_blob_name}")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file)
        log("✅ Upload success")
        return True
    except Exception as e:
        log_error(f"GCS Upload Failed: {e}")
        return False

def verify_bucket_access(bucket_name):
    """
    Fail-fast check to ensure bucket is accessible before downloading large files.
    """
    if not bucket_name or not storage:
        return # Skip if no bucket configured (local mode) or no storage lib
        
    log(f"🔍 Checking access to GCS Bucket: {bucket_name}")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        # Attempt to list 1 blob - this requires storage.objects.list (included in objectAdmin)
        # whereas bucket.reload() requires storage.buckets.get (not included)
        blobs = list(client.list_blobs(bucket_name, max_results=1))
        log(f"✅ Bucket '{bucket_name}' verified (access ok).")
    except Exception as e:
        log_error(f"❌ CRITICAL failure accessing bucket '{bucket_name}'")
        log_error(f"Reason: {e}")
        log_error("Aborting build immediately to prevent resource waste.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-file', help='Local ZIP file')
    parser.add_argument('--local-key', help='Local Key')
    parser.add_argument('--minimal', action='store_true', help='Create minimal ZIP (only modified files)')
    parser.add_argument('--fast', action='store_true', help='Use fast compression (store mode)')
    parser.add_argument('--raw-output', action='store_true', help='Skip ZIP, output raw init_boot.img only (fastest)')
    parser.add_argument('--skip-hash-check', action='store_true', help='Skip local SHA256 calculation if file exists (Dangerous)')
    args = parser.parse_args()

    print_header("PIXEL AUTO-PATCHER START")

    # 0. Fail-Fast Infrastructure Check
    # Verify bucket immediately if configured
    bucket_env = os.environ.get('BUCKET_NAME') or os.environ.get('_BUCKET_NAME')
    verify_bucket_access(bucket_env)

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
        # Check Cloud Storage if configured
        bucket_env = os.environ.get('BUCKET_NAME') or os.environ.get('_BUCKET_NAME')
        if bucket_env and storage:
            log(f"Key not found locally. Attempting fetch from bucket: {bucket_env}")
            # Assumption: keys are stored in keys/ prefix as per cloudbuild.yaml
            key_blob = f"keys/{DEFAULT_KEY_NAME}"
            fetched_key_path = os.path.join("/app", DEFAULT_KEY_NAME) # Write to /app
            if download_gcs_file(bucket_env, key_blob, fetched_key_path):
                key_path = fetched_key_path
            else:
                log_error(f"Could not fetch key from GCS.")
                sys.exit(1)
        else:
            log_error(f"Key not found: {DEFAULT_KEY_NAME} (and no BUCKET_NAME defined or storage lib missing)")
            sys.exit(1)
    
    with open(key_path, 'r') as kf:
        key_content = kf.read()
    key_hash = verifier.calculate_string_sha256(key_content)

    # 2. File Resolution
    if args.local_file:
        log(f"🛠️  Local Mode: {args.local_file}")
        if not os.path.exists(args.local_file): 
            log_error("Local file does not exist!")
            sys.exit(1)
        filename = args.local_file
    else:
        log("🌐 Online Mode...")
        url, scraped_filename, scraped_sha256 = downloader.get_latest_factory_image_data_headless(DEVICE_CODENAME)
        
        if not url:
            log_error("CRITICAL: Could not fetch URL.")
            sys.exit(1)

        filename = scraped_filename
        potential_cached_path = os.path.join(OUTPUT_DIR, scraped_filename)
        
        # Check if already downloaded
        if os.path.exists(potential_cached_path):
            log(f"💾 Found in cache: {potential_cached_path}")
            # Verify basic integrity including optional skip check
            if scraped_sha256 and not args.skip_hash_check:
                calc_hash = verifier.verify_zip_sha256(potential_cached_path, scraped_sha256)
                if calc_hash:
                    log("⚡ CACHE HIT!")
                    filename = potential_cached_path
                    sha256 = calc_hash
                    used_cached_file = True
                else:
                    log("⚠️  CACHE MISS (Checksum invalid).")
            else:
                if args.skip_hash_check:
                     log("⚠️  Skipping hash check logic as requested.")
                else:
                     log("⚠️  No SHA256 to verify cache (on Soft Hit trusting local file).")
                
                log("⚠️  TRUSTING LOCAL FILE (Soft Hit).")
                filename = potential_cached_path
                used_cached_file = True

        if not used_cached_file:
            # Must download
            downloader.download_file(url, filename)
            
            # Verify download
            if scraped_sha256:
                calc_hash = verifier.verify_zip_sha256(filename, scraped_sha256)
                if not calc_hash: sys.exit(1)
                sha256 = calc_hash
            
            # Persist to OUTPUT_DIR
            if os.path.exists(OUTPUT_DIR) and not os.path.exists(potential_cached_path):
                try:
                    dest_path = os.path.join(OUTPUT_DIR, os.path.basename(filename))
                    shutil.copy2(filename, dest_path)
                except: pass

    # 3. Smart Caching Check (Skip Repack)
    abs_filename = os.path.abspath(filename)
    if not sha256:
        if used_cached_file and args.skip_hash_check:
            log("⚠️ Skipping SHA256 calc (User requested skip).")
            # Use filename as dummy hash to prevent breaking json logic if it allows arbitrary strings
            # But better to just use a marker. 
            sha256 = "TRUSTED_LOCAL_FILE"
        else:
            sha256 = verifier.calculate_sha256(abs_filename)
        
    # Smart Caching Check (moved from workspace)
    cached_output = verifier.check_smart_cache(sha256, key_hash)
    if cached_output:
        print_status("SMART SKIP", "PASS", f"Output {cached_output} already exists for this input. Skipping build.", Color.GREEN)
        sys.exit(0)

    # 4. Unpack & Verification - DEPRECATED / REMOVED
    # Since we use avbroot with OTA images, unpacking is redundant.
    # avbroot verifies the zip signature internally.
    # We rely on the initial SHA256 check of the ZIP download.
    log("ℹ️  Skipping legacy unpack/verify (avbroot handles integrity internally).")

    # 6. Patcher & Signing
    output_filename = f"ksu_patched_{os.path.basename(filename)}"
    
    try:
        avb_patcher.run_avbroot_patch(filename, output_filename, key_path)
    except Exception as e:
        sys.exit(1)

    # 7. Extract Images (for manual fastboot flash)
    # Extract to a subdirectory matching the zip name (minus extension)
    extraction_subdir = os.path.join(OUTPUT_DIR, os.path.splitext(os.path.basename(output_filename))[0])
    os.makedirs(extraction_subdir, exist_ok=True)
    
    avb_patcher.extract_patched_boot_images(output_filename, extraction_subdir)

    # 8. Custota
    avb_patcher.generate_custota_csig(output_filename, key_path)
    
    # 8. Report
    final_output_sha256 = verifier.calculate_sha256(output_filename)
    print(f"Final Visual Hash: {get_visual_hash(final_output_sha256)}")
    
    status = "success"
    now = datetime.now()
    
    build_info = {
        "build_meta": {
            "device": DEVICE_CODENAME,
            "date": datetime.utcnow().isoformat(),
            "status": status,
            "last_successful_build": now.strftime("%Y-%m-%d %H:%M:%S") if status == "success" else None,
            "mode": "Local File" if args.local_file else "Auto Download",
            "from_cache": used_cached_file,
            "key_hash": key_hash
        },
        "input": {
            "filename": os.path.basename(filename),
            "sha256": sha256,
            "google_signature_verified": True
        },
        "output": {
            "filename": output_filename,
            "sha256": final_output_sha256,
            "format": "flashable_update_zip",
            "usage": f"fastboot update {output_filename}",
            "signed_by": os.path.basename(key_path)
        }
    }
    
    with open(OUTPUT_JSON, "w") as f:
        json.dump(build_info, f, indent=4)
        
    print_status("DONE", "SUCCESS", f"Report saved to {OUTPUT_JSON}", Color.GREEN)

    # 9. Cloud Upload (if bucket defined)
    bucket_env = os.environ.get('BUCKET_NAME') or os.environ.get('_BUCKET_NAME')
    if bucket_env and storage:
        log("🚀 Starting Cloud Upload...")
        date_str = datetime.utcnow().strftime('%Y%m%d')
        # Structure: builds/{device}/{date}/{filename}
        
        # Upload ZIP
        zip_blob = f"builds/{DEVICE_CODENAME}/{date_str}/{os.path.basename(output_filename)}"
        if not upload_gcs_file(bucket_env, output_filename, zip_blob):
            log_error("Failed to upload ZIP file. Aborting.")
            sys.exit(1)
        
        # Upload CSIG
        csig_file = f"{output_filename}.csig"
        if os.path.exists(csig_file):
            if not upload_gcs_file(bucket_env, csig_file, f"{zip_blob}.csig"):
                log_error("Failed to upload CSIG file. Aborting.")
                sys.exit(1)
            
        # Upload JSON info
        if not upload_gcs_file(bucket_env, OUTPUT_JSON, f"builds/{DEVICE_CODENAME}/{date_str}/info.json"):
            log_error("Failed to upload JSON report. Aborting.")
            sys.exit(1)


if __name__ == "__main__":
    main()
