// Import Styles
import 'bulma/css/bulma.min.css';
import './style.css';

// Import Logic
import { runWebFlasher, FlasherConfig, ValidatedFiles } from './flasher';

// Import ADB Libraries
import { Adb } from '@yume-chan/adb';
import AdbWebUsbBackend from '@yume-chan/adb-backend-webusb';

// Configuration
const BUCKET_NAME = "sabre-gcp-project-pixel-root-ota-updater-release";
const INDEX_URL = `https://storage.googleapis.com/${BUCKET_NAME}/builds_index.json`;
const PUBLIC_KEY_URL = `https://storage.googleapis.com/${BUCKET_NAME}/keys/avb_pkmd.bin`;

// Interfaces
interface BuildEntry {
    device: string;
    android_version: string;
    build_date: string; // "2024..."
    filename: string;
    url: string;
    timestamp: string;
}

// Variables
let buildsList: BuildEntry[] = [];

// Logger
function log(msg: string, type: 'info' | 'error' | 'success' = 'info') {
    const container = document.getElementById('log-container');
    if (!container) return;

    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'error' ? '❌ ' : type === 'success' ? '✅ ' : 'ℹ️ ';
    // Append text line to pre
    container.textContent += `[${timestamp}] ${prefix}${msg}\n`;
    container.scrollTop = container.scrollHeight;
}

// UI Elements
const btnConnect = document.getElementById('connect-btn') as HTMLButtonElement;
const btnFlash = document.getElementById('flash-btn') as HTMLButtonElement;
const lblDevice = document.getElementById('device-name') as HTMLElement;
const lblStatus = document.getElementById('connection-status') as HTMLElement;
const selVersion = document.getElementById('version-select') as HTMLSelectElement;
const btnTheme = document.getElementById('theme-toggle') as HTMLButtonElement;

// Inputs
const chkUnlock = document.getElementById('chk-unlock') as HTMLInputElement;
const chkFlashKey = document.getElementById('chk-flash-key') as HTMLInputElement;
const chkFlashZip = document.getElementById('chk-flash-zip') as HTMLInputElement;
const chkLock = document.getElementById('chk-lock') as HTMLInputElement;

// --- THEME TOGGLE (Bulma) ---
function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
}

// --- FETCH BUILDS ---
async function fetchBuilds() {
    try {
        log("Fetching build index from cloud...");
        const resp = await fetch(INDEX_URL);
        if (!resp.ok) throw new Error("Index not found");

        const data = await resp.json();
        const rawList = Array.isArray(data) ? data : (data.builds || []);
        buildsList = rawList as BuildEntry[];

        // Populate Select
        selVersion.innerHTML = '';
        if (buildsList.length === 0) {
            const opt = document.createElement('option');
            opt.text = "No builds found";
            selVersion.add(opt);
            return;
        }

        buildsList.forEach((build, index) => {
            const opt = document.createElement('option');
            opt.value = index.toString();
            // Correct keys: build_date, filename
            opt.text = `${build.build_date} - ${build.filename} (Signed)`;
            if (index === 0) opt.selected = true; // Auto select latest
            selVersion.add(opt);
        });

        log(`Loaded ${buildsList.length} builds. Latest selected.`);

    } catch (e: any) {
        log(`Failed to fetch builds: ${e.message}`, 'error');
        const opt = document.createElement('option');
        opt.text = "Error loading builds";
        selVersion.add(opt);
    }
}

// --- ADB REBOOT HELPER ---
async function tryRebootToBootloader() {
    try {
        log("Trying ADB Reboot (WebUSB)...");
        const backend = await AdbWebUsbBackend.requestDevice({ filters: [{ vendorId: 0x18d1 }] });
        if (!backend) return false;

        const adb = await Adb.overWebUsb(backend);
        log("ADB Connection established. sending reboot bootloader...");
        await adb.subprocess.spawnAndWait("reboot bootloader");
        log("Reboot command sent. Device should restart.");
        return true;
    } catch (e: any) {
        log(`ADB Reboot failed: ${e.message}. Manual reboot required.`, 'error');
        return false;
    }
}

// Event Listeners
window.addEventListener('DOMContentLoaded', () => {
    fetchBuilds();

    // Theme
    if (btnTheme) btnTheme.addEventListener('click', toggleTheme);

    // Init theme based on preference or default
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    // Connect
    if (btnConnect) btnConnect.addEventListener('click', async () => {
        if (!navigator.usb) {
            alert("WebUSB not supported!");
            return;
        }

        try {
            const device = await navigator.usb.requestDevice({ filters: [{ vendorId: 0x18d1 }] });
            if (device) {
                if (lblDevice) lblDevice.textContent = device.productName || "Pixel Device";
                if (lblStatus) {
                    lblStatus.textContent = "CONNECTED";
                    lblStatus.classList.remove('is-dark');
                    lblStatus.classList.add('is-success');
                }

                btnConnect.textContent = "Device Paired";
                btnConnect.classList.remove('is-primary');
                btnConnect.classList.add('is-success');
                btnConnect.disabled = true;

                btnFlash.disabled = false;

                const helpDiv = document.getElementById('fastboot-help');
                if (helpDiv) {
                    helpDiv.style.display = 'block';

                    const body = helpDiv.querySelector('.message-body');
                    if (body) {
                        const rebootBtn = document.createElement('button');
                        rebootBtn.className = "button is-small is-info mt-2";
                        rebootBtn.textContent = "Attempt ADB Reboot to Bootloader";
                        rebootBtn.onclick = tryRebootToBootloader;
                        body.appendChild(rebootBtn);
                    }
                }
            }
        } catch (e) {
            console.error(e);
            log("Connection cancelled or failed.", "error");
        }
    });

    // Start Flash
    if (btnFlash) btnFlash.addEventListener('click', async () => {
        const selIdx = parseInt(selVersion.value);
        if (chkFlashZip.checked && (isNaN(selIdx) || !buildsList[selIdx])) {
            alert("Please select a valid System Version from the list.");
            return;
        }

        const selectedBuild = buildsList[selIdx];

        const config: FlasherConfig = {
            unlock: chkUnlock.checked,
            flashKey: chkFlashKey.checked,
            flashZip: chkFlashZip.checked,
            lock: chkLock.checked,
            wipeData: false
        };

        btnFlash.disabled = true;
        btnFlash.classList.add('is-loading');

        try {
            // --- Cloud Key Fetch Logic ---
            let keyBlob: Blob | null = null;
            if (config.flashKey) {
                log("Fetching AVB Public Key from Cloud...");
                try {
                    const resp = await fetch(PUBLIC_KEY_URL);
                    if (!resp.ok) throw new Error("Failed to fetch Public Key from Cloud");
                    keyBlob = await resp.blob();
                    log("✅ Public Key fetched successfully.");
                } catch (e: any) {
                    throw new Error("Could not download AVB Public Key: " + e.message);
                }
            }

            const files: ValidatedFiles = {
                key: keyBlob,
                zipUrl: selectedBuild ? selectedBuild.url : null
            };

            await runWebFlasher(config, files);
        } catch (e: any) {
            log(e.message, 'error');
        } finally {
            btnFlash.disabled = false;
            btnFlash.classList.remove('is-loading');
        }
    });
});
