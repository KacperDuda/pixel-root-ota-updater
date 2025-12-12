import os
import subprocess
import sys
import argparse
from ui_utils import ProgressBar, print_status, Color

def zip_directory_with_progress(source_dir, output_zip, compression_level=0):
    """
    Zip directory with progress tracking.
    
    Args:
        source_dir: Directory to compress
        output_zip: Output ZIP file path
        compression_level: 0 (store/fast) or 9 (max compression)
    """
    try:
        if not os.path.exists(source_dir):
            print_status("ZIP", "ERROR", f"Directory not found: {source_dir}", Color.RED)
            return False

        # Calculate total size for progress tracking
        print_status("ZIP", "INFO", f"Calculating total size of {source_dir}...")
        total_size = 0
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                filepath = os.path.join(root, file)
                if not os.path.islink(filepath):
                    total_size += os.path.getsize(filepath)
        
        # Use native zip command which has proper ZIP64 support
        comp_flag = "-0" if compression_level == 0 else "-9"
        comp_desc = "store" if compression_level == 0 else "max compression"
        print_status("ZIP", "INFO", f"Compressing ({comp_desc})...")
        
        # Make output_zip absolute BEFORE chdir
        output_zip = os.path.abspath(output_zip)
        
        # Change to source dir for cleaner paths
        original_cwd = os.getcwd()
        os.chdir(source_dir)
        
        # Remove old zip if exists
        if os.path.exists(output_zip):
            os.remove(output_zip)
        
        # Call native zip (supports ZIP64 automatically for large files)
        cmd = ['zip', '-r', comp_flag, '-q', output_zip, '.']
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Monitor progress by watching output file size
        bar = ProgressBar(f"Compressing {os.path.basename(output_zip)}", total=total_size)
        
        import time
        while process.poll() is None:
            time.sleep(0.5)
            if os.path.exists(output_zip):
                current_size = os.path.getsize(output_zip)
                # Compressed size as proxy for progress (not perfect but visible)
                bar.update(min(current_size, total_size) - bar.processed)
        
        # Final update
        if os.path.exists(output_zip):
            final_size = os.path.getsize(output_zip)
            bar.processed = total_size  # Force to 100%
        bar.finish()
        
        os.chdir(original_cwd)
        
        if process.returncode != 0:
            stderr = process.stderr.read().decode()
            print_status("ZIP", "ERROR", f"Zip failed: {stderr}", Color.RED)
            return False
        
        return True

    except Exception as e:
        print_status("ZIP", "ERROR", f"Exception during zip creation: {e}", Color.RED)
        try:
            os.chdir(original_cwd)
        except:
            pass
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    parser.add_argument("output_zip")
    parser.add_argument("--fast", action="store_true", help="Use store mode (no compression)")
    args = parser.parse_args()
    
    comp_level = 0 if args.fast else 9
    if not zip_directory_with_progress(args.source_dir, args.output_zip, comp_level):
        sys.exit(1)
