#!/system/bin/sh

BUCKET="pixel10-frankel-builds"
LAST_HASH_FILE="/data/local/tmp/last_installed_hash"

# 1. Check for new hash in bucket
# (Assuming you have curl and a way to read the bucket, e.g., a public metadata file)
REMOTE_HASH=$(curl -s https://storage.googleapis.com/$BUCKET/last_seen_hash)

if [ -f "$LAST_HASH_FILE" ]; then
    LOCAL_HASH=$(cat $LAST_HASH_FILE)
else
    LOCAL_HASH=""
fi

if [ "$REMOTE_HASH" == "$LOCAL_HASH" ]; then
    echo "System up to date."
    exit 0
fi

echo "New update found: $REMOTE_HASH"

# 2. Download the signed OTA
# Since update_engine needs a seekable file or a perfect HTTP stream, 
# downloading to local storage is safest for custom setups.
cd /data/local/tmp
curl -o update.zip "https://storage.googleapis.com/$BUCKET/frankel-update-$REMOTE_HASH.zip"

# 3. Apply Update to Inactive Slot
# We need to extract payload_properties.txt for the headers
unzip -p update.zip payload_properties.txt > payload_properties.txt

# Read properties into variables for the command
FILE_HASH=$(grep FILE_HASH payload_properties.txt | cut -d= -f2)
FILE_SIZE=$(grep FILE_SIZE payload_properties.txt | cut -d= -f2)
METADATA_HASH=$(grep METADATA_HASH payload_properties.txt | cut -d= -f2)
METADATA_SIZE=$(grep METADATA_SIZE payload_properties.txt | cut -d= -f2)

echo "Applying update via update_engine..."

# The payload spec requires file:// URI
update_engine_client \
  --payload=file:///data/local/tmp/update.zip \
  --offset=$(unzip -v update.zip payload.bin | awk 'NR==2{print $1}') \
  --update \
  --headers="FILE_HASH=$FILE_HASH
FILE_SIZE=$FILE_SIZE
METADATA_HASH=$METADATA_HASH
METADATA_SIZE=$METADATA_SIZE"

# 4. Cleanup and Mark Done
if [ $? -eq 0 ]; then
    echo "Update applied successfully! Reboot to switch slots."
    echo "$REMOTE_HASH" > $LAST_HASH_FILE
    rm update.zip payload_properties.txt
    # Optional: reboot
else
    echo "Update failed."
fi