# Quick Test Commands

## Test Fast Mode (Default)
```bash
docker run --rm -v "$(pwd)/output:/app/output" -v "$(pwd)/cyber_rsa4096_private.pem:/app/cyber_rsa4096_private.pem" pixel_builder
# Expected: ~30 seconds compression (store mode)
```

## Test Minimal ZIP
```bash
docker run --rm -v "$(pwd)/output:/app/output" -v "$(pwd)/cyber_rsa4096_private.pem:/app/cyber_rsa4096_private.pem" pixel_builder python3 pixel_automator.py --minimal
# Expected: ~3MB output (only init_boot.img + flash.sh)
```

## Test Work Area Cache HIT
```bash
# Run twice with same input
docker run ...
docker run ...  # Second run should show "WORK AREA UNCHANGED"
```

## What Changed

### 1. Fast Compression (DEFAULT)
- `-0` store mode = instant compression
- `--fast` flag (enabled by default via FAST_MODE=yes)
- 5 minutes → 30 seconds

### 2. Minimal Output
- `--minimal` flag creates tiny ZIP (~3MB)
- Contains: init_boot.img + flash.sh helper
- Perfect for quick flash testing

### 3. Work Area Caching
- Hashes init_boot.img state
- Reuses previous ZIP if unchanged
- Stores hash in build_status.json

### 4. vbmeta Clarification
```text
❗ vbmeta.img: STOCK (Google signature preserved)
❗ init_boot.img: MODIFIED (Custom AVB signature)
```

### 5. Progress Visibility
- All operations show progress
- Fast mode updates faster (no compression lag)
