import os
import shutil
import json
import hashlib
from ui_utils import print_status, Color, ProgressBar, log_error
import zip_extractor

OUTPUT_JSON = "build_status.json"
EXTRACTED_CACHE_DIR = "/app/output/extracted_cache"

def prepare_extracted_workspace(zip_path):
    """
    Centralized unpacking logic.
    Returns path to the directory containing extracted images (inner zip content).
    """
    base_name = os.path.splitext(os.path.basename(zip_path))[0]
    workspace_dir = os.path.join(EXTRACTED_CACHE_DIR, base_name)
    
    if os.path.exists(workspace_dir):
        # fast check
        if os.path.exists(os.path.join(workspace_dir, "init_boot.img")) or \
           os.path.exists(os.path.join(workspace_dir, "boot.img")):
            print_status("CACHE", "HIT", f"Using extracted cache: {workspace_dir}", Color.GREEN)
            return workspace_dir
    
    print_status("UNPACK", "START", f"Unpacking factory image to cache...", Color.YELLOW)
    
    temp_outer = os.path.join(EXTRACTED_CACHE_DIR, "temp_outer")
    if os.path.exists(temp_outer): shutil.rmtree(temp_outer)
    os.makedirs(temp_outer, exist_ok=True)
    
    zip_extractor.extract_with_progress(zip_path, temp_outer)
    
    inner_zip = None
    for root, dirs, files in os.walk(temp_outer):
        for f in files:
            if f.startswith("image-") and f.endswith(".zip"):
                inner_zip = os.path.join(root, f)
                break
    
    if not inner_zip:
        log_error("Could not find inner image zip!")
        import sys; sys.exit(1)
        
    os.makedirs(workspace_dir, exist_ok=True)
    zip_extractor.extract_with_progress(inner_zip, workspace_dir)
    
    shutil.rmtree(temp_outer)
    return workspace_dir

def check_smart_cache(input_sha256, key_content_sha256):
    """
    Checks if we have already built this exact configuration successfully.
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
        if not output_filename or not os.path.exists(output_filename): return False
        
        return output_filename
    except:
        return False
