import os
import sys
import json
import argparse
import shutil
from datetime import datetime, timezone
import time
import subprocess

try:
    from google.cloud import storage
    from google.cloud import monitoring_v3
except ImportError:
    storage = None
    monitoring_v3 = None

from ui_utils import print_header, print_status, log, log_error, Color, get_visual_hash
import downloader
import verifier
import avb_patcher

DEVICE_CODENAME = os.environ.get('_DEVICE_CODENAME', 'frankel')
OUTPUT_JSON = "build_status.json"
DEFAULT_KEY_NAME = "cyber_rsa4096_private.pem"
KEY_SEARCH_PATHS = [
    "/app/secrets/cyber_rsa4096_private.pem",
    f"/app/{DEFAULT_KEY_NAME}",
    DEFAULT_KEY_NAME
]
OUTPUT_DIR = "/app/output"

def report_failure_metric(error_reason="unknown"):
    if not monitoring_v3:
        return

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return

    log(f"📈 Reporting failure metric to Stackdriver (Reason: {error_reason})...")
    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        series = monitoring_v3.TimeSeries()
        series.metric.type = "custom.googleapis.com/pixel_automator/build_failures"
        series.resource.type = "global"
        series.metric.labels["device"] = DEVICE_CODENAME
        series.metric.labels["reason"] = str(error_reason)[:64]

        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)
        interval = monitoring_v3.TimeInterval(
            {"end_time": {"seconds": seconds, "nanos": nanos}}
        )

        point = monitoring_v3.Point({"interval": interval, "value": {"int64_value": 1}})
        series.points = [point]

        client.create_time_series(name=project_name, time_series=[series])
    except Exception as e:
        log_error(f"Failed to push metric: {e}")

def report_success_metric():
    if not monitoring_v3: return

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id: return

    log("📈 Reporting success metric to Stackdriver...")
    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        series = monitoring_v3.TimeSeries()
        series.metric.type = "custom.googleapis.com/pixel_automator/build_success"
        series.resource.type = "global"
        series.metric.labels["device"] = DEVICE_CODENAME
        
        # Point
        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)
        interval = monitoring_v3.TimeInterval({"end_time": {"seconds": seconds, "nanos": nanos}})
        point = monitoring_v3.Point({"interval": interval, "value": {"int64_value": 1}})
        series.points = [point]

        client.create_time_series(name=project_name, time_series=[series])
    except Exception as e:
        log_error(f"Failed to push success metric: {e}")

def debug_paths():
    log("🔍 Debugging Key Paths:")
    if os.path.exists("/app/secrets"):
        log(f"   /app/secrets exists. Contents: {os.listdir('/app/secrets')}")
    else:
        log("   /app/secrets does NOT exist.")

    if os.path.exists("/app"):
        files = os.listdir("/app")
        log(f"   /app contents (partial): {files[:10]}")

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

def verify_bucket_access(bucket_name):
    if not bucket_name or not storage:
        return

    log(f"🔍 Checking access to GCS Bucket: {bucket_name}")
    try:
        client = storage.Client()
        client.bucket(bucket_name)
        # Check Read/List
        blobs = client.list_blobs(bucket_name, max_results=1)
        for _ in blobs: pass

        # Check Write
        bucket = client.bucket(bucket_name)
        test_blob_name = f"access_check_{int(time.time())}.tmp"
        blob = bucket.blob(test_blob_name)
        blob.upload_from_string("write_test")
        blob.delete()

        log(f"✅ Bucket '{bucket_name}' verified.")
    except Exception as e:
        log_error(f"❌ CRITICAL failure accessing bucket '{bucket_name}': {e}")
        report_failure_metric("bucket_access_failed")
        sys.exit(1)

def extract_and_upload_public_key(bucket_name, private_key_path):
    if not bucket_name or not storage:
        return

    public_key_blob = "keys/avb_pkmd.bin"
    log(f"🔑 Checking if Public Key exists in bucket: {public_key_blob}")

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(public_key_blob)

        if blob.exists():
            log("   Public Key already exists in cloud. Skipping generation.")
            return

        log("   Public Key missing. generating from Private Key...")
        output_path = "/tmp/avb_pkmd.bin"

        cmd = [
            "/usr/local/bin/avbtool.py", "extract_public_key",
            "--key", private_key_path,
            "--output", output_path
        ]

        subprocess.check_call(cmd)

        if os.path.exists(output_path):
            log(f"   Uploading generated Public Key to {public_key_blob}...")
            upload_gcs_file(bucket_name, output_path, public_key_blob)
            log("✅ Public Key published successfully.")
        else:
            log_error("Failed to generate Public Key (file not found after command).")

    except Exception as e:
        log_error(f"Failed to publish Public Key: {e}")

def get_bucket_env():
    return os.environ.get('BUCKET_NAME') or os.environ.get('_BUCKET_NAME')

def check_cloud_index(bucket_env, filename):
    if not bucket_env or not storage:
        return False
        
    log("🔎 Checking Cloud Index for existing build...")
    try:
        index_filename = "builds_index.json"
        if download_gcs_file(bucket_env, index_filename, index_filename):
            with open(index_filename, 'r') as f:
                indices = json.load(f)
            
            expected_output = f"ksu_patched_{filename}"
            for entry in indices:
                if entry.get("filename") == expected_output:
                    log(f"✅ Build already exists in Cloud Index: {expected_output}")
                    return True
    except Exception as e:
        log(f"⚠️  Index check failed (ignoring): {e}")
    return False

def manage_cache_download(cache_bucket_env, filename, scraped_sha256):
    if not cache_bucket_env:
        return False
        
    log(f"🕵️  Checking Cloud Cache for: {filename}")
    try:
        client = storage.Client()
        c_bucket = client.bucket(cache_bucket_env)
        blob = c_bucket.blob(filename)
        if blob.exists():
            log(f"⚡ CLOUD CACHE HIT! Downloading from GCS...")
            blob.download_to_filename(filename)
            log("✅ Download from Cache complete.")
            return True
    except Exception as e:
        log(f"⚠️  Cache lookup failed: {e}")
    return False

def resolve_key_path(local_key):
    if local_key:
        if os.path.exists(local_key): 
            return os.path.abspath(local_key)
        sys.exit(1)
        
    debug_paths()
    for path in KEY_SEARCH_PATHS:
        if os.path.exists(path):
            log(f"🔑 Found key at: {path}")
            return path
            
    # Fallback to GCS fetch
    bucket_env = get_bucket_env()
    if bucket_env and storage:
        log(f"Key not found locally. Attempting fetch from bucket: {bucket_env}")
        key_blob = f"keys/{DEFAULT_KEY_NAME}"
        fetched_key_path = os.path.join("/app", DEFAULT_KEY_NAME)
        if download_gcs_file(bucket_env, key_blob, fetched_key_path):
            return fetched_key_path
        else:
            log_error(f"Could not fetch key from GCS.")
            report_failure_metric("key_fetch_failed")
            sys.exit(1)
            
    log_error(f"Key not found: {DEFAULT_KEY_NAME}")
    report_failure_metric("key_not_found_local")
    sys.exit(1)

def update_central_index(bucket_env, output_filename, zip_blob_path, filename):
    index_filename = "builds_index.json"
    log("update_build_index: Downloading existing index...")
    
    current_index = []
    if download_gcs_file(bucket_env, index_filename, index_filename):
        try:
            with open(index_filename, "r") as f:
                current_index = json.load(f)
        except:
            current_index = []
    
    new_entry = {
        "device": DEVICE_CODENAME,
        "android_version": os.path.basename(filename).split('-')[2] if len(os.path.basename(filename).split('-')) > 2 else "unknown",
        "build_date": datetime.now(timezone.utc).strftime('%Y%m%d'),
        "filename": os.path.basename(output_filename),
        "url": f"https://storage.googleapis.com/{bucket_env}/{zip_blob_path}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    current_index = [x for x in current_index if x.get("filename") != new_entry["filename"]]
    current_index.append(new_entry)
    current_index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    with open(index_filename, "w") as f:
        json.dump(current_index, f, indent=4)
        
    upload_gcs_file(bucket_env, index_filename, index_filename)
    log("✅ Central index updated.")

def update_local_index(filename, output_filename):
    date_str = datetime.now(timezone.utc).strftime('%Y%m%d')
    local_index_path = os.path.join(OUTPUT_DIR, "builds_index.json")
    local_index = []
    
    if os.path.exists(local_index_path):
        try:
            with open(local_index_path, 'r') as f:
                local_index = json.load(f)
        except: pass

    new_local_entry = {
        "device": DEVICE_CODENAME,
        "android_version": os.path.basename(filename).split('-')[2] if len(os.path.basename(filename).split('-')) > 2 else "unknown",
        "build_date": date_str,
        "filename": os.path.basename(output_filename),
        "url": f"/builds/{os.path.basename(output_filename)}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    local_index = [x for x in local_index if x.get("filename") != new_local_entry["filename"]]
    local_index.append(new_local_entry)
    local_index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    with open(local_index_path, "w") as f:
        json.dump(local_index, f, indent=4)
        
    log(f"✅ Local build index updated: {local_index_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-file', help='Local ZIP file')
    parser.add_argument('--local-key', help='Local Key')
    parser.add_argument('--minimal', action='store_true', help='Create minimal ZIP (only modified files)')
    parser.add_argument('--fast', action='store_true', help='Use fast compression (store mode)')
    parser.add_argument('--raw-output', action='store_true', help='Skip ZIP, output raw init_boot.img only (fastest)')
    parser.add_argument('--skip-hash-check', action='store_true', help='Skip local SHA256 calculation if file exists')
    args = parser.parse_args()

    print_header("PIXEL AUTO-PATCHER START")

    bucket_env = get_bucket_env()
    verify_bucket_access(bucket_env)
    
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
    used_cached_file = False
    
    key_path = resolve_key_path(args.local_key)
    
    with open(key_path, 'r') as kf:
        key_content = kf.read()
    key_hash = verifier.calculate_string_sha256(key_content)
    
    if bucket_env and storage:
        extract_and_upload_public_key(bucket_env, key_path)

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
            report_failure_metric("url_fetch_failed")
            sys.exit(1)

        filename = scraped_filename
        
        if not args.local_file and check_cloud_index(bucket_env, filename):
            log("🎉 Nothing to do. Exiting.")
            sys.exit(0)

        potential_cached_path = os.path.join(OUTPUT_DIR, scraped_filename)
        
        if os.path.exists(potential_cached_path):
            log(f"💾 Found in cache: {potential_cached_path}")
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
                log("⚠️  TRUSTING LOCAL FILE (Soft Hit).")
                filename = potential_cached_path
                used_cached_file = True

        if not used_cached_file:
            cloud_cache_hit = manage_cache_download(cache_bucket_env, filename, scraped_sha256)

            if not cloud_cache_hit:
                downloader.download_file(url, filename)
                if cache_bucket_env:
                     log(f"📦 Populating Cloud Cache with {filename}...")
                     upload_gcs_file(cache_bucket_env, filename, filename)
            
            if scraped_sha256:
                calc_hash = verifier.verify_zip_sha256(filename, scraped_sha256)
                if not calc_hash: 
                    report_failure_metric("shasum_mismatch")
                    sys.exit(1)
                sha256 = calc_hash
            
            if os.path.exists(OUTPUT_DIR) and not os.path.exists(potential_cached_path):
                try:
                    dest_path = os.path.join(OUTPUT_DIR, os.path.basename(filename))
                    shutil.copy2(filename, dest_path)
                except: pass

    abs_filename = os.path.abspath(filename)
    if not sha256:
        if used_cached_file and args.skip_hash_check:
            log("⚠️ Skipping SHA256 calc (User requested skip).")
            sha256 = "TRUSTED_LOCAL_FILE"
        else:
            sha256 = verifier.calculate_sha256(abs_filename)
        
    cached_output = verifier.check_smart_cache(sha256, key_hash)
    if cached_output:
        print_status("SMART SKIP", "PASS", f"Output {cached_output} already exists. Skipping build.", Color.GREEN)
        sys.exit(0)

    output_filename = f"ksu_patched_{os.path.basename(filename)}"
    
    try:
        avb_patcher.run_avbroot_patch(filename, output_filename, key_path)
    except Exception as e:
        log_error(f"Patching failed: {e}")
        report_failure_metric("avb_patch_failed")
        sys.exit(1)

    try:
        if os.path.exists(filename) and filename != output_filename:
            log(f"🧹 freeing space: removing input file {filename}")
            os.remove(filename)
    except: pass

    extraction_subdir = os.path.join(OUTPUT_DIR, os.path.splitext(os.path.basename(output_filename))[0])
    os.makedirs(extraction_subdir, exist_ok=True)
    
    avb_patcher.extract_patched_boot_images(output_filename, extraction_subdir)

    avb_patcher.generate_custota_csig(output_filename, key_path)
    
    final_output_sha256 = verifier.calculate_sha256(output_filename)
    print(f"Final Visual Hash: {get_visual_hash(final_output_sha256)}")
    
    custota_json_name = f"{DEVICE_CODENAME}.json"
    csig_path = f"{output_filename}.csig"
    avb_patcher.generate_custota_json(output_filename, csig_path, DEVICE_CODENAME, ".", custota_json_name)
    
    build_info = {
        "build_meta": {
             "device": DEVICE_CODENAME,
             "status": "success",
             "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "output": {
            "filename": output_filename,
            "sha256": final_output_sha256,
            "csig": csig_path
        }
    }
    
    with open(OUTPUT_JSON, "w") as f:
        json.dump(build_info, f, indent=4)
        
    print_status("DONE", "SUCCESS", f"Report saved to {OUTPUT_JSON} and {custota_json_name}", Color.GREEN)

    if bucket_env and storage:
        log("🚀 Starting Cloud Upload...")
        date_str = datetime.now(timezone.utc).strftime('%Y%m%d')
        base_prefix = f"builds/{DEVICE_CODENAME}/{date_str}"
        zip_blob_path = f"{base_prefix}/{os.path.basename(output_filename)}"
        
        if not upload_gcs_file(bucket_env, output_filename, zip_blob_path):
            log_error("Failed to upload ZIP file. Aborting.")
            report_failure_metric("zip_upload_failed")
            sys.exit(1)
        
        csig_file = f"{output_filename}.csig"
        if os.path.exists(csig_file):
            upload_gcs_file(bucket_env, csig_file, f"{zip_blob_path}.csig")
            
        upload_gcs_file(bucket_env, OUTPUT_JSON, f"{base_prefix}/info.json")

        if os.path.exists(extraction_subdir):
            log(f"☁️  Uploading extracted images from {extraction_subdir}...")
            extracted_prefix = f"{base_prefix}/{os.path.basename(extraction_subdir)}"
            client = storage.Client()
            bucket = client.bucket(bucket_env)
            
            for root, dirs, files in os.walk(extraction_subdir):
                for file in files:
                    local_path = os.path.join(root, file)
                    rel_path = os.path.relpath(local_path, extraction_subdir)
                    blob_path = f"{extracted_prefix}/{rel_path}"
                    bucket.blob(blob_path).upload_from_filename(local_path)
                    print(f"   -> Uploaded: {rel_path}")
            log("✅ Extracted images uploaded.")

        public_img_url = f"https://storage.googleapis.com/{bucket_env}/{base_prefix}/{os.path.basename(extraction_subdir)}/init_boot.img"
        latest_json_content = {
            "date": date_str,
            "id": os.path.basename(output_filename),
            "image_url": public_img_url
        }
        
        with open("latest.json", "w") as f:
            json.dump(latest_json_content, f)
            
        upload_gcs_file(bucket_env, "latest.json", "latest.json")
        update_central_index(bucket_env, output_filename, zip_blob_path, filename)
        report_success_metric()

    update_local_index(filename, output_filename)

if __name__ == "__main__":
    main()
