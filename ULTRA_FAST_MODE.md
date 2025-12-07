# Ultra-Fast Mode Usage

## Speed Comparison

| Mode | Time | Output | Use Case |
|------|------|--------|----------|
| Normal | ~6 min | 8.4GB ZIP | Archive/backup |
| Fast (default) | ~2 min | 8.4GB ZIP | Quick rebuild |
| Minimal | ~1 min | 3MB ZIP | Testing |
| **Raw** | **~45 sec** | **3MB .img** | **Production flash** |

## Raw Output Mode (FASTEST)

```bash
docker run --rm \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/cyber_rsa4096_private.pem:/app/cyber_rsa4096_private.pem" \
  pixel_builder \
  python3 pixel_automator.py --raw-output
```

**Output:**
- `init_boot_ksu_frankel...img` (3MB)
- `avb_custom_public.bin` (AVB public key)

**Time:** ~45 seconds total!

## Flash Instructions

### Unlocked Bootloader (Safe)
```bash
fastboot flash init_boot_a init_boot_ksu_*.img
fastboot flash init_boot_b init_boot_ksu_*.img
fastboot reboot
```

### Locked Bootloader (Advanced)
```bash
# 1. Program custom AVB key (one-time!)
fastboot flash avb_custom_key avb_custom_public.bin

# 2. Flash patched init_boot
fastboot flash init_boot_a init_boot_ksu_*.img
fastboot flash init_boot_b init_boot_ksu_*.img

# 3. Lock bootloader
fastboot flashing lock

# 4. Reboot
fastboot reboot
```

**⚠️ CRITICAL:** `avb_custom_key` MUST be flashed BEFORE `flashing lock`!

## Safety

✅ **With OEM Unlock ON:**
- ALWAYS recoverable
- `fastboot flashing unlock` → restore stock

❌ **With OEM Unlock OFF + Wrong Key:**
- Permanent brick
- NO recovery possible

## Recommendation

1. Test with **unlocked BL** first
2. Verify KernelSU works
3. Only then consider locking with custom key
4. **NEVER** disable OEM unlock until 100% confident
