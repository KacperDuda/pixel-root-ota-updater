import sys
import os
import zipfile
import argparse
import time

def format_size(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

def extract_with_progress(zip_path, dest_dir, member_name=None):
    """
    Wypakowuje plik(i) z ZIPa z paskiem postępu i prędkością.
    """
    try:
        if not os.path.exists(zip_path):
            print(f"❌ Błąd: Plik nie istnieje: {zip_path}")
            return False

        with zipfile.ZipFile(zip_path, 'r') as z:
            if member_name:
                try:
                    members = [z.getinfo(member_name)]
                except KeyError:
                    print(f"❌ Plik {member_name} nie istnieje w archiwum.")
                    return False
            else:
                members = z.infolist()

            total_size = sum(m.file_size for m in members)
            processed_global = 0
            chunk_size = 1024 * 1024 # 1MB
            start_time = time.time()
            last_update_time = start_time

            print(f"📦 Rozpakowywanie {os.path.basename(zip_path)}...")

            for member in members:
                if member.is_dir(): continue
                    
                target_path = os.path.join(dest_dir, member.filename)
                target_dir = os.path.dirname(target_path)
                if target_dir: os.makedirs(target_dir, exist_ok=True)

                short_name = os.path.basename(member.filename)
                if len(short_name) > 20: short_name = short_name[:17] + "..."

                with z.open(member) as source, open(target_path, "wb") as target:
                    while True:
                        chunk = source.read(chunk_size)
                        if not chunk: break
                        target.write(chunk)
                        processed_global += len(chunk)
                        
                        # Aktualizuj UI co ~0.1s żeby nie spamować konsoli
                        current_time = time.time()
                        if current_time - last_update_time > 0.1 or processed_global == total_size:
                            last_update_time = current_time
                            elapsed = current_time - start_time
                            speed_str = "..."
                            if elapsed > 0:
                                speed = processed_global / elapsed
                                speed_str = f"{format_size(speed)}/s"

                            if total_size > 0:
                                percent = processed_global * 100 / total_size
                                bar_len = 25
                                filled = int(bar_len * percent // 100)
                                bar = '█' * filled + '-' * (bar_len - filled)
                                
                                # \033[K czyści resztę linii (zapobiega śmieciom przy zmianie długości nazw)
                                sys.stdout.write(f"\r   |{bar}| {percent:.1f}% | {speed_str} | {short_name}\033[K")
                                sys.stdout.flush()
            print() 
            return True

    except Exception as e:
        print(f"\n❌ Wyjątek przy rozpakowywaniu: {e}")
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