
import { runWebFlasher } from './flasher.js';

// Configuration
const BUCKET_NAME = "sabre-gcp-project-pixel-root-ota-updater-release";
const MANIFEST_URL = `https://storage.googleapis.com/${BUCKET_NAME}/latest.json`;

// Variables
let selectedZipFile = null;
let selectedKeyFile = null;

// UI Elements
const btnConnect = document.getElementById('connect-btn');
const btnFlash = document.getElementById('flash-btn');
const lblDevice = document.getElementById('device-name');
const lblStatus = document.getElementById('connection-status');

// Inputs
const chkUnlock = document.getElementById('chk-unlock');
const chkFlashKey = document.getElementById('chk-flash-key');
const chkFlashZip = document.getElementById('chk-flash-zip');
const chkLock = document.getElementById('chk-lock');
const fileInputKey = document.getElementById('file-key');
const fileInputZip = document.getElementById('file-zip');

// Fetch logic (Optional Auto-Download future expansion)
async function fetchCloudInfo() {
    try {
        const resp = await fetch(MANIFEST_URL);
        if (resp.ok) {
            const data = await resp.json();
            document.getElementById('cloud-info').style.display = 'block';
            document.getElementById('latest-build-date').textContent = data.date;
            document.getElementById('target-file').textContent = data.image_url;
            console.log("Cloud manifest loaded.");
        }
    } catch (e) { console.warn("Cloud info fetch failed", e); }
}

// Event Listeners
window.addEventListener('DOMContentLoaded', () => {
    fetchCloudInfo();

    // File Selection Handlers
    fileInputKey.addEventListener('change', (e) => {
        selectedKeyFile = e.target.files[0];
        console.log("Key file selected:", selectedKeyFile?.name);
    });

    fileInputZip.addEventListener('change', (e) => {
        selectedZipFile = e.target.files[0];
        console.log("Zip file selected:", selectedZipFile?.name);
    });

    // Checkbox Logic
    chkFlashKey.addEventListener('change', () => {
        // Validation visual cues could go here
    });

    // 1. Connect Button (Just checks WebUSB availability here, actual connect is in flasher flow or we can do pre-check)
    btnConnect.addEventListener('click', async () => {
        // In this architecture, connection is part of the flow OR pre-check.
        // Let's do a pre-check to show device name.
        if (!navigator.usb) {
            alert("WebUSB not supported in this browser!");
            return;
        }

        try {
            // Request permission early to populate UI
            const device = await navigator.usb.requestDevice({ filters: [{ vendorId: 0x18d1 }] });
            if (device) {
                lblDevice.textContent = device.productName || "Pixel Device";
                lblStatus.textContent = "AUTHORIZED";
                lblStatus.classList.add("connected");
                btnFlash.disabled = false;
                btnConnect.style.display = 'none'; // Hide connect button after success
            }
        } catch (e) {
            console.error(e);
        }
    });

    // 2. Start Flash Button
    btnFlash.addEventListener('click', async () => {
        // VALIDATION
        if (chkFlashKey.checked && !selectedKeyFile) {
            alert("Please select an AVB Key file!");
            return;
        }
        // For Zip, we might allow undefined if user just wants to unlock/lock/key
        if (chkFlashZip.checked && !selectedZipFile) {
            // If we implemented cloud download, we'd handle it here. 
            // For now, strict file input.
            // alert("Please select a System Zip file!");
            // return; 
            // Mocking internal zip if testing without file
        }

        const config = {
            unlock: chkUnlock.checked,
            flashKey: chkFlashKey.checked,
            flashZip: chkFlashZip.checked,
            lock: chkLock.checked,
            wipeData: false // Could add another checkbox for this
        };

        const files = {
            key: selectedKeyFile,
            zip: selectedZipFile
        };

        btnFlash.disabled = true;

        // Handover to Controller
        await runWebFlasher(config, files);

        btnFlash.disabled = false;
    });
});

