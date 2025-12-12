
// Configuration - AUTO-FILLED by Terraform/CloudBuild ideally, or hardcoded for now
const BUCKET_NAME = "sabre-gcp-project-pixel-root-ota-updater-release";
const PROJECT_ID = "sabre-gcp-project";
const REPO_NAME = "pixel-root-ota-updater";
const DEVICE_CODENAME = "frankel"; // Default

// URLs
const MANIFEST_URL = `https://storage.googleapis.com/${BUCKET_NAME}/latest.json`;

// State
let usbDevice = null;
let latestBuildData = null;

// Logger
function log(msg, type = 'info') {
    const container = document.getElementById('log-container');
    const el = document.createElement('div');
    el.className = 'log-entry';
    if (type === 'error') el.classList.add('log-err');

    const timestamp = new Date().toLocaleTimeString();
    el.textContent = `[${timestamp}] ${msg}`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

// UI Elements
const btnConnect = document.getElementById('connect-btn');
const btnFlash = document.getElementById('flash-btn');
const lblDevice = document.getElementById('device-name');
const lblDate = document.getElementById('latest-build-date');
const lblFile = document.getElementById('target-file');
const lblStatus = document.getElementById('connection-status');

// --- 1. Fetch Latest Build Info ---
async function fetchLatestBuild() {
    try {
        log("Fetching latest build info from Cloud...");
        const resp = await fetch(MANIFEST_URL);
        if (!resp.ok) throw new Error("Manifest not found");

        const data = await resp.json();
        latestBuildData = data;

        lblDate.textContent = `${data.date} (${data.id})`;
        lblFile.textContent = data.image_url;

        log(`Latest build found: ${data.date}`);
    } catch (e) {
        log(`Failed to fetch build info: ${e.message}`, 'error');
        lblDate.textContent = "Error";
    }
}

// --- 2. WebUSB Connection ---
async function connectDevice() {
    try {
        log("Requesting WebUSB device...");
        // Filter for Google devices (Pixel)
        // Vendor ID 0x18d1 is Google
        usbDevice = await navigator.usb.requestDevice({ filters: [{ vendorId: 0x18d1 }] });

        await usbDevice.open();

        // Basic info
        lblDevice.textContent = `${usbDevice.productName} (v${usbDevice.deviceVersionMajor}.${usbDevice.deviceVersionMinor})`;
        lblStatus.textContent = "CONNECTED";
        lblStatus.classList.add("connected");

        if (usbDevice.configuration === null) {
            await usbDevice.selectConfiguration(1);
        }
        await usbDevice.claimInterface(0);

        log(`Connected to: ${usbDevice.productName}`);

        // Enable flash button if we have build data
        if (latestBuildData) {
            btnFlash.disabled = false;
        }

    } catch (e) {
        log(`Connection failed: ${e.message}`, 'error');
    }
}

// --- 3. Flashing Logic (Mockup/Placeholder for full Fastboot implementation) ---
/* 
   NOTE: Implementing the full Fastboot protocol in vanilla JS in a single file is complex.
   Ideally we would use `android-webusb-fastboot` library.
   For this demo, we will simulate the download and "flash" commands to show the architecture works.
   The user can then integrate the library.
*/
async function flashDevice() {
    if (!usbDevice || !latestBuildData) return;

    btnFlash.disabled = true;
    log("🚀 STARTING FLASH SEQUENCE...");

    try {
        // 1. Download
        log(`Downloading image from: ${latestBuildData.image_url}`);
        // In real impl: fetch blob
        const blob = await fetch(latestBuildData.image_url).then(r => r.blob());
        log(`Download complete. Size: ${(blob.size / 1024 / 1024).toFixed(2)} MB`);

        // 2. Flash (Simulated)
        log("sending 'fastboot flash init_boot' command...");
        // await device.transferOut(...)

        await new Promise(r => setTimeout(r, 2000)); // Fake latency

        log("✅ FLASH COMPLETE!");
        log("Rebooting device...");

    } catch (e) {
        log(`Flash failed: ${e.message}`, 'error');
    } finally {
        btnFlash.disabled = false;
    }
}


// Init
window.addEventListener('DOMContentLoaded', () => {
    fetchLatestBuild();

    btnConnect.addEventListener('click', connectDevice);
    btnFlash.addEventListener('click', flashDevice);
});
