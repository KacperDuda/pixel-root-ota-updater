import { log } from './ui-utils';

export interface BuildEntry {
    device: string;
    android_version: string;
    build_date: string;
    filename: string;
    url: string;
    timestamp: string;
}

let BUCKET_NAME = "sabre-gcp-project-pixel-root-ota-updater-release";
let INDEX_URL = `https://storage.googleapis.com/${BUCKET_NAME}/builds_index.json`;
export let PUBLIC_KEY_URL = `https://storage.googleapis.com/${BUCKET_NAME}/keys/avb_pkmd.bin`;

// LOCAL MODE DETECTION
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    console.log("🏠 Local Development Mode Detected");
    INDEX_URL = "/output/builds_index.json";
    PUBLIC_KEY_URL = "/output/keys/avb_pkmd.bin";
}

export async function fetchBuildsList(): Promise<BuildEntry[]> {
    try {
        log(`Fetching build index from ${window.location.hostname === 'localhost' ? 'LOCAL DISK' : 'CLOUD'}...`);
        const resp = await fetch(INDEX_URL);
        if (!resp.ok) throw new Error("Index not found (Run Docker build first?)");

        const data = await resp.json();
        let list = Array.isArray(data) ? data : (data.builds || []);

        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            list = list.map((b: any) => ({
                ...b,
                url: `/output/${b.filename}`
            }));
            console.log("Local Mode: Rewrote build URLs to relative paths", list);
        }

        log(`Loaded ${list.length} builds. Latest selected.`);
        return list as BuildEntry[];
    } catch (e: any) {
        log(`Failed to fetch builds: ${e.message}`, 'error');
        return [];
    }
}
