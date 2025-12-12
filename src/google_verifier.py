
import os
import sys
import subprocess
import re
from ui_utils import print_status, print_header, ProgressBar, Color, get_visual_hash

AVBTOOL = "/usr/local/bin/avbtool.py"
if not os.path.exists(AVBTOOL):
    AVBTOOL = "avbtool.py"

def log(msg):
    print_status("VERIFY", "INFO", msg, Color.BLUE)

def log_error(msg):
    print_status("VERIFY", "ERROR", msg, Color.RED)

def parse_chain(output):
    """
    Parses avbtool verify_image output to extract chain links AND signature details.
    """
    chain_info = {
        'vbmeta_sig': None,
        'vbmeta_key': None,
        'chained_partitions': []
    }
    
    # Extract vbmeta signature info
    # Look for "vbmeta: Successfully verified SHA256_RSA4096..."
    if "Successfully verified" in output:
        alg_match = re.search(r"Successfully verified (\S+) vbmeta", output)
        if alg_match:
            chain_info['vbmeta_sig'] = alg_match.group(1)
    
    # Extract public key if shown
    key_match = re.search(r"Public key \(sha1\):\s+([a-f0-9]+)", output)
    if key_match:
        chain_info['vbmeta_key'] = key_match.group(1)
    
    # Chained partition descriptors
    blocks = output.split("Chained partition descriptor:")
    for block in blocks[1:]:
        info = {}
        part_match = re.search(r"Partition Name:\s+(\w+)", block)
        key_match = re.search(r"Public key \(sha1\):\s+([a-f0-9]+)", block)
        
        if part_match: info['partition'] = part_match.group(1)
        if key_match: info['key_sha1'] = key_match.group(1)
        
        if info: chain_info['chained_partitions'].append(info)
        
    return chain_info

def visualize_chain(chain_info):
    print(f"\n{Color.BOLD}{Color.MAGENTA}=== Chain of Trust ==={Color.NC}")
    print(f"{Color.RED}Google Root Key{Color.NC}")
    print(f"{Color.GRAY}     |{Color.NC}")
    print(f"{Color.GRAY}     v{Color.NC}")
    
    # vbmeta signature
    sig_type = chain_info.get('vbmeta_sig', 'SHA256_RSA4096')
    vbmeta_key = chain_info.get('vbmeta_key')
    
    print(f"{Color.GREEN}vbmeta.img{Color.NC} (Verified via {Color.CYAN}{sig_type}{Color.NC})")
    
    if vbmeta_key:
        vhash = get_visual_hash(vbmeta_key.ljust(64, '0'))
        print(f"{Color.GRAY}     ↳ Public Key: {Color.NC}{vbmeta_key[:16]}... {vhash}")
    
    chained = chain_info.get('chained_partitions', [])
    
    if not chained:
        print(f"{Color.GRAY}     |{Color.NC}")
        print(f"{Color.GRAY}     v{Color.NC}")
        print(f"{Color.YELLOW}(No chained partitions found - Direct validation){Color.NC}")
        return

    for i, link in enumerate(chained):
        is_last = (i == len(chained) - 1)
        branch = "└──" if is_last else "├──"
        
        part = link.get('partition', 'unknown')
        key_short = link.get('key_sha1', '???')[:8]
        
        vhash = get_visual_hash(link.get('key_sha1', '00').ljust(64, '0'))
        
        print(f"{Color.GRAY}     {branch} {Color.NC}{Color.CYAN}{part}{Color.NC}")
        print(f"{Color.GRAY}     {'    ' if is_last else '|   '} ↳ Key: {Color.NC}{key_short}... {vhash}")

def verify_vbmeta(path):
    log(f"Verifying {os.path.basename(path)}...")
    
    if not os.path.exists(path):
        log_error("vbmeta.img not found!")
        return False

    dest_dir = os.path.dirname(path)
    cmd = f"python3 {AVBTOOL} verify_image --image \"{path}\" --follow_chain_partitions"
    
    try:
        # Capture output for visualization
        # We need to run this command in the directory where images are, so avbtool finds them?
        # avbtool usually looks in CWD or same dir?
        # It looks for files in the same directory as the image if --follow_chain_partitions is used.
        # But let's be safe and CWD to that dir.
        
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=dest_dir)
        
        # Show progress spinner while verifying
        bar = ProgressBar("Verifying Chain", unit=' step')
        output_accum = ""
        
        while True:
            char = process.stdout.read(1)
            if not char and process.poll() is not None:
                break
            if char:
                output_accum += char.decode('utf-8', errors='ignore')
                # Update spinner occasionally
                if len(output_accum) % 100 == 0: bar.update(1)
        
        bar.finish()
        
        if process.returncode == 0:
            print_status("VERIFY", "OK", "Signature verified successfully.", Color.GREEN)
            
            chain_info = parse_chain(output_accum)
            visualize_chain(chain_info)
            return True
        else:
            log_error("Signature Verification Failed!")
            print(output_accum)
            return False
            
    except Exception as e:
        log_error(f"Execution error: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: google_verifier.py <directory_or_zip>")
        sys.exit(1)

    target_path = sys.argv[1]
    
    print_header("GOOGLE SIGNATURE VERIFICATION")
    
    vbmeta_path = None
    
    if os.path.isdir(target_path):
        # Scan for vbmeta.img
        potential = os.path.join(target_path, "vbmeta.img")
        if os.path.exists(potential):
            vbmeta_path = potential
        else:
            # Maybe inside images subdirectory (extracted structure often has subdirs)
            for root, dirs, files in os.walk(target_path):
                if "vbmeta.img" in files:
                    vbmeta_path = os.path.join(root, "vbmeta.img")
                    break
    
    if not vbmeta_path:
        # If passed a zip, extraction logic is handled by automator now.
        # But for standalone usage compatibility:
        log("No directory or vbmeta found. Assuming Zip not implemented here anymore.")
        log_error("Please pass extracted workspace directory.")
        sys.exit(1)
        
    if not verify_vbmeta(vbmeta_path):
        sys.exit(1)

if __name__ == "__main__":
    main()
