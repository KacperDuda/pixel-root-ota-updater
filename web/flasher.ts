import * as Fastboot from 'android-fastboot';

/**
 * Configuration interface for the flasher.
 */
export interface FlasherConfig {
    unlock: boolean;
    flashKey: boolean;
    flashZip: boolean;
    lock: boolean;
    wipeData: boolean;
}

/**
 * File inputs for the flasher.
 */
export interface ValidatedFiles {
    key: Blob | null;
    zipUrl: string | null;
}

/**
 * Internal interface for the Fastboot Device provided by the library.
 * Minimally typed based on usage.
 */
interface FastbootDevice {
    connect(): Promise<void>;
    getVariable(name: string): Promise<string>;
    runCommand(cmd: string): Promise<void>;
    waitForConnect(): Promise<void>;
    upload(partition: string, buffer: ArrayBuffer): Promise<void>;
    flashFactoryZip(blob: Blob | File, wipe: boolean, onReconnect: () => Promise<void>, onProgress: (action: string, item: string, progress: number) => void): Promise<void>;
}

/**
 * Shows a blocking modal (The Gatekeeper) with a 60s timer.
 * @param message - Warning message.
 * @returns Promise<boolean> true if confirmed, false if timeout/cancelled.
 */
export async function showBlockingWarning(message: string): Promise<boolean> {
    const modal = document.getElementById('warning-modal') as HTMLElement | null;
    const timerDisplay = document.getElementById('modal-timer');
    const confirmBtn = document.getElementById('btn-confirm');
    const cancelBtn = document.getElementById('btn-cancel');
    const msgBody = document.getElementById('modal-message');

    if (!modal || !timerDisplay || !confirmBtn || !cancelBtn || !msgBody) return false;

    msgBody.textContent = message;

    // Native Dialog API
    if (typeof (modal as any).showModal === 'function') {
        (modal as any).showModal();
    } else {
        modal.style.display = 'block'; // Fallback
    }

    let timeLeft = 60;
    timerDisplay.textContent = `${timeLeft}`;

    return new Promise((resolve) => {
        let timerInterval: any;

        const cleanup = () => {
            clearInterval(timerInterval);
            if (typeof (modal as any).close === 'function') {
                (modal as any).close();
            } else {
                modal.style.display = 'none';
            }
            confirmBtn.onclick = null;
            cancelBtn.onclick = null;
        };

        // 1. Timer Logic
        timerInterval = setInterval(() => {
            timeLeft--;
            timerDisplay.textContent = `${timeLeft}`;
            if (timeLeft <= 0) {
                cleanup();
                console.warn("Gatekeeper: Timeout reached.");
                resolve(false); // AUTO-CLOSE: Fail safe
            }
        }, 1000);

        // 2. Confirm
        confirmBtn.onclick = () => {
            cleanup();
            resolve(true); // Proceed
        };

        // 3. Cancel
        cancelBtn.onclick = () => {
            cleanup();
            resolve(false); // Abort
        };
    });
}

/**
 * Log wrapper to update UI console.
 */
function log(msg: string, type: 'info' | 'error' | 'success' = 'info') {
    const container = document.getElementById('log-container');
    if (!container) return;

    if (type === 'error') console.error(msg);
    else console.log(msg);

    const el = document.createElement('div');
    el.className = 'log-entry';
    if (type === 'error') el.classList.add('log-err');
    else if (type === 'success') el.classList.add('log-success');

    const timestamp = new Date().toLocaleTimeString();
    el.textContent = `[${timestamp}] ${msg}`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

/**
 * 1. UNLOCK FLOW
 */
async function performUnlock(device: FastbootDevice) {
    log("Checking bootloader state...");
    let isUnlocked = 'no';
    try {
        isUnlocked = await device.getVariable('unlocked');
    } catch (e) {
        log("Could not check unlock state (older device?), assuming locked.", "error");
    }

    if (isUnlocked === 'yes') {
        log("Device is already unlocked. Skipping unlock step.", "success");
        return;
    }

    const userConsent = await showBlockingWarning(
        "WARNING: You are about to UNLOCK the bootloader. This will WIPE ALL DATA on the device. You have 60 seconds to confirm."
    );

    if (!userConsent) {
        throw new Error("Unlock operation cancelled by user or timeout.");
    }

    log("Sending unlock command...");
    try {
        await device.runCommand('flashing unlock');
    } catch (e: any) {
        try {
            await device.runCommand('oem unlock');
        } catch (innerE) {
            throw new Error("Failed to send unlock command: " + e.message);
        }
    }

    alert("ACTION REQUIRED: Check your phone! Use Volume keys to select 'UNLOCK' and Power to confirm.");
    log("Waiting for device to reconnect after unlock/wipe...", "info");
    await device.waitForConnect();
}

/**
 * 2. FLASH KEY FLOW
 */
async function flashCustomKey(device: FastbootDevice, keyBlob: Blob) {
    if (!keyBlob) throw new Error("No AVB key provided!");

    const isUserspace = await device.getVariable('is-userspace');
    if (isUserspace === 'yes') {
        log("Switching to Bootloader Interface for key flashing...");
        await device.runCommand('reboot-bootloader');
        await device.waitForConnect();
    }

    log("Erasing old AVB key...");
    await device.runCommand('erase:avb_custom_key');

    log("Flashing new AVB Custom Key...");
    // FIX: buffer conversion and explicit partition naming
    const buffer = await keyBlob.arrayBuffer();
    await device.upload('avb_custom_key', buffer);

    await device.runCommand('flash:avb_custom_key');

    log("AVB Key flashed successfully.", "success");
}



/**
 * 4. LOCK FLOW
 */
async function performLock(device: FastbootDevice) {
    const isUserspace = await device.getVariable('is-userspace');
    if (isUserspace === 'yes') {
        log("Switching to Bootloader Interface for locking...");
        await device.runCommand('reboot-bootloader');
        await device.waitForConnect();
    }

    const userConsent = await showBlockingWarning(
        "CRITICAL WARNING: You are about to LOCK the bootloader. Ensure you have flashed the correct AVB Custom Key matching your installed system. If keys mismatch, your device will BRICK. Proceed?"
    );

    if (!userConsent) {
        log("Locking skipped by user/timeout. Device remains unlocked.", "info");
        return;
    }

    log("Sending lock command...");
    await device.runCommand('flashing lock');
    alert("ACTION REQUIRED: Confirm LOCK on device screen!");
}

/**
 * === MAIN ORCHESTRATOR ===
 */
export async function runWebFlasher(config: FlasherConfig, files: ValidatedFiles) {
    // Instantiate via imported library
    const device = new Fastboot.FastbootDevice();

    try {
        log("Connecting to USB device...");
        await device.connect();

        const product = await device.getVariable('product');
        log(`Connected: ${product}`, "success");

        if (config.unlock) {
            await performUnlock(device as any);
        }

        if (config.flashKey && files.key) {
            await flashCustomKey(device as any, files.key);
        }

        if (config.flashZip && files.zipUrl) {
            log(`Downloading System Image from Cloud...`);
            log(files.zipUrl);

            try {
                const response = await fetch(files.zipUrl);
                if (!response.ok) throw new Error(`Download failed: ${response.statusText}`);

                // Progress Bar Logic
                const contentLength = response.headers.get('content-length');
                const total = contentLength ? parseInt(contentLength, 10) : 0;
                let loaded = 0;

                const reader = response.body?.getReader();
                if (!reader) throw new Error("Browser does not support streaming download.");

                const root = await navigator.storage.getDirectory();
                const fileHandle = await root.getFileHandle('firmware.zip', { create: true });
                const writable = await fileHandle.createWritable();

                let lastLoggedPercent = 0;
                log(`Download started. Total size: ${(total / 1024 / 1024).toFixed(2)} MB`);

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    if (value) {
                        await writable.write(value);
                        loaded += value.length;

                        if (total > 0) {
                            const percentNum = (loaded / total) * 100;
                            const percentStr = percentNum.toFixed(1);

                            // Update UI Bar
                            const bar = document.getElementById('progress-bar') as HTMLProgressElement;
                            if (bar) bar.value = percentNum;

                            // Log every 10%
                            if (percentNum - lastLoggedPercent >= 10) {
                                log(`Downloading... ${percentStr}%`);
                                lastLoggedPercent = percentNum;
                            }
                        }
                    }
                }

                await writable.close();
                const file = await fileHandle.getFile();
                log(`Download finished. Size: ${(file.size / 1024 / 1024).toFixed(2)} MB`, "success");

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

                // Use the real flashFactoryZip method from the device instance
                await (device as unknown as FastbootDevice).flashFactoryZip(file, config.wipeData, async () => {
                    log("Device reboot detected. Reconnecting...");
                    await device.waitForConnect();
                }, (action: string, item: string, progress: number) => {
                    const percent = (progress * 100).toFixed(1);
                    log(`[${action}] ${item}: ${percent}%`);
                    const bar = document.getElementById('progress-bar') as HTMLProgressElement;
                    if (bar) bar.value = progress * 100;
                });

                log("Flash Complete.", "success");
            } catch (err: any) {
                throw new Error(`Cloud Download Error: ${err.message}`);
            }
        }

        if (config.lock) {
            await performLock(device as any);
        } else {
            log("Locking skipped (not selected).");
        }

        log("Looking good! Process finished.", "success");

    } catch (error: any) {
        log(`CRITICAL ERROR: ${error.message}`, "error");
        alert(`Process Failed: ${error.message}`);
    }
}
