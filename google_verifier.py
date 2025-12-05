
import sys
import subprocess
import argparse
import os

def main():
    # The original script had an issue with argument parsing.
    # This version correctly accepts a positional argument for the file path.
    parser = argparse.ArgumentParser(description='Verify Google Factory Image.')
    parser.add_argument('image_path', help='Path to the factory image zip file.')
    args = parser.parse_args()

    image_path = args.image_path
    if not os.path.exists(image_path):
        print(f"❌ ERROR: File not found at '{image_path}'")
        sys.exit(1)

    # We need to extract vbmeta.img from the zip archive first.
    # The verifier works on vbmeta.img, not the whole zip.
    print(f"INFO: Unzipping '{image_path}' to find vbmeta.img...")
    
    # Create a temporary directory to extract to
    import tempfile
    import zipfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        vbmeta_path = None
        try:
            with zipfile.ZipFile(image_path, 'r') as zip_ref:
                # We need to find the inner zip file, e.g., image-frankel-bd1a.250702.001.zip
                inner_zip_name = None
                for name in zip_ref.namelist():
                    if 'image-' in name and name.endswith('.zip'):
                        inner_zip_name = name
                        break
                
                if not inner_zip_name:
                    print("❌ ERROR: Could not find the inner image zip file.")
                    sys.exit(1)

                # Extract the inner zip
                inner_zip_path = zip_ref.extract(inner_zip_name, path=temp_dir)
                
                # Now extract all images from the inner zip
                with zipfile.ZipFile(inner_zip_path, 'r') as inner_zip_ref:
                    inner_zip_ref.extractall(path=temp_dir)
                    vbmeta_path = os.path.join(temp_dir, 'vbmeta.img')
                    if not os.path.exists(vbmeta_path):
                        print("❌ ERROR: vbmeta.img not found in the inner archive.")
                        sys.exit(1)

                print(f"INFO: Found vbmeta.img at {vbmeta_path}")

                # Now, run avbtool verify_image.
                # No --key is needed since the public key is embedded in vbmeta.
                print("INFO: Running avbtool.py to verify vbmeta.img...")
                avbtool_path = '/usr/local/bin/avbtool.py'
                cmd = ['python3', avbtool_path, 'verify_image', '--image', vbmeta_path, '--follow_chain_partitions']
                
                print(f"EXEC: {' '.join(cmd)}")
                process = subprocess.run(cmd, capture_output=True, text=True)

                if process.returncode == 0:
                    print("✅ Verification successful.")
                    # The output of verify_image contains details, print them.
                    print(process.stdout)
                    sys.exit(0)
                else:
                    print("❌ ERROR: Verification failed!")
                    print("STDOUT:", process.stdout)
                    print("STDERR:", process.stderr)
                    sys.exit(1)

        except zipfile.BadZipFile:
            print(f"❌ ERROR: '{image_path}' is not a valid zip file.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ An unexpected error occurred: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
