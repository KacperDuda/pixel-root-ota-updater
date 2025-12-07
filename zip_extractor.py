import sys
import os
import zipfile
import argparse
import time
from ui_utils import ProgressBar, print_status, Color

def extract_with_progress(zip_path, dest_dir, member_name=None):
    try:
        if not os.path.exists(zip_path):
            print_status("ZIP", "ERROR", f"File not found: {zip_path}", Color.RED)
            return False

        with zipfile.ZipFile(zip_path, 'r') as z:
            if member_name:
                try:
                    members = [z.getinfo(member_name)]
                except KeyError:
                    print_status("ZIP", "ERROR", f"File {member_name} not found in archive.", Color.RED)
                    return False
            else:
                members = z.infolist()

            total_size = sum(m.file_size for m in members)
            
            # Simple caching check: if single file and already exists with same size?
            # For now, we trust the caller (automator) to handle high-level caching.
            # But low-level: overwrite.

            chunk_size = 1024 * 1024 # 1MB
            
            bar = ProgressBar(f"Extracting {os.path.basename(zip_path)}", total=total_size)

            for member in members:
                if member.is_dir(): continue
                    
                target_path = os.path.join(dest_dir, member.filename)
                target_dir = os.path.dirname(target_path)
                if target_dir: os.makedirs(target_dir, exist_ok=True)

                with z.open(member) as source, open(target_path, "wb") as target:
                    while True:
                        chunk = source.read(chunk_size)
                        if not chunk: break
                        target.write(chunk)
                        bar.update(len(chunk))
            
            bar.finish()
            return True

    except Exception as e:
        print_status("ZIP", "ERROR", f"Exception: {e}", Color.RED)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_file")
    parser.add_argument("dest_dir")
    parser.add_argument("--file", default=None)
    args = parser.parse_args()
    
    os.makedirs(args.dest_dir, exist_ok=True)
    if not extract_with_progress(args.zip_file, args.dest_dir, args.file):
        sys.exit(1)