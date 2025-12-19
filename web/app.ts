
import 'bulma/css/bulma.min.css';
import './style.css';

import { runWebFlasher, FlasherConfig, ValidatedFiles } from './flasher';
import { log, toggleTheme } from './ui-utils';
import { fetchBuildsList, BuildEntry, PUBLIC_KEY_URL } from './build-service';
import { handleConnectClick, ConnectionUI, getConnectedDevice } from './connection-handler';
import { startStatsPolling, stopStatsPolling } from './stats-service';
import { FastbootDevice } from 'android-fastboot';

let buildsList: BuildEntry[] = [];

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
const chkReboot = document.getElementById('chk-reboot') as HTMLInputElement;
const chkLock = document.getElementById('chk-lock') as HTMLInputElement;

// Elements for Stats
const helpDiv = document.getElementById('fastboot-help') as HTMLElement;
const statsDiv = document.getElementById('device-stats') as HTMLElement;
const elMode = document.getElementById('stat-mode') as HTMLElement;
const elLock = document.getElementById('stat-unlocked') as HTMLElement;

if (btnTheme) btnTheme.addEventListener('click', toggleTheme);

async function initBuilds() {
    buildsList = await fetchBuildsList();

    selVersion.innerHTML = '';
    if (buildsList.length === 0) {
        const opt = document.createElement('option');
        opt.text = "No builds found / Error";
        selVersion.add(opt);
        return;
    }

    buildsList.forEach((build, index) => {
        const opt = document.createElement('option');
        opt.value = index.toString();
        opt.text = `${build.build_date} - ${build.filename}`;
        if (index === 0) opt.selected = true;
        selVersion.add(opt);
    });
}

window.addEventListener('DOMContentLoaded', () => {
    initBuilds();

    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    if (btnConnect) btnConnect.addEventListener('click', () => {
        const ui: ConnectionUI = {
            btnConnect, btnFlash, lblStatus, lblDevice,
            helpDiv, statsDiv, elMode, elLock
        };
        handleConnectClick(ui);
    });

    if (btnFlash) btnFlash.addEventListener('click', async () => {
        const connectedDevice = getConnectedDevice();
        if (!connectedDevice) {
            alert("Device not connected!");
            return;
        }

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
            wipeData: false,
            autoReboot: chkReboot ? chkReboot.checked : true
        };

        btnFlash.disabled = true;
        btnFlash.classList.add('is-loading');

        try {
            stopStatsPolling();

            let keyBlob: Blob | null = null;
            if (config.flashKey) {
                log("Fetching AVB Public Key from Cloud...");
                try {
                    const resp = await fetch(PUBLIC_KEY_URL);
                    if (!resp.ok) throw new Error(`Cloud Key fetch failed (${resp.status}). Check build server.`);
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

            await runWebFlasher(config, files, connectedDevice as FastbootDevice);

        } catch (e: any) {
            log(e.message, 'error');
        } finally {
            btnFlash.disabled = false;
            btnFlash.classList.remove('is-loading');

            if (connectedDevice) {
                startStatsPolling(connectedDevice, (stats) => {
                    if (elMode) {
                        elMode.textContent = (stats.isUserspace) ? 'FastbootD (Userspace)' : 'Bootloader';
                        elMode.className = (stats.isUserspace) ? 'tag is-warning' : 'tag is-success';
                    }
                    if (elLock) {
                        elLock.textContent = (stats.unlocked === 'yes') ? 'UNLOCKED' : (stats.unlocked === 'no' ? 'LOCKED' : 'Unknown');
                        elLock.className = (stats.unlocked === 'yes') ? 'tag is-danger' : 'tag is-success';
                    }
                    if (btnFlash) {
                        const isValidState = !stats.isUserspace;
                        btnFlash.disabled = !isValidState;
                    }
                    if (helpDiv) {
                        if (!stats.isUserspace) helpDiv.style.display = 'none';
                    }
                });
            }
        }
    });
});
