import { AdbService } from './adb-service';
import { log, showPermissionError, wrapDeviceLogger } from './ui-utils';
import * as Fastboot from 'android-fastboot';
import { FastbootDevice } from 'android-fastboot';
import { startStatsPolling } from './stats-service';

export interface ConnectionUI {
    btnConnect: HTMLButtonElement;
    btnFlash: HTMLButtonElement;
    lblStatus: HTMLElement;
    lblDevice: HTMLElement;
    helpDiv: HTMLElement;
    statsDiv: HTMLElement;
    elMode: HTMLElement;
    elLock: HTMLElement;
}

let connectedDevice: FastbootDevice | null = null;
let currentAdbService: AdbService | null = null;

export function getConnectedDevice() {
    return connectedDevice;
}

export async function handleConnectClick(ui: ConnectionUI) {
    if (!navigator.usb) {
        alert("WebUSB not supported!");
        return;
    }

    ui.btnConnect.disabled = true;
    ui.btnConnect.classList.add('is-loading');

    try {
        log("Requesting WebUSB device...");

        if (connectedDevice) {
            try {
                log("Resetting previous connection...", "info");
                const rawDevice = (connectedDevice as any).device || (connectedDevice as any)._device;
                if (rawDevice && typeof rawDevice.close === 'function') {
                    await rawDevice.close();
                    log("Closed previous USB session.", "success");
                }
            } catch (e) { console.warn("Cleanup warning:", e); }
            connectedDevice = null;
        }
        if (currentAdbService) {
            try {
                if (typeof currentAdbService.dispose === 'function') {
                    await currentAdbService.dispose();
                    log("Disposed previous ADB session.", "info");
                }
            } catch (e) {
                console.warn("ADB Dispose Error:", e);
            }
            currentAdbService = null;
        }

        const selectedDevice = await navigator.usb.requestDevice({
            filters: [{ vendorId: 0x18d1 }]
        });

        if (!selectedDevice) return;

        // PRE-VALIDATION: ADB Check
        let isAdb = false;
        if (selectedDevice.vendorId === 0x18d1) {
            if (selectedDevice.productId === 0x4ee7) {
                isAdb = true;
            } else if (selectedDevice.configuration?.interfaces.some(i =>
                i.alternates[0].interfaceClass === 255 &&
                i.alternates[0].interfaceSubclass === 66 &&
                i.alternates[0].interfaceProtocol === 1
            )) {
                isAdb = true;
            }
        }

        if (isAdb) {
            await handleAdbMode(selectedDevice, ui);
            return;
        }

        // FASTBOOT MODE
        const rawDevice = new Fastboot.FastbootDevice();
        connectedDevice = wrapDeviceLogger(rawDevice);
        await connectedDevice!.connect();

        try {
            const product = await connectedDevice!.getVariable('product');
            if (ui.lblDevice) ui.lblDevice.textContent = product || "Pixel Device";
        } catch (ignore) { }

        if (ui.lblStatus) {
            ui.lblStatus.textContent = "CONNECTED";
            ui.lblStatus.classList.remove('is-dark');
            ui.lblStatus.classList.add('is-success');
        }

        ui.btnConnect.textContent = "Device Paired";
        ui.btnConnect.classList.remove('is-primary');
        ui.btnConnect.classList.add('is-success');
        ui.btnConnect.classList.remove('is-loading');
        ui.btnConnect.disabled = true;

        if (ui.helpDiv) ui.helpDiv.style.display = 'block';
        if (ui.statsDiv) ui.statsDiv.style.display = 'block';

        startStatsPolling(connectedDevice!, (stats) => {
            if (ui.elMode) {
                ui.elMode.textContent = (stats.isUserspace) ? 'FastbootD (Userspace)' : 'Bootloader';
                ui.elMode.className = (stats.isUserspace) ? 'tag is-warning' : 'tag is-success';
            }
            if (ui.elLock) {
                ui.elLock.textContent = (stats.unlocked === 'yes') ? 'UNLOCKED' : (stats.unlocked === 'no' ? 'LOCKED' : 'Unknown');
                ui.elLock.className = (stats.unlocked === 'yes') ? 'tag is-danger' : 'tag is-success';
            }

            const isValidState = !stats.isUserspace;
            ui.btnFlash.disabled = !isValidState;

            if (isValidState && ui.helpDiv) ui.helpDiv.style.display = 'none';
        });

    } catch (e: any) {
        handleConnectionError(e);
    } finally {
        if (ui.btnConnect.textContent !== "Device Paired") {
            ui.btnConnect.disabled = false;
            ui.btnConnect.classList.remove('is-loading');
        }
    }
}

async function handleAdbMode(device: USBDevice, ui: ConnectionUI) {
    log("⚠️ Device detected in ADB Mode...", "info");
    log("Trying to fetch device info via ADB...", "info");

    try {
        currentAdbService = new AdbService();
        await currentAdbService.connect(device);
        const info = await currentAdbService.fetchInfo();

        log("✅ ADB Connection Successful", "success");
        log(`📱 Model: ${info.model}`);
        log(`🤖 Android: ${info.androidVer}`);
        log(`🔋 Battery: ${info.batLevel}%`);

    } catch (adbErr: any) {
        console.error("ADB Fetch Info Failed:", adbErr);
        log("Could not fetch ADB info: " + adbErr.message, "error");
    }

    if (ui.helpDiv) {
        ui.helpDiv.style.display = 'block';
        ui.helpDiv.className = 'message is-small is-info mt-3';
        const body = ui.helpDiv.querySelector('.message-body') as HTMLElement;
        if (body) {
            body.innerHTML = `
                <strong>ADB Mode Detected</strong><br>
                Connected to Android OS.<br>
                To flash, we need to switch to <strong>Bootloader Mode</strong>.<br>
            `;
            const rebootBtn = document.createElement('button');
            rebootBtn.className = "button is-small is-info mt-2";
            rebootBtn.textContent = "🔄 Reboot to Bootloader";
            rebootBtn.onclick = () => tryRebootToBootloader(ui);
            body.appendChild(rebootBtn);
        }
    }
}

export async function tryRebootToBootloader(ui: ConnectionUI) {
    try {
        log("Trying ADB Reboot (WebUSB)...");

        try {
            if (currentAdbService) {
                await currentAdbService.rebootToBootloader();
            } else {
                const device = await navigator.usb.requestDevice({ filters: [{ vendorId: 0x18d1 }] });
                if (device) {
                    const service = new AdbService();
                    await service.connect(device);
                    await service.rebootToBootloader();
                }
            }
        } catch (e: any) {
            if (!e.message.includes('NetworkError') && !e.message.includes('transferIn')) {
                console.warn("Reboot cmd error:", e);
            }
        }

        if (ui.lblStatus) {
            ui.lblStatus.textContent = "REBOOTING...";
            ui.lblStatus.className = "tag is-warning is-medium";
        }

        if (ui.btnConnect) {
            setTimeout(() => {
                if (ui.lblStatus && ui.lblStatus.textContent === "REBOOTING...") {
                    ui.btnConnect.disabled = false;
                    ui.btnConnect.textContent = "Authorize Device?";
                    ui.btnConnect.className = "button is-info is-pulsing";
                }
            }, 3000);
        }

        for (let i = 0; i < 40; i++) {
            await new Promise(r => setTimeout(r, 500));

            if (connectedDevice) return true;

            try {
                const devices = await navigator.usb.getDevices();
                const candidates = devices.filter(d => d.vendorId === 0x18d1);

                if (candidates.length > 0) {
                    const rawDevice = new Fastboot.FastbootDevice();
                    connectedDevice = wrapDeviceLogger(rawDevice);
                    await connectedDevice!.connect();

                    log("✅ Device re-connected in Bootloader mode!", "success");

                    try {
                        const product = await connectedDevice!.getVariable('product');
                        if (ui.lblDevice) ui.lblDevice.textContent = product || "Pixel Device";
                    } catch (ign) { }

                    if (ui.lblStatus) {
                        ui.lblStatus.textContent = "CONNECTED";
                        ui.lblStatus.classList.remove('is-dark');
                        ui.lblStatus.classList.add('is-success');
                    }
                    if (ui.btnConnect) {
                        ui.btnConnect.textContent = "Device Paired";
                        ui.btnConnect.className = "button is-success";
                        ui.btnConnect.disabled = true;
                    }

                    if (ui.helpDiv) ui.helpDiv.style.display = 'none';
                    if (ui.statsDiv) ui.statsDiv.style.display = 'block';

                    startStatsPolling(connectedDevice!, (stats) => {
                        if (ui.elMode) {
                            ui.elMode.textContent = (stats.isUserspace) ? 'FastbootD (Userspace)' : 'Bootloader';
                            ui.elMode.className = (stats.isUserspace) ? 'tag is-warning' : 'tag is-success';
                        }
                        if (ui.elLock) {
                            ui.elLock.textContent = (stats.unlocked === 'yes') ? 'UNLOCKED' : (stats.unlocked === 'no' ? 'LOCKED' : 'Unknown');
                            ui.elLock.className = (stats.unlocked === 'yes') ? 'tag is-danger' : 'tag is-success';
                        }
                        const isValidState = !stats.isUserspace;
                        if (ui.btnFlash) ui.btnFlash.disabled = !isValidState;
                    });

                    return true;
                }
            } catch (e) { }
        }

        log("Timed out waiting for device.", "error");
        if (ui.lblStatus) ui.lblStatus.textContent = "DISCONNECTED";

        return false;

    } catch (e: any) {
        log(`ADB Reboot operation failed: ${e.message}`, 'error');
        return false;
    }
}

function handleConnectionError(e: any) {
    console.error(e);
    if ((e.name === 'SecurityError' || e.message.includes('Access denied')) && !e.message.includes('ADB Mode')) {
        showPermissionError();
    } else {
        log("❌ Connection Error: " + e.message, "error");
    }
}
