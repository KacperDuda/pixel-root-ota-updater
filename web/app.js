
import { runWebFlasher } from './flasher.js?v=2.1';

// Configuration
const BUCKET_NAME = "sabre-gcp-project-pixel-root-ota-updater-release";
const INDEX_URL = `https://storage.googleapis.com/${BUCKET_NAME}/builds_index.json`;

// Variables
let selectedKeyFile = null;
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
const fileInputKey = document.getElementById('file-key');

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
        // Expecting { builds: [ { date:..., id:..., url:... }, ... ] }
        // or just an array list. Assuming our format is list or similar. 
        // Based on pixel_automator.py: builds_index.json is a list of dicts.

        buildsList = Array.isArray(data) ? data : (data.builds || []);

        // Populate Select
        selVersion.innerHTML = '';
        if (buildsList.length === 0) {
            const opt = document.createElement('option');
            opt.text = "No builds found";
            selVersion.add(opt);
            return;
        }

        // Sort desc date (assuming API might not)
        // buildsList.sort((a,b) => new Date(b.date) - new Date(a.date));

        buildsList.forEach((build, index) => {
            const opt = document.createElement('option');
            opt.value = index; // Store index to retrieve obj later
            opt.text = `${build.date} - ${build.id} (Signed)`;
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

    // Key File
    fileInputKey.addEventListener('change', (e) => {
        selectedKeyFile = e.target.files[0];
        const nameLabel = document.getElementById('file-key-name');
        if (selectedKeyFile) {
            nameLabel.textContent = selectedKeyFile.name;
            log(`AVB Key selected: ${selectedKeyFile.name}`);
        } else {
            nameLabel.textContent = "No file selected";
        }
    });

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
                document.getElementById('device-name').value = device.productName || "Pixel Device"; // Input readonly
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
        if (chkFlashKey.checked && !selectedKeyFile) {
            alert("Please select an AVB Public Key (.bin) to flash!");
            return;
        }

        // Get Selected Build
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

        const files = {
            key: selectedKeyFile,
            zipUrl: selectedBuild ? selectedBuild.url : null // Pass URL instead of File object
        };

        btnFlash.disabled = true;
        btnFlash.classList.add('is-loading');

        try {
            await runWebFlasher(config, files);
        } catch (e) {
            log(e.message, 'error');
        } finally {
            btnFlash.disabled = false;
            btnFlash.classList.remove('is-loading');
        }
    });
});

