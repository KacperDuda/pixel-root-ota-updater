
import { runWebFlasher } from './flasher.js?v=2.3';

// Configuration
const BUCKET_NAME = "sabre-gcp-project-pixel-root-ota-updater-release";
const INDEX_URL = `https://storage.googleapis.com/${BUCKET_NAME}/builds_index.json`;
const PUBLIC_KEY_URL = `https://storage.googleapis.com/${BUCKET_NAME}/keys/avb_pkmd.bin`;

// Variables
let buildsList = [];

// Logger
function log(msg, type = 'info') {
    const container = document.getElementById('log-container');
    if (!container) return;

    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'error' ? '❌ ' : type === 'success' ? '✅ ' : 'ℹ️ ';
    // Append text line to pre
    container.textContent += `[${timestamp}] ${prefix}${msg}\n`;
    container.scrollTop = container.scrollHeight;
}

// UI Elements
const btnConnect = document.getElementById('connect-btn');
const btnFlash = document.getElementById('flash-btn');
const lblDevice = document.getElementById('device-name');
const lblStatus = document.getElementById('connection-status');
const selVersion = document.getElementById('version-select');
const btnTheme = document.getElementById('theme-toggle');

// Inputs
const chkUnlock = document.getElementById('chk-unlock');
const chkFlashKey = document.getElementById('chk-flash-key');
const chkFlashZip = document.getElementById('chk-flash-zip');
const chkLock = document.getElementById('chk-lock');

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
        buildsList = Array.isArray(data) ? data : (data.builds || []);

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
            opt.value = index; // Store index to retrieve obj later
            // Use correct JSON keys from pixel_automator.py: { build_date, filename }
            opt.text = `${build.build_date} - ${build.filename} (Signed)`;
            if (index === 0) opt.selected = true; // Auto select latest
            selVersion.add(opt);
        });

        log(`Loaded ${buildsList.length} builds. Latest selected.`);

    } catch (e) {
        log(`Failed to fetch builds: ${e.message}`, 'error');
        const opt = document.createElement('option');
        opt.text = "Error loading builds";
        selVersion.add(opt);
    }
}

// Event Listeners
window.addEventListener('DOMContentLoaded', () => {
    fetchBuilds();

    // Theme
    btnTheme.addEventListener('click', toggleTheme);
    // Init theme based on preference or default
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    // Connect
    btnConnect.addEventListener('click', async () => {
        if (!navigator.usb) {
            alert("WebUSB not supported!");
            return;
        }
        try {
            // Request permission
            const device = await navigator.usb.requestDevice({ filters: [{ vendorId: 0x18d1 }] });
            if (device) {
                // Update UI visually
                document.getElementById('device-name').textContent = device.productName || "Pixel Device";
                lblStatus.textContent = "CONNECTED";
                lblStatus.classList.remove('is-dark');
                lblStatus.classList.add('is-success');

                // Show connect button as "Connected" or hide? 
                // Bulma style: change button state
                btnConnect.textContent = "Device Paired";
                btnConnect.classList.remove('is-primary');
                btnConnect.classList.add('is-success');
                btnConnect.disabled = true;

                // Enable Flash
                btnFlash.disabled = false;

                // Show helper tip
                document.getElementById('fastboot-help').style.display = 'block';
            }
        } catch (e) {
            console.error(e);
            log("Connection cancelled or failed.", "error");
        }
    });

    // Start Flash
    btnFlash.addEventListener('click', async () => {
        // Validation
        const selIdx = selVersion.value;
        if (chkFlashZip.checked && (selIdx === "" || !buildsList[selIdx])) {
            alert("Please select a valid System Version from the list.");
            return;
        }

        const selectedBuild = buildsList[selIdx];

        const config = {
            unlock: chkUnlock.checked,
            flashKey: chkFlashKey.checked,
            flashZip: chkFlashZip.checked,
            lock: chkLock.checked,
            wipeData: false // Could be toggle
        };

        btnFlash.disabled = true;
        btnFlash.classList.add('is-loading');

        try {
            // --- Cloud Key Fetch Logic ---
            let keyBlob = null;
            if (config.flashKey) {
                log("Fetching AVB Public Key from Cloud...");
                try {
                    const resp = await fetch(PUBLIC_KEY_URL);
                    if (!resp.ok) throw new Error("Failed to fetch Public Key from Cloud");
                    keyBlob = await resp.blob();
                    log("✅ Public Key fetched successfully.");
                } catch (e) {
                    throw new Error("Could not download AVB Public Key: " + e.message);
                }
            }

            const files = {
                key: keyBlob,
                zipUrl: selectedBuild ? selectedBuild.url : null
            };

            await runWebFlasher(config, files);
        } catch (e) {
            log(e.message, 'error');
        } finally {
            btnFlash.disabled = false;
            btnFlash.classList.remove('is-loading');
        }
    });
});

