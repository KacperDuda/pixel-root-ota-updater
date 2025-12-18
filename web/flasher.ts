import * as Fastboot from 'android-fastboot';
import { FastbootDevice } from 'android-fastboot';
import { performUnlock, flashCustomKey, performLock } from './flash-actions';
import { log } from './ui-utils';
import { AdbService } from './adb-service';
import { SideloadService } from './sideload-service';

export interface ValidatedFiles {
    zipUrl: string | null;
    key: Blob | null;
}

export interface FlasherConfig {
    unlock: boolean;
    flashKey: boolean;
    flashZip: boolean;
    lock: boolean;
    wipeData: boolean;
    autoReboot: boolean;
}

/**
 * === MAIN ORCHESTRATOR ===
 */
export async function runWebFlasher(config: FlasherConfig, files: ValidatedFiles, existingDevice?: FastbootDevice) {
    // Instantiate via imported library OR use existing
    const device = existingDevice || new Fastboot.FastbootDevice();

    try {
        if (!existingDevice) {
            log("Connecting to USB device...");
            await device.connect();
        } else {
            log("Using existing connection...", "info");
        }

        const product = await device.getVariable('product');
        log(`Connected: ${product}`, "success");

        if (config.unlock) {
            await performUnlock(device);
        }

        if (config.flashKey && files.key) {
            await flashCustomKey(device, files.key);
        }

        if (config.flashZip && files.zipUrl) {
            log(`Downloading System Image from Cloud...`);
            log(files.zipUrl);

            try {
                // Extract filename from URL to use as cache key
                const zipFilename = files.zipUrl.split('/').pop() || 'firmware.zip';

                const root = await navigator.storage.getDirectory();
                const fileHandle = await root.getFileHandle(zipFilename, { create: true });

                // CACHING LOGIC
                let useCache = false;
                try {
                    const existingFile = await fileHandle.getFile();
                    if (existingFile.size > 0) {
                        // Check remote size (HEAD request)
                        const headResp = await fetch(files.zipUrl, { method: 'HEAD' });
                        const remoteSizeStr = headResp.headers.get('content-length');
                        const remoteSize = remoteSizeStr ? parseInt(remoteSizeStr, 10) : 0;

                        // Trust cache if size matches (approximate check for small diffs due to sector reporting etc)
                        if (remoteSize > 0 && Math.abs(existingFile.size - remoteSize) < 1024) {
                            useCache = true;
                            log(`Using cached firmware: ${zipFilename}. Skipping download.`, "success");
                        }
                    }
                } catch (e) {
                    // Ignore error, proceed to download
                }

                if (!useCache) {
                    const response = await fetch(files.zipUrl);
                    if (!response.ok) throw new Error(`Download failed: ${response.statusText}`);

                    const contentLength = response.headers.get('content-length');
                    const total = contentLength ? parseInt(contentLength, 10) : 0;
                    let loaded = 0;

                    // Re-create writable to truncate/overwrite
                    const writable = await fileHandle.createWritable();

                    const reader = response.body?.getReader();
                    if (!reader) throw new Error("Browser does not support streaming download.");


                    log(`Download started. Total size: ${(total / 1024 / 1024).toFixed(2)} MB`);

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        if (value) {
                            await writable.write(value);
                            loaded += value.length;

                            if (total > 0) {
                                const percentNum = (loaded / total) * 100;

                                // Update UI Bar
                                const bar = document.getElementById('progress-bar') as HTMLProgressElement;
                                if (bar) bar.value = percentNum;
                            }
                        }
                    }

                    await writable.close();
                    log("Download complete and flushed to storage.", "success");
                }

                const file = await fileHandle.getFile();
                log(`Firmware Ready. Size: ${(file.size / 1024 / 1024).toFixed(2)} MB`, "success");

                // RESET BAR for Flashing Phase
                const bar = document.getElementById('progress-bar') as HTMLProgressElement;
                if (bar) bar.value = 0;

                log("Verifying device connection before flashing...", "info");
                try {
                    // Check if connection is still alive
                    await device.getVariable('product');
                } catch (e) {
                    log("Connection appears stale (timeout?). Reconnecting...", "info");
                    try {
                        await device.connect();
                        log("Reconnected successfully.", "success");
                    } catch (connErr: any) {
                        throw new Error("Failed to reconnect after download: " + connErr.message);
                    }
                }

                log(`Starting Firmware Flash (Wipe: ${config.wipeData})...`, "info");

                // --- ZIP HEADER CHECK ---
                // Validate it's actually a ZIP (PK..) before passing to library
                const headerSlice = file.slice(0, 4);
                const headerArr = new Uint8Array(await headerSlice.arrayBuffer());
                const headerHex = Array.from(headerArr).map(b => b.toString(16).padStart(2, '0')).join('');
                log(`ZIP Header Check: ${headerHex} (Expected: 504b0304 or similar)`);

                if (headerArr[0] !== 0x50 || headerArr[1] !== 0x4B) {
                    throw new Error(`Invalid ZIP Header (${headerHex}). Download might be corrupt or 404/500 text.`);
                }

                // --- MANUAL FLASHING SEQUENCE (zip.js) ---
                log("Unzipping Factory Image (Streamed)...", "info");
                const zip = await import('@zip.js/zip.js');

                // Use BlobReader for efficient random access without OOM
                const reader = new zip.ZipReader(new zip.BlobReader(file));
                const entries = await reader.getEntries();

                // DEBUG: Log all filenames to see structure
                log(`Zip Entries Found (${entries.length}):`);
                entries.slice(0, 10).forEach(e => log(` - ${e.filename}`));
                if (entries.length > 10) log(` - ... and ${entries.length - 10} more`);

                // 0. OTA GUARD
                if (entries.some(e => e.filename === 'payload.bin' || e.filename.endsWith('/payload.bin'))) {
                    log("OTA Image Detected (payload.bin). Switching to Sideload Mode...", "info");

                    // 1. AUTO REBOOT TO RECOVERY
                    try {
                        log("Auto-rebooting to Recovery...", "info");
                        await device.runCommand('reboot-recovery');
                    } catch (e: any) {
                        // If fails, user might be in recovery already or disconnected
                        log(`Auto-reboot hint: ${e.message}`, "info");
                    }

                    const adbService = new AdbService();

                    try {
                        log("Waiting for device/ADB...", "info");
                        log("NOTE: 'No Command' screen? -> Hold Power + Tap Vol Up.", "error");

                        // SHOW MANUAL CONTROLS
                        const controls = document.getElementById('sideload-controls');
                        const btnManual = document.getElementById('btn-sideload-manual');
                        if (controls) controls.style.display = 'block';

                        let connected = false;

                        const tryConnect = async (device: USBDevice) => {
                            try {
                                log("Connecting to ADB interface...", "info");
                                await adbService.connect(device);
                                connected = true;
                                if (controls) controls.style.display = 'none';
                            } catch (e: any) {
                                log(`Connect failed: ${e.message}`, "error");
                            }
                        };

                        if (btnManual) {
                            btnManual.onclick = async () => {
                                try {
                                    const usbDevice = await navigator.usb.requestDevice({
                                        filters: [{ classCode: 255, subclassCode: 66, protocolCode: 1 }]
                                    });
                                    await tryConnect(usbDevice);
                                } catch (e) { }
                            };
                        }

                        // POLL Loop (180s)
                        for (let i = 0; i < 180; i++) {
                            if (connected) break;
                            const devices = await navigator.usb.getDevices();
                            const candidate = devices.find(d =>
                                d.vendorId === 0x18d1 &&
                                (d.productId === 0x4ee7 || d.configuration?.interfaces.some(iface =>
                                    iface.alternates[0].interfaceClass === 255 &&
                                    iface.alternates[0].interfaceSubclass === 66 &&
                                    iface.alternates[0].interfaceProtocol === 1
                                ))
                            );
                            if (candidate) await tryConnect(candidate);
                            await new Promise(r => setTimeout(r, 1000));
                        }

                        if (btnManual) btnManual.onclick = null;
                        if (controls) controls.style.display = 'none';

                        if (!connected) throw new Error("ADB Device not found. Use 'Connect Manually'.");

                        // AUTO-REBOOT Check (if accidentally in normal ADB)
                        // ADB Sideload usually doesn't allow shell commands, but "recovery" does?
                        // If we are in "sideload", shell fails. 
                        // If we are in "device", we can reboot.
                        try {
                            // Try a harmless command to see if we have shell access
                            // If we are in 'sideload' mode, this throws "closed" or similar?
                            // Actually, sideloadService opens a specific socket.
                            // Let's just proceed to Sideload. If it fails, user handles it.
                        } catch (e) { }

                        // Sideload
                        const sideloadService = new SideloadService(adbService.adb!);
                        await sideloadService.sideload(file);

                        log("✅ Sideload Complete!", "success");

                        // -------------------------------------------------
                        // POST-FLASH VALIDATION FLOW
                        // -------------------------------------------------

                        // 1. Reboot to System
                        // 1. Reboot to System
                        try {
                            log("Rebooting to System for Verification...", "info");
                            await adbService.rebootSystem();
                        } catch (e) {
                            log("Reboot command sent.", "info");
                        }

                        // Disconnect ADB
                        try { await adbService.dispose(); } catch (e) { }

                        // 2. Verified Modal
                        log("Waiting for User Verification...", "info");
                        const verifyModal = document.getElementById('verify-boot-modal');
                        const verifyBtn = document.getElementById('btn-verify-done');
                        if (verifyModal) verifyModal.classList.add('is-active');

                        await new Promise<void>(resolve => {
                            if (verifyBtn) verifyBtn.onclick = () => {
                                if (verifyModal) verifyModal.classList.remove('is-active');
                                resolve();
                            };
                        });

                        // 3. Re-Connect Fastboot
                        log("Waiting for Bootloader connection...", "info");
                        let fastbootDev: FastbootDevice | null = null;

                        // Poll 120s
                        for (let i = 0; i < 120; i++) {
                            const devices = await navigator.usb.getDevices();
                            const dev = devices.find(d => d.vendorId === 0x18d1);
                            if (dev) {
                                try {
                                    fastbootDev = new FastbootDevice(dev);
                                    await fastbootDev.connect();
                                    // @ts-ignore
                                    await fastbootDev.getVariable("product");
                                    break;
                                } catch (e) {
                                    fastbootDev = null;
                                }
                            }
                            await new Promise(r => setTimeout(r, 1000));
                        }

                        if (!fastbootDev) {
                            throw new Error("Device not found in Bootloader mode. Validation aborted.");
                        }

                        log("Device connected in Bootloader.", "success");

                        // 4. Lock Modal
                        const lockModal = document.getElementById('lock-confirmation-modal');
                        const lockBtn = document.getElementById('btn-lock-confirm');
                        const skipBtn = document.getElementById('btn-lock-skip');
                        if (lockModal) lockModal.classList.add('is-active');

                        await new Promise<void>((resolve) => {
                            if (lockBtn) lockBtn.onclick = async () => {
                                if (lockModal) lockModal.classList.remove('is-active');
                                log("Locking Bootloader...", "info");
                                try {
                                    // @ts-ignore
                                    await fastbootDev!.runCommand("flashing lock");
                                    log("WARNING: Please CONFIRM on device screen!", "info");
                                    log("Waiting for reboot...", "info");
                                    await new Promise(r => setTimeout(r, 5000));
                                    // @ts-ignore
                                    try { await fastbootDev!.runCommand("reboot"); } catch (e) { }
                                    resolve();
                                } catch (e: any) {
                                    log(`Lock Command Failed: ${e.message}`, "error");
                                    log("Cause: 'invalid images' (Boot not verified)?", "info");
                                    resolve();
                                }
                            };
                            if (skipBtn) skipBtn.onclick = () => {
                                if (lockModal) lockModal.classList.remove('is-active');
                                log("Skipping Lock. Rebooting...", "info");
                                // @ts-ignore
                                fastbootDev!.runCommand("reboot").catch(() => { });
                                resolve();
                            }
                        });


                        return; // Exit Sideload Flow

                    } catch (adbErr: any) {
                        throw new Error("ADB Sideload Failed: " + adbErr.message);
                    } finally {
                        // adbService disposed manually above
                    }
                }

                // Helper to get Blob from an Entry
                const getEntryBlob = async (entry: any): Promise<Blob> => {
                    const writer = new zip.BlobWriter();
                    return await entry.getData(writer);
                };

                // 1. Bootloader & Radio - SKIPPED FOR SAFETY
                log("SAFETY: Skipping Bootloader and Radio flashing to prevent bricking.", "info");

                // 3. Nested Images
                const imageZipEntry = entries.find(e => e.filename.match(/image-.+\.zip$/));
                if (imageZipEntry) {
                    log(`Unpacking nested images (${imageZipEntry.filename})...`);
                    const imageZipBlob = await getEntryBlob(imageZipEntry);

                    // Nested Reader
                    const nestedReader = new zip.ZipReader(new zip.BlobReader(imageZipBlob));
                    const nestedEntries = await nestedReader.getEntries();

                    // Reboot to FastbootD
                    const isUserspace = await device.getVariable('is-userspace');
                    if (isUserspace !== 'yes') {
                        log("Rebooting to FastbootD (Userspace) for system flashing...");
                        await device.runCommand('reboot-fastboot');
                        await device.waitForConnect();
                    }

                    const imgEntries = nestedEntries.filter(e => e.filename.endsWith('.img'));
                    log(`Found ${imgEntries.length} partition images to flash.`);

                    for (const entry of imgEntries) {
                        const partName = entry.filename.replace('.img', '');
                        // Filter out non-partitions if necessary (e.g. android-info.txt is already filtered by .img)

                        log(`Flashing ${partName}...`);
                        const content = await getEntryBlob(entry);

                        try {
                            await (device as any).flashBlob(partName, content);
                            const progressBar = document.getElementById('progress-bar') as HTMLProgressElement;
                            if (progressBar) progressBar.innerText = `Flashed ${partName}`;
                        } catch (e: any) {
                            log(`Failed to flash ${partName}: ${e.message}`, "error");
                            // Critical failure? Usually yes.
                            throw e;
                        }
                    }
                    await nestedReader.close();
                }

                await reader.close();

                // Reboot to System
                if (config.autoReboot) {
                    log("Flashing Complete. Rebooting to System...", "success");
                    await device.runCommand('reboot');
                } else {
                    log("Flashing Complete. Reboot skipped (checkbox unchecked).", "success");
                }
            } catch (err: any) {
                // CACHE INVALIDATION ON ERROR
                // Don't delete cache if it was just a user abort (retained for retry)
                if (!err.message.includes("Aborted by user") && !err.message.includes("Sideload cancelled")) {
                    try {
                        // Re-derive filename to ensure we delete the correct one
                        const zipFilename = files.zipUrl.split('/').pop() || 'firmware.zip';
                        const root = await navigator.storage.getDirectory();
                        await root.removeEntry(zipFilename);
                        log(`Invalidated corrupt/partial cache (${zipFilename} removed).`, "info");
                    } catch (cleanupErr) {
                        console.error("Failed to cleanup cache:", cleanupErr);
                    }
                } else {
                    log("Cache retained (User Abort).", "info");
                }

                throw new Error(`Cloud Download/Flash Error: ${err.message}`);
            }
        }

        if (config.lock) {
            await performLock(device);
        } else {
            log("Locking skipped (not selected).");
        }


        log("Looking good! Process finished.", "success");

    } catch (error: any) {
        log(`CRITICAL ERROR: ${error.message}`, "error");
        alert(`Process Failed: ${error.message}`);
    }
}
