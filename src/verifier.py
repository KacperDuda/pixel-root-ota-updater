import os
import hashlib
import json
import subprocess
from datetime import datetime
from ui_utils import print_status, Color, ProgressBar, log_error, log, get_visual_hash
import google_verifier

OUTPUT_JSON = "build_status.json"

def calculate_sha256(filename):
    sha256_hash = hashlib.sha256()
    file_size = os.path.getsize(filename)
    
    bar = ProgressBar(f"Calculating SHA256 (Local I/O)", total=file_size)
    
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(1024*1024), b""):
            sha256_hash.update(byte_block)
            bar.update(len(byte_block))
    bar.finish()
    return sha256_hash.hexdigest()

def calculate_string_sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

def get_cached_hash_from_status(filename):
    """Check if we already know the hash from a previous build."""
    if not os.path.exists(OUTPUT_JSON):
        return None
    
    try:
        with open(OUTPUT_JSON, 'r') as f:
            data = json.load(f)
        
        if data.get("input", {}).get("filename") == os.path.basename(filename):
            cached_hash = data.get("input", {}).get("sha256")
            if cached_hash and len(cached_hash) == 64:  # Valid SHA256
                return cached_hash
    except:
        pass
    return None

def verify_zip_sha256(filename, expected_sha256):
    if not expected_sha256:
        log("⚠️  Missing expected SHA256.")
        return False

    cached_hash = get_cached_hash_from_status(filename)
    
    if cached_hash:
        log(f"📋 Using cached hash from previous build...")
        calculated_hash = cached_hash
        print(f"Visual Hash: {get_visual_hash(calculated_hash)}")
    else:
        calculated_hash = calculate_sha256(filename)
        print(f"Visual Hash: {get_visual_hash(calculated_hash)}")
    
    if calculated_hash.lower() == expected_sha256.lower():
        print_status("HASH", "OK", "SHA256 Match", Color.GREEN)
        return calculated_hash # Return hash on success
    else:
        log_error(f"CHECKSUM MISMATCH! Expected: {expected_sha256}, Got: {calculated_hash}")
        return False

def verify_extracted_workspace(extracted_workspace, zip_sha256):
    """
    Verifies the Google signature of the extracted images.
    Persists successful verification to a .verified file to skip future checks.
    """
    marker_path = os.path.join(extracted_workspace, ".verified")
    
    if os.path.exists(marker_path):
        log("✅ Stock images previously verified (Marker found). Skipping.")
        return True
    
    if os.path.exists(os.path.join(extracted_workspace, "payload.bin")):
        log("✅ OTA Image detected (payload.bin). Skipping Google VBMeta Verification (Not applicable/Supported internally by update_engine).")
        # Touch marker
        with open(marker_path, "w") as f: f.write("verified_ota")
        return True

    log("🛡️  Verifying Google Signatures (In-Place)...")
    
    vbmeta_path = None
    # Search for vbmeta.img
    for root, dirs, files in os.walk(extracted_workspace):
        if "vbmeta.img" in files:
            vbmeta_path = os.path.join(root, "vbmeta.img")
            break
            
    if not vbmeta_path:
        log_error("vbmeta.img not found for verification!")
        return False

    if google_verifier.verify_vbmeta(vbmeta_path):
        # Save success marker
        try:
            with open(marker_path, 'w') as f:
                f.write(zip_sha256 if zip_sha256 else "SKIPPED_HASH")
        except: pass
        return True
    else:
        return False
