```python
import os
import hashlib
import json
import zipfile
from ui_utils import print_status, Color, log, log_error, get_visual_hash

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
    print(f"Visual Hash: {get_visual_hash(calculated_sha256)}")
    
    if calculated_sha256.lower() == expected_sha256.lower():
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
    mapping_file = "/app/output/input_map.json"
    if not os.path.exists(mapping_file):
        return None
        
    try:
        with open(mapping_file, 'r') as f:
            mapping = json.load(f)
            
        composite_key = f"{input_file_sha}_{key_hash}"
        
        if composite_key in mapping:
            output_filename = mapping[composite_key]
            full_path = os.path.join("/app/output", output_filename)
            if os.path.exists(full_path):
                return output_filename
    except:
        pass
        
    return None

def update_smart_cache(input_file_sha, key_hash, output_filename):
    mapping_file = "/app/output/input_map.json"
    mapping = {}
    
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
        except: pass
        
    composite_key = f"{input_file_sha}_{key_hash}"
    mapping[composite_key] = output_filename
    
    try:
        with open(mapping_file, 'w') as f:
            json.dump(mapping, f, indent=4)
    except: pass
```
