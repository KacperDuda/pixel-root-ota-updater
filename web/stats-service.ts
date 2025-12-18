
import { FastbootDevice } from 'android-fastboot';
// No UI imports needed here! Pure logic.

export interface DeviceStats {
    isUserspace: boolean; // true = FastbootD, false = Bootloader
    unlocked: string; // 'yes', 'no', 'unknown'
}

let pollInterval: any = null;

export function stopStatsPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

export function startStatsPolling(
    device: FastbootDevice,
    onUpdate: (stats: DeviceStats) => void,
    intervalMs = 500
) {
    stopStatsPolling();

    pollInterval = setInterval(async () => {
        try {
            // Check Mode
            let isUserspace = 'no';
            try {
                isUserspace = await device.getVariable('is-userspace');
            } catch (e) {
                // Often fails if device is busy, assume bootloader/error
            }

            // Check Unlocked
            let unlocked = 'unknown';
            try {
                unlocked = await device.getVariable('unlocked');
            } catch (e) { }

            onUpdate({
                isUserspace: ((isUserspace || '').trim().toLowerCase() === 'yes'),
                unlocked: (unlocked || '').trim().toLowerCase()
            });

        } catch (e) {
            // If completely failed, maybe stop polling or just retry?
            // Retry for now.
        }
    }, intervalMs);
}
