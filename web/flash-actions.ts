
import { FastbootDevice } from 'android-fastboot';

/**
 * Log wrapper (matches expected UI signature, can be injected or reused)
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
 * Shows a blocking warning modal (reused from original)
 */
function showBlockingWarning(text: string, countdownSecs = 60): Promise<boolean> {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'modal is-active';
        modal.innerHTML = `
        <div class="modal-background"></div>
        <div class="modal-card">
            <header class="modal-card-head has-background-danger">
                <p class="modal-card-title has-text-white">⚠️ CRITICAL WARNING</p>
                <button class="delete" aria-label="close"></button>
            </header>
            <section class="modal-card-body">
                <div class="content">
                    <p class="subtitle is-5">${text}</p>
                    <p>Please read carefully. This action may be irreversible or cause data loss.</p>
                </div>
            </section>
            <footer class="modal-card-foot">
                <button id="modal-confirm" class="button is-danger" disabled>I Understand (Wait ${countdownSecs}s)</button>
                <button id="modal-cancel" class="button">Cancel</button>
            </footer>
        </div>
        `;
        document.body.appendChild(modal);

        const confirmBtn = modal.querySelector('#modal-confirm') as HTMLButtonElement;
        const cancelBtn = modal.querySelector('#modal-cancel') as HTMLButtonElement;
        const closeBtn = modal.querySelector('.delete') as HTMLButtonElement;

        let left = countdownSecs;
        const cleanup = () => {
            if (interval) clearInterval(interval);
            document.body.removeChild(modal);
        };

        // Close X
        closeBtn.onclick = () => {
            cleanup();
            resolve(false);
        };

        const interval = setInterval(() => {
            left--;
            if (left <= 0) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = "I Understand & Proceed";
                clearInterval(interval);
            } else {
                confirmBtn.textContent = `I Understand (Wait ${left}s)`;
            }
            if (left < -300) { // Safety timeout (5 mins)
                cleanup();
                resolve(false);
            }
        }, 1000);

        confirmBtn.onclick = () => {
            cleanup();
            resolve(true);
        };

        cancelBtn.onclick = () => {
            cleanup();
            resolve(false);
        };
    });
}


/**
 * 1. UNLOCK FLOW
 */
export async function performUnlock(device: FastbootDevice) {
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
        } catch (innerE: any) {
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
export async function flashCustomKey(device: FastbootDevice, keyBlob: Blob) {
    if (!keyBlob) throw new Error("No AVB key provided!");

    let isUserspace = await device.getVariable('is-userspace');
    if (isUserspace === 'yes') {
        log("Device in FastbootD. Switching to Bootloader Interface for key flashing...");
        await device.runCommand('reboot-bootloader');
        await device.waitForConnect();

        // Double check
        isUserspace = await device.getVariable('is-userspace');
        if (isUserspace === 'yes') {
            throw new Error("Failed to switch to Bootloader. Please manually Reboot to Bootloader.");
        }
    }

    // Check lock state
    let unlocked = await device.getVariable('unlocked');
    unlocked = (unlocked || '').trim().toLowerCase();

    // Validation
    log(`Key Size: ${keyBlob.size} bytes`);
    if (keyBlob.size < 64 || keyBlob.size > 10240) {
        throw new Error(`Invalid AVB Key size (${keyBlob.size} bytes). Download might have failed.`);
    }

    // Checking for HTML/JSON error response (common if 404/500 returns text)
    const headerSlice = keyBlob.slice(0, 50);
    const headerText = await headerSlice.text();
    if (headerText.includes('<!DOCTYPE') || headerText.includes('<html') || headerText.includes('{"error"')) {
        throw new Error(`Invalid Key content (looks like HTML/JSON error): "${headerText.substring(0, 20)}...". File likely missing.`);
    }

    if (unlocked === 'no') {
        throw new Error("Device is LOCKED! You must Unlock Bootloader first.");
    }

    log("Erasing old AVB key...");
    await device.runCommand('erase:avb_custom_key');

    // Wait for stability
    log("Waiting for device sync...");
    await new Promise(r => setTimeout(r, 12000));

    // Flash Phase with Retry
    log("Flashing new AVB Custom Key...");
    let lastError;

    for (let attempt = 1; attempt <= 2; attempt++) {
        try {
            if (attempt > 1) log(`Retry attempt ${attempt}...`);
            await (device as any).flashBlob('avb_custom_key', keyBlob);
            log("✅ AVB Key flashed successfully.", "success");
            return;
        } catch (e: any) {
            console.warn(`Flash attempt ${attempt} failed:`, e);
            lastError = e;
            // Short wait before retry
            await new Promise(r => setTimeout(r, 1000));
        }
    }

    throw new Error(
        `Failed to flash avb_custom_key after retries: ${lastError.message}. ` +
        "Please check if your cable is stable or if the device requires a manual reboot."
    );
}

/**
 * 3. LOCK FLOW
 */
export async function performLock(device: FastbootDevice) {
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
