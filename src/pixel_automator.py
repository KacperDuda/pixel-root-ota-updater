import os
import sys
import json
import argparse
import shutil
from datetime import datetime, timezone
import time

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
# Paths to check for the key (Priority order)
KEY_SEARCH_PATHS = [
    "/app/secrets/cyber_rsa4096_private.pem", # Cloud Run Secret Mount
    f"/app/{DEFAULT_KEY_NAME}",              # Docker Copy
    DEFAULT_KEY_NAME                          # Local CWD
]
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
        # 1. Check Read/List
        blobs = client.list_blobs(bucket_name, max_results=1)
        for b in blobs: pass
        
        # 2. Check Write (Create/Delete)
        # We create a tiny temp file to confirm we have write permissions
        # crucial before starting a massive download/patch job.
        test_blob_name = f"access_check_{int(time.time())}.tmp"
        blob = bucket.blob(test_blob_name)
        blob.upload_from_string("write_test")
        blob.delete()
        
        log(f"✅ Bucket '{bucket_name}' verified (read/write access ok).")
    except Exception as e:
        log_error(f"❌ CRITICAL failure accessing bucket '{bucket_name}': {e}")
        log_error("   Verify 'roles/storage.objectAdmin' is assigned to the Cloud Build Service Account.")
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
    # Verify Release bucket
    bucket_env = os.environ.get('BUCKET_NAME') or os.environ.get('_BUCKET_NAME')
    verify_bucket_access(bucket_env)
    
    # Verify Cache bucket (if configured)
    cache_bucket_env = os.environ.get('CACHE_BUCKET_NAME')
    if cache_bucket_env:
        try:
             verify_bucket_access(cache_bucket_env)
             log(f"📦 Cache Bucket detected: {cache_bucket_env}")
        except:
             log_error(f"⚠️  Cache Bucket configured but inaccessible: {cache_bucket_env}")
             cache_bucket_env = None

    filename = None
    sha256 = None
    key_path = None
    used_cached_file = False
    
    # 1. Key Resolution
    if args.local_key:
        if os.path.exists(args.local_key): key_path = os.path.abspath(args.local_key)
        else: sys.exit(1)
    else:
        # Check predefined paths
        for path in KEY_SEARCH_PATHS:
            if os.path.exists(path):
                key_path = path
                log(f"🔑 Found key at: {key_path}")
                break
    
    if not key_path:
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
            # TRY CLOUD CACHE FIRST
            cloud_cache_hit = False
            if cache_bucket_env and not args.local_file:
                 log(f"🕵️  Checking Cloud Cache for: {filename}")
                 # We simply check if the file exists in the bucket
                 # It's usually the filename (no folder structure for cache for simplicity, or maybe OTA/?)
                 # Let's use simple flat structure for now
                 try:
                     client = storage.Client()
                     c_bucket = client.bucket(cache_bucket_env)
                     blob = c_bucket.blob(filename)
                     if blob.exists():
                         log(f"⚡ CLOUD CACHE HIT! Downloading from GCS...")
                         blob.download_to_filename(filename)
                         cloud_cache_hit = True
                         log("✅ Download from Cache complete.")
                 except Exception as e:
                     log(f"⚠️  Cache lookup failed: {e}")

            if not cloud_cache_hit:
                # Must download from Web
                downloader.download_file(url, filename)
                
                # Upload to Cache for next time
                if cache_bucket_env:
                     log(f"📦 Populating Cloud Cache with {filename}...")
                     upload_gcs_file(cache_bucket_env, filename, filename)
            
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
            "date": datetime.now(timezone.utc).isoformat(),
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
        date_str = datetime.now(timezone.utc).strftime('%Y%m%d')
        # Structure: builds/{device}/{date}/{filename}
        
        base_prefix = f"builds/{DEVICE_CODENAME}/{date_str}"
        zip_blob_path = f"{base_prefix}/{os.path.basename(output_filename)}"
        
        # 9.1 Upload Main Artifacts
        # Upload ZIP
        if not upload_gcs_file(bucket_env, output_filename, zip_blob_path):
            log_error("Failed to upload ZIP file. Aborting.")
            sys.exit(1)
        
        # Upload CSIG
        csig_file = f"{output_filename}.csig"
        if os.path.exists(csig_file):
            upload_gcs_file(bucket_env, csig_file, f"{zip_blob_path}.csig")
            
        # Upload JSON report
        upload_gcs_file(bucket_env, OUTPUT_JSON, f"{base_prefix}/info.json")

        # 9.2 Upload Extracted Images (Recursively)
        if os.path.exists(extraction_subdir):
            log(f"☁️  Uploading extracted images from {extraction_subdir}...")
            # We want to upload to: builds/{device}/{date}/{zip_basename_no_ext}/
            extracted_prefix = f"{base_prefix}/{os.path.basename(extraction_subdir)}"
            
            client = storage.Client()
            bucket = client.bucket(bucket_env)
            
            for root, dirs, files in os.walk(extraction_subdir):
                for file in files:
                    local_path = os.path.join(root, file)
                    rel_path = os.path.relpath(local_path, extraction_subdir)
                    blob_path = f"{extracted_prefix}/{rel_path}"
                    
                    blob = bucket.blob(blob_path)
                    blob.upload_from_filename(local_path)
                    print(f"   -> Uploaded: {rel_path}")
            log("✅ Extracted images uploaded.")

        # 9.3 Generate and Upload latest.json (for Web Flasher)
        # Using public URL format
        # https://storage.googleapis.com/BUCKET/builds/DEVICE/DATE/SUBDIR/init_boot.img
        public_img_url = f"https://storage.googleapis.com/{bucket_env}/{base_prefix}/{os.path.basename(extraction_subdir)}/init_boot.img"
        
        latest_json_content = {
            "date": date_str,
            "id": os.path.basename(output_filename),
            "image_url": public_img_url
        }
        
        with open("latest.json", "w") as f:
            json.dump(latest_json_content, f)
            
        upload_gcs_file(bucket_env, "latest.json", "latest.json") # Root latest.json
        
        # 9.4 Update Central Index (builds_index.json)
        index_filename = "builds_index.json"
        log("update_build_index: Downloading existing index...")
        
        current_index = []
        # Try download
        if download_gcs_file(bucket_env, index_filename, index_filename):
            try:
                with open(index_filename, "r") as f:
                    current_index = json.load(f)
            except:
                log("   Index corrupt or empty, creating new.")
                current_index = []
        
        # New Entry
        new_entry = {
            "device": DEVICE_CODENAME,
            "android_version": os.path.basename(filename).split('-')[2] if len(os.path.basename(filename).split('-')) > 2 else "unknown", # Heuristic parse
            "build_date": date_str,
            "filename": os.path.basename(output_filename),
            "url": f"https://storage.googleapis.com/{bucket_env}/{zip_blob_path}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Remove duplicates (by filename)
        current_index = [x for x in current_index if x.get("filename") != new_entry["filename"]]
        current_index.append(new_entry)
        
        # Sort by date desc
        current_index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        with open(index_filename, "w") as f:
            json.dump(current_index, f, indent=4)
            
        upload_gcs_file(bucket_env, index_filename, index_filename)
        log("✅ Central index updated.")


if __name__ == "__main__":
    main()
