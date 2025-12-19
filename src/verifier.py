import os
import hashlib
import json
from ui_utils import print_status, Color, ProgressBar, log_error, log, get_visual_hash

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
    except Exception:
        pass
    return None

def check_smart_cache(input_sha256, key_content_sha256):
    """
    Checks if we already built this exact configuration successfully.
    """
    if not os.path.exists(OUTPUT_JSON): return False
    
    try:
        with open(OUTPUT_JSON, 'r') as f:
            data = json.load(f)
            
        last_status = data.get("build_meta", {}).get("status")
        if last_status != "success": return False
        
        last_input_sha = data.get("input", {}).get("sha256")
        if last_input_sha != input_sha256: return False
        
        output_filename = data.get("output", {}).get("filename")
        if not output_filename:
            return False
            
        # Check relative to CWD or absolute
        if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", output_filename)) and not os.path.exists(output_filename): 
             if not os.path.exists(output_filename): return False
        
        return output_filename
    except Exception:
        return False

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
        return calculated_hash 
    else:
        log_error(f"CHECKSUM MISMATCH! Expected: {expected_sha256}, Got: {calculated_hash}")
        return False
