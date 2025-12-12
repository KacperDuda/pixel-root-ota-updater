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
                
                # USER REQUEST: If this is the nested image zip, copy it to output root too
                if member.filename.startswith("image-") and member.filename.endswith(".zip"):
                    print_status("ZIP", "INFO", f"Found inner image zip: {member.filename}", Color.BLUE)
                    # We assume dest_dir is .../extracted... so parent of that or ../output?
                    # The script puts extracted files in output/work_area mostly.
                    # We'll save it to the parent of dest_dir (usually output/)
                    inner_zip_dest = os.path.join(os.path.dirname(dest_dir), member.filename)
                    print_status("ZIP", "COPY", f"Saving inner zip to: {inner_zip_dest}", Color.GREEN)
                    
                    with z.open(member) as source, open(inner_zip_dest, "wb") as target:
                        # Copy stream
                        while True:
                            chunk = source.read(chunk_size)
                            if not chunk: break
                            target.write(chunk)
                            
                    # Continue to extract it normally to dest_dir (so other scripts find images)
                    # No, usually we extract contents OF this zip. But here we are extracting specific files FROM factory zip.
                    # If this is the image zip, we usually extract its CONTENTS.
                    # But the user wants the FILE itself.
                    # So we let the loop continue to extract it to work_area (default behavior) or whatever.
                    # The default extractor just extracts files. Using standard extraction logic below will extract it to dest_dir.

                    
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