
/**
 * Generic Logger Interface
 */
export function log(msg: string, type: 'info' | 'error' | 'success' = 'info') {
    const container = document.getElementById('log-container');
    if (!container) return;

    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'error' ? '❌ ' : type === 'success' ? '✅ ' : 'ℹ️ ';
    // Append text line to pre
    container.textContent += `[${timestamp}] ${prefix}${msg}\n`;
    container.scrollTop = container.scrollHeight;
}

/**
 * Toggles Dark/Light Theme
 */
export function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
}

/**
 * Shows the Linux Permission Error Box
 */
export function showPermissionError() {
    log("❌ Access Denied! Linux permissions missing.", "error");

    const helpDiv = document.getElementById('fastboot-help');
    if (helpDiv) {
        helpDiv.style.display = 'block';
        helpDiv.className = 'message is-small is-danger mt-3'; // Change to red
        const body = helpDiv.querySelector('.message-body');
        if (body) {
            body.innerHTML = `
            <strong>LINUX PERMISSION ERROR (Access Denied)</strong><br>
            Your browser cannot access the USB device. Do NOT run as sudo.<br>
            <br>
            <strong>Fix it (Terminal):</strong><br>
            <code>echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/51-android.rules && sudo udevadm control --reload-rules && sudo udevadm trigger</code>
            <br><br>
            <strong>Using Snap (Chromium/Chrome)?</strong><br>
            <code>sudo snap connect chromium:raw-usb</code>
            <br><br>
            <strong>THEN: Unplug and Re-plug the cable!</strong>
        `;
        }
    }
    alert("Linux Permission Error: Check the red box below for the fix command!");
}

/**
 * Wraps the FastbootDevice in a Proxy to log all interactions
 */
export function wrapDeviceLogger(device: any): any {
    return new Proxy(device, {
        get(target, prop, receiver) {
            const value = Reflect.get(target, prop, receiver);
            if (typeof value === 'function') {
                return async (...args: any[]) => {
                    const cmdName = String(prop);
                    // Filter noisy logs (e.g. repetitive polling)
                    const isPooling = cmdName === 'getVariable' && (args[0] === 'product' || args[0] === 'unlocked' || args[0] === 'is-userspace');

                    if (!isPooling) {
                        let argStr = args.map(a => {
                            if (a instanceof Blob || a instanceof File) return `[Blob ${a.size} bytes]`;
                            // @ts-ignore
                            if (a instanceof Uint8Array) return `[Uint8Array ${a.length}]`;
                            return JSON.stringify(a);
                        }).join(', ');
                        log(`[CMD] ${cmdName}(${argStr})`, 'info');
                    }

                    try {
                        const result = await value.apply(target, args);
                        if (!isPooling && result !== undefined) {
                            // truncate long results
                            const resStr = JSON.stringify(result);
                            const truncated = resStr && resStr.length > 100 ? resStr.substring(0, 100) + '...' : resStr;
                            log(`[RES] ${cmdName} => ${truncated}`);
                        }
                        return result;
                    } catch (e: any) {
                        log(`[ERR] ${cmdName} failed: ${e.message}`, 'error');
                        throw e;
                    }
                };
            }
            return value;
        }
    });
}
