import os
import hashlib
import json
import os
import zipfile
from ui_utils import print_status, Color, log, log_error

def calculate_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def calculate_string_sha256(string_data):
    return hashlib.sha256(string_data.encode('utf-8')).hexdigest()

def verify_zip_sha256(filepath, expected_sha256):
    log(f"Verifying SHA256 for {os.path.basename(filepath)}...")
    calculated_sha256 = calculate_sha256(filepath)
    if calculated_sha256 == expected_sha256:
        print_status("VERIFY", "SUCCESS", "SHA256 Match", Color.GREEN)
        return calculated_sha256
    else:
        log_error(f"SHA256 Mismatch! Expected: {expected_sha256}, Got: {calculated_sha256}")
        return None

def verify_zip_integrity(filepath):
    log(f"Verifying integrity of ZIP: {filepath}")
    if not zipfile.is_zipfile(filepath):
        log_error("File is not a valid ZIP.")
        return False
    try:
        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            ret = zip_ref.testzip()
            if ret is not None:
                log_error(f"First bad file in zip: {ret}")
                return False
        return True
    except Exception as e:
        log_error(f"ZIP integrity check error: {e}")
        return False

def check_smart_cache(input_file_sha, key_hash): 
    # Use output directory to look for previous builds
    # Logic:
    # 1. We keep a local 'builds_index.json' or similiar metadata
    # 2. Or we parse filenames? No, filenames don't store input hash.
    # 3. We can look at a special mapping file: input_map.json
    
    mapping_file = "/app/output/input_map.json"
    if not os.path.exists(mapping_file):
        return None
        
    try:
        with open(mapping_file, 'r') as f:
            mapping = json.load(f)
            
        # Key format: input_hash + key_hash (if key changes, output changes)
        composite_key = f"{input_file_sha}_{key_hash}"
        
        if composite_key in mapping:
            output_filename = mapping[composite_key]
            full_path = os.path.join("/app/output", output_filename)
            if os.path.exists(full_path):
                return output_filename
    except:
        pass
        
    return None

        calculated_hash = calculate_sha256(filename)
        print(f"Visual Hash: {get_visual_hash(calculated_hash)}")
    
    if calculated_hash.lower() == expected_sha256.lower():
        print_status("HASH", "OK", "SHA256 Match", Color.GREEN)
        return calculated_hash 
    else:
        log_error(f"CHECKSUM MISMATCH! Expected: {expected_sha256}, Got: {calculated_hash}")
        return False
