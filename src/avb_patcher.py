import os
import subprocess
import sys
from ui_utils import print_status, Color, log_error, log
from downloader import download_file

EXTRACTED_CACHE_DIR = "/app/output/extracted_cache"

def run_avbroot_patch(filename, output_filename, key_path, avb_passphrase=None):
    """
    Runs avbroot to patch and sign the firmware.
    """
    log("Passing to avbroot for patching and signing...")
    
    ksu_apk_path = os.path.join(EXTRACTED_CACHE_DIR, "kernelsu.apk")
    
    if not os.path.exists(ksu_apk_path):
        log("Downloading KernelSU Next...")
        ksu_url = "https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v1.0.3/KernelSU_Next_v1.0.3_11386_Release.apk"
        # Since downloader module needs to download to this path, ensuring directory exists
        os.makedirs(os.path.dirname(ksu_apk_path), exist_ok=True)
        download_file(ksu_url, ksu_apk_path)
    
    try:
         cmd = [
             "avbroot", "ota", "patch",
             "--input", filename, # Original ZIP
             "--output", output_filename,
             "--key", key_path,
             "--magisk", ksu_apk_path,
             "--rootless", "false"
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
         csig_path = f"{output_filename}.csig"
         subprocess.check_call([
             "custota-tool", "gen-csig",
             "--input", output_filename,
             "--key", key_path,
             "--output", csig_path
         ])
         print_status("CUSTOTA", "SUCCESS", "Signature generated", Color.GREEN)
    except Exception as e:
        log("⚠️  Custota tool failed or not found. Skipping metadata.")
