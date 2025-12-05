# Pixel Firmware Automator

This project automates the process of patching stock Google Pixel firmware images to include KernelSU and signing them with a custom AVB key. The entire workflow is designed to be executed within a CI/CD pipeline, specifically Google Cloud Build.

The process creates a modified update zip that can be flashed to a Pixel device with an unlocked bootloader, effectively rooting the device while maintaining a verifiable boot chain with a custom key.

## Summary of Referenced Files

This is a summary of the files used by `Dockerfile` and `cloudbuild.yaml`.

*   **`cloudbuild.yaml`**: The main orchestrator for the Google Cloud Build pipeline. It defines the build steps, from fetching secrets to building the Docker container and uploading the final artifacts.
*   **`Dockerfile`**: Defines the containerized environment where the patching process runs. It installs all necessary system dependencies (like `openjdk`, `zip`) and Python packages, and copies the application scripts.
*   **`entrypoint.sh`**: The main entrypoint for the Docker container. It executes the main Python script (`pixel_automator.py`) and handles the final output files.
*   **`pixel_automator.py`**: The core Python script that likely drives the automation. It is responsible for fetching the stock firmware and orchestrating the patching process by calling other scripts.
*   **`patcher.sh`**: A bash script that performs the core logic of patching the boot image. It unpacks the firmware, injects the KernelSU module (`kernelsu.ko`) into the ramdisk, and re-signs the image.
*   **`google_verifier.py`**: A Python script likely used to verify the authenticity of the downloaded stock firmware from Google's servers.
*   **`zip_extractor.py`**: A helper script to extract specific files from the nested zip archives found in Pixel firmware packages.
*   **`requirements.txt`**: A standard Python requirements file listing the necessary packages to be installed in the Docker container.
*   **`cyber_rsa4096_private.pem`**: The TEST AND TEMPORARY private key used by `avbtool` to sign the modified boot image. This file is fetched from a secure location (like Google Cloud Storage) during the build process.

## Workflow Overview

1.  **Trigger**: The process is initiated by a Google Cloud Build trigger.
2.  **Setup**: Cloud Build fetches the `cyber_rsa4096_private.pem` key from a GCS bucket.
3.  **Build**: A Docker image is built using the provided `Dockerfile`. This image contains all the necessary tools (`magiskboot`, `avbtool`, Python environment) and scripts.
4.  **Execution**: The Docker container is run.
    *   `entrypoint.sh` starts the `pixel_automator.py` script.
    *   `pixel_automator.py` downloads the target stock firmware for a specific device.
    *   It then calls `patcher.sh` to modify the firmware.
5.  **Patching**: The `patcher.sh` script:
    *   Unpacks the initial firmware zip to find the inner `image-*.zip`.
    *   Extracts the `init_boot.img` or `boot.img`.
    *   Downloads the specified `kernelsu.ko` module.
    *   Uses `magiskboot` to unpack the boot image's ramdisk, add the `kernelsu.ko` module, and repack it.
    *   Uses `avbtool.py` to sign the newly modified boot image with the custom `cyber_rsa4096_private.pem` key.
    *   Repackages the modified boot image into a new firmware zip file.
6.  **Upload**: The final `ksu_patched_*.zip` artifact and a `build_status.json` file are uploaded back to a GCS bucket.
