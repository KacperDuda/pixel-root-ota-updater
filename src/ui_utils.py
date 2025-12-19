import sys
import time
import hashlib
from datetime import datetime

class Color:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    print(f"\n{Color.HEADER}{Color.BOLD}=== {text} ==={Color.RESET}\n")

def print_status(stage, status, message, color=Color.BLUE):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Color.CYAN}[{timestamp}]{Color.RESET} {Color.BOLD}{stage:<12}{Color.RESET} : {color}[{status}]{Color.RESET} {message}")

def log(message):
    print_status("INFO", "...", message, Color.RESET)

def log_error(message):
    print_status("ERROR", "FAIL", message, Color.RED)

def get_visual_hash(sha256_str):
    if not sha256_str: return "UNKNOWN"
    short_hash = sha256_str[:8]
    r = int(short_hash[:2], 16)
    g = int(short_hash[2:4], 16)
    b = int(short_hash[4:6], 16)
    
    # ANSI 256 color approximation
    return f"\033[38;2;{r};{g};{b}m█ █ █ {short_hash} █ █ █\033[0m"

class ProgressBar:
    def __init__(self, description, total=100):
        self.description = description
        self.total = total
        self.current = 0
        self.start_time = time.time()
        self._print_bar()

    def update(self, amount=1):
        self.current += amount
        if self.current > self.total: self.current = self.total
        self._print_bar()

    def _print_bar(self):
        percent = 100 * (self.current / float(self.total)) if self.total > 0 else 0
        filled_length = int(50 * self.current // self.total) if self.total > 0 else 0
        bar = '█' * filled_length + '-' * (50 - filled_length)
        
        elapsed = time.time() - self.start_time
        
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
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    for row in data:
        for i, val in enumerate(row):
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
    symbols = ['@', '#', '$', '%', '&', '+']
    # Mapping colors: Red, Green, Yellow, Blue, Cyan, Magenta
    colors = [Color.RED, Color.GREEN, Color.YELLOW, Color.BLUE, Color.CYAN, '\033[0;35m']
    
    visual_str = ""
    bytes_data = bytes.fromhex(sha256_hex)
    
    # Limit to 16 symbols for compactness as requested "shorter"
    for i in range(0, len(bytes_data), 2):
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
