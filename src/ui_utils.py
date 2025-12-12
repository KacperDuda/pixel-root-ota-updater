
import sys
import time
import os

class Color:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    RED = '\033[0;31m'
    MAGENTA = '\033[0;35m'
    GRAY = '\033[0;90m'
    NC = '\033[0m'
    BOLD = '\033[1m'

def format_size(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

class ProgressBar:
    def __init__(self, desc, total=0, unit='B'):
        self.desc = desc
        self.total = total
        self.unit = unit
        self.processed = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        
        # Disable progress bar if not a TTY (e.g. Cloud Build logs)
        # We prefer a clean log in production
        self.enabled = sys.stdout.isatty() and not os.environ.get("CI")
        
        if self.enabled:
            # Initial print
            self._print_bar()
        else:
            # Simple log for production
            print(f"{desc}...")

    def update(self, amount):
        self.processed += amount
        if not self.enabled: return
        
        current_time = time.time()
        if current_time - self.last_update_time > 0.1 or (self.total > 0 and self.processed >= self.total):
            self.last_update_time = current_time
            self._print_bar()

    def _print_bar(self):
        if not self.enabled: return
        
        elapsed = time.time() - self.start_time
        speed_str = "..."
        if elapsed > 0:
            speed = self.processed / elapsed
            speed_str = f"{format_size(speed)}/s" if self.unit == 'B' else f"{speed:.2f}/s"

        percent_str = ""
        bar = ""
        
        if self.total > 0:
            percent = min(100.0, self.processed * 100 / self.total)
            percent_str = f"{percent:.1f}%"
            
            bar_len = 30
            filled = int(bar_len * percent // 100)
            bar = '█' * filled + '-' * (bar_len - filled)
            bar = f"|{bar}|"
        else:
            # removing indentation to fix aesthetics
            bar_len = 10
            # simple spinner or just size
            steps = ['-', '\\', '|', '/']
            idx = int(elapsed * 4) % 4
            bar = f"[{steps[idx]}]"
            percent_str = ""

        # Construct line
        # Template: [DESC] |BAR| PERCENT | PROCESSED/TOTAL | SPEED
        
        processed_fmt = format_size(self.processed) if self.unit == 'B' else str(self.processed)
        total_fmt = format_size(self.total) if self.unit == 'B' and self.total > 0 else (str(self.total) if self.total > 0 else "?")
        
        # Truncate description if too long (fix for line wrapping)
        desc_display = self.desc
        if len(desc_display) > 40:
            desc_display = desc_display[:20] + "..." + desc_display[-17:]

        # Clear line
        sys.stdout.write(f"\r{desc_display} {bar} {percent_str} {processed_fmt}/{total_fmt} {speed_str}\033[K")
        sys.stdout.flush()

    def finish(self):
        if self.enabled:
            self._print_bar()
            sys.stdout.write("\n")
            sys.stdout.flush()

def print_status(component, status, msg, color=Color.NC):
    """
    Format: [COMPONENT] [STATUS] Message
    """
    # Align status
    status_fmt = f"[{status}]"
    print(f"{Color.BOLD}[{component}]{Color.NC} {color}{status_fmt:<10}{Color.NC} {msg}")

def print_header(title):
    print(f"\n{Color.BOLD}{Color.CYAN}=== {title} ==={Color.NC}")

def print_step(n, total, title):
    print(f"\n{Color.YELLOW}[STEP {n}/{total}] {title}{Color.NC}")

def print_table(headers, data):
    """
    data is a list of lists.
    """
    col_widths = [len(h) for h in headers]
    
    # Calculate widths
    for row in data:
        for i, val in enumerate(row):
            # len() might be wrong with ansi codes, stripping for calc
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            text = ansi_escape.sub('', str(val))
            col_widths[i] = max(col_widths[i], len(text))
    
    # Add padding
    col_widths = [w + 2 for w in col_widths]
    
    # Header
    header_row = "".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
    print(f"{Color.GRAY}{'-' * len(header_row)}{Color.NC}")
    print(f"{Color.BOLD}{header_row}{Color.NC}")
    print(f"{Color.GRAY}{'-' * len(header_row)}{Color.NC}")
    
    for row in data:
        row_str = ""
        for i, val in enumerate(row):
            # We must pad manually because f-string padding counts ansi codes as length
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            text_len = len(ansi_escape.sub('', str(val)))
            padding = col_widths[i] - text_len
            row_str += f"{str(val)}{' ' * padding}"
        print(row_str)
    
    print(f"{Color.GRAY}{'-' * len(header_row)}{Color.NC}")

def get_visual_hash(sha256_hex):
    """
    Generates a unique, colorful, short visual representation of a SHA256 hash.
    Uses user requested symbols: @ # $ % & +
    """
    # Define symbols and colors
    symbols = ['@', '#', '$', '%', '&', '+']
    # Mapping colors: Red, Green, Yellow, Blue, Cyan, Magenta
    colors = [Color.RED, Color.GREEN, Color.YELLOW, Color.BLUE, Color.CYAN, '\033[0;35m']
    
    visual_str = ""
    
    # Process the hash byte by byte (2 hex chars)
    # We will take 16 bytes (32 hex chars) to form a 16-symbol visual hash.
    # We scan the string with stride 2.
    
    bytes_data = bytes.fromhex(sha256_hex)
    
    # Limit to 16 symbols for compactness as requested "shorter"
    
    for i in range(0, len(bytes_data), 2):
        # Actually loop 16 times max
        if i/2 >= 16: break
        
        b = bytes_data[i]
        
        sym_idx = b % len(symbols)
        col_idx = (b >> 3) % len(colors)
        
        visual_str += f"{colors[col_idx]}{symbols[sym_idx]}{Color.NC}"
        
    return visual_str

def log(msg):
    print_status("LOG", "INFO", msg, Color.BLUE)

def log_error(msg):
    print_status("LOG", "ERROR", msg, Color.RED)
