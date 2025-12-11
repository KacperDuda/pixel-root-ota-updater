#!/bin/bash
# Generate AVB Public Key from Private Key
set -e

PRIVATE_KEY="cyber_rsa4096_private.pem"
PUBLIC_KEY_PEM="cyber_rsa4096_public.pem"
PUBLIC_KEY_BIN="cyber_rsa4096_public.bin"

echo "=== AVB Public Key Generator ==="
echo ""

# Check if private key exists
if [ ! -f "$PRIVATE_KEY" ]; then
    echo "❌ Private key not found: $PRIVATE_KEY"
    exit 1
fi

echo "📋 Found private key: $PRIVATE_KEY"
echo ""

# 1. Extract public key in PEM format
echo "🔑 Step 1/2: Extracting public key (PEM format)..."
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY_PEM"
echo "   ✅ Created: $PUBLIC_KEY_PEM"
echo ""

# 2. Convert to AVB binary format
echo "🔑 Step 2/2: Converting to AVB binary format..."

# Use local avbtool.py
if [ -f "avbtool.py" ]; then
    python3 avbtool.py extract_public_key --key "$PUBLIC_KEY_PEM" --output "$PUBLIC_KEY_BIN"
else
    echo "❌ avbtool.py not found in current directory"
    exit 1
fi

echo "   ✅ Created: $PUBLIC_KEY_BIN"
echo ""

# Show key info
echo "=== Generated Keys ==="
ls -lh cyber_rsa4096_public.*
echo ""

echo "✅ AVB keys ready!"
echo ""
echo "📋 Files created:"
echo "   1. $PUBLIC_KEY_PEM  - Human readable (for verification)"
echo "   2. $PUBLIC_KEY_BIN  - AVB binary (for fastboot flash)"
echo ""
echo "ℹ️  Note: With UNLOCKED bootloader, AVB key is ignored"
echo "   Custom key only matters when bootloader is LOCKED"
echo ""
echo "Next steps:"
echo "  ./flash_ksu.sh    # Flash KernelSU (AVB key will be flashed but unused)"
