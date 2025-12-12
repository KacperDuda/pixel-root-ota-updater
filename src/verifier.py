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
    
    bar = ProgressBar(f"Hashing {os.path.basename(filename)}", total=file_size)
    
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
    Checks verification.json or runs google_verifier.
    """
    verification_stat_file = os.path.join(extracted_workspace, "verification.json")
    
    if os.path.exists(verification_stat_file):
        try:
            with open(verification_stat_file, 'r') as vf:
                vdata = json.load(vf)
            if vdata.get("zip_sha256") == zip_sha256 and vdata.get("status") == "OK":
                log("✅ Stock images already verified. Skipping re-verification.")
                return True
        except: pass
        
    # Run Google Verifier
    log("🛡️  Verifying Google Signatures (In-Place)...")
    
    # We can try importing and running direct, IF we trust it doesn't sys.exit(1) implicitly on us in a bad way.
    # google_verifier.main() has sys.exit calls.
    # But verify_vbmeta(path) returns True/False.
    
    vbmeta_path = os.path.join(extracted_workspace, "vbmeta.img")
    # Search if not found direct
    if not os.path.exists(vbmeta_path):
        for root, dirs, files in os.walk(extracted_workspace):
            if "vbmeta.img" in files:
                vbmeta_path = os.path.join(root, "vbmeta.img")
                break
                
    if not os.path.exists(vbmeta_path):
        log_error("vbmeta.img not found for verification!")
        return False

    if google_verifier.verify_vbmeta(vbmeta_path):
        # Save success
        try:
            with open(verification_stat_file, 'w') as vf:
                json.dump({
                    "zip_sha256": zip_sha256,
                    "verified_at": datetime.utcnow().isoformat(),
                    "status": "OK"
                }, vf)
        except: pass
        return True
    else:
        return False
