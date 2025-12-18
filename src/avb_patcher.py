import os
import subprocess
import sys
from ui_utils import print_status, Color, log_error, log


EXTRACTED_CACHE_DIR = "/app/output/extracted_cache"

def run_avbroot_patch(filename, output_filename, key_path, avb_passphrase=None):
    """
    Runs avbroot to patch and sign the firmware.
    """
    log("Passing to avbroot for patching and signing...")
    
    # Use pre-bundled Magisk from Docker image
    magisk_path = "/usr/local/share/magisk.zip"
    
    if not os.path.exists(magisk_path):
        log_error(f"CRITICAL: Pre-bundled Magisk not found at {magisk_path}")
        sys.exit(1)
    
    # Prepare keys and certs for avbroot v3.23+
    # Write cert to /tmp/ because key_path directory might be read-only (Cloud Run Secret Volume)
    cert_filename = os.path.basename(key_path).replace(".pem", ".crt").replace(".key", ".crt")
    if cert_filename == os.path.basename(key_path): cert_filename += ".crt"
    cert_path = os.path.join("/tmp", cert_filename)
    
    if not os.path.exists(cert_path):
        log(f"Generating OTA certificate from key: {cert_path}")
        try:
            # Generate self-signed cert from private key (non-interactive)
            subprocess.check_call([
                "openssl", "req", "-new", "-x509", 
                "-key", key_path, 
                "-out", cert_path, 
                "-days", "10000", 
                "-subj", "/CN=PixelRootOTA"
            ])
        except Exception as e:
            log_error(f"Failed to generate certificate: {e}")
            sys.exit(1)

    # Validation: avbroot --magisk expects a specific ZIP structure (assets/util_functions.sh)
    # Magisk APKs are ZIPs themselves and usually valid.
    import zipfile
    try:
        with zipfile.ZipFile(magisk_path, 'r') as z:
            if "assets/util_functions.sh" not in z.namelist():
                # Some Magisk versions or other root zips might differ, but official Magisk has this.
                # If we switched to real Magisk, we expect this to pass now.
                log_error("❌ ERROR: Provided file is not a standard Magisk Installer.")
                log_error(f"File: {magisk_path}")
                log_error("Missing 'assets/util_functions.sh'. Please ensure you are using official Magisk v27.0+.")
                sys.exit(1)
            else:
                log("✅ Verified Magisk structure (assets/util_functions.sh found).")
    except zipfile.BadZipFile:
        log_error(f"❌ ERROR: File is not a valid ZIP: {magisk_path}")
        sys.exit(1)

    try:
         cmd = [
             "avbroot", "ota", "patch",
             "--input", filename,
             "--output", output_filename,
             "--key-avb", key_path,
             "--key-ota", key_path,
             "--cert-ota", cert_path,
             "--magisk", magisk_path,
             "--magisk-preinit-device", "metadata"
         ]
         
         if avb_passphrase:
             os.environ["AVBROOT_PASSPHRASE"] = avb_passphrase
         elif "AVB_PASSPHRASE" in os.environ:
             os.environ["AVBROOT_PASSPHRASE"] = os.environ["AVB_PASSPHRASE"]

         log(f"Running avbroot: {' '.join(cmd)}")
         subprocess.check_call(cmd)
         print_status("PATCH", "SUCCESS", "avbroot completed", Color.GREEN)
         
    except Exception as e:
        log_error(f"avbroot failed: {e}")
        # Re-raise to let orchestrator handle exit
        raise e

def generate_custota_csig(output_filename, key_path):
    log("Generating Custota metadata...")
    try:
         cert_filename = os.path.basename(key_path).replace(".pem", ".crt").replace(".key", ".crt")
         if cert_filename == os.path.basename(key_path): cert_filename += ".crt"
         cert_path = os.path.join("/tmp", cert_filename)
         
         csig_path = f"{output_filename}.csig"
         subprocess.check_call([
             "custota-tool", "gen-csig",
             "--input", output_filename,
             "--key", key_path,
             "--cert", cert_path,
             "--output", csig_path
         ])
         print_status("CUSTOTA", "SUCCESS", "Signature generated", Color.GREEN)
    except Exception as e:
         subprocess.check_call([
             "custota-tool", "gen-csig",
             "--input", output_filename,
             "--key", key_path,
             "--cert", cert_path,
             "--output", csig_path
         ])
         print_status("CUSTOTA", "SUCCESS", "Signature generated", Color.GREEN)
    except Exception as e:
        log("⚠️  Custota tool failed or not found. Skipping metadata.")

def generate_custota_json(output_filename, csig_filename, device_codename, url_prefix, output_json_path):
    log("Generating Custota JSON...")
    # custota-tool gen-update-info --location <url_to_zip> --file <json_file>
    # The tool updates the file if it exists, or creates it.
    
    zip_url = f"{url_prefix}/{os.path.basename(output_filename)}"
    
    try:
        # Create empty file if not exists to ensure tool works (if it expects existing)
        # Actually it likely creates it.
        
        subprocess.check_call([
            "custota-tool", "gen-update-info",
            "--location", zip_url,
            "--file", output_json_path
        ])
        print_status("CUSTOTA", "SUCCESS", f"JSON generated: {output_json_path}", Color.GREEN)
    except Exception as e:
         log_error(f"Failed to generate Custota JSON: {e}")

def extract_patched_boot_images(zip_path, output_dir):
    """
    Extracts init_boot.img and boot.img from the patched OTA zip.
    """
    log("Extracting patched boot images...")
    try:
        subprocess.check_call([
            "avbroot", "ota", "extract",
            "--input", zip_path,
            "--directory", output_dir
        ])
        print_status("EXTRACT", "SUCCESS", "Boot images extracted", Color.GREEN)
    except Exception as e:
        log_error(f"Failed to extract images: {e}")
        # Non-critical, do not exit
