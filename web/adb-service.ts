import { Adb, AdbDaemonTransport } from '@yume-chan/adb';
import { AdbWebUsbBackend } from '@yume-chan/adb-backend-webusb';
import AdbWebCredentialStore from '@yume-chan/adb-credential-web';

export class AdbService {
    public adb: Adb | null = null;

    constructor() { }

    /**
     * Connects to the given USB device via ADB.
     */
    async connect(device: USBDevice): Promise<void> {
        try {
            const backend = new AdbWebUsbBackend(device, undefined, navigator.usb);
            const connection = await backend.connect();

            const CredentialStore = new AdbWebCredentialStore();

            const transport = await AdbDaemonTransport.authenticate({
                serial: device.serialNumber!,
                connection: connection as any,
                credentialStore: CredentialStore
            });

            this.adb = new Adb(transport);
        } catch (e: any) {
            console.error("AdbService Connect Failed:", e);
            throw e;
        }
    }

    /**
     * Fetches basic device info (Model, Version, Battery).
     */
    async fetchInfo() {
        if (!this.adb) throw new Error("ADB not connected");

        const runShell = async (cmd: string) => {
            if (!this.adb!.subprocess.shellProtocol) {
                throw new Error("Shell protocol not supported");
            }
            const result = await this.adb!.subprocess.shellProtocol.spawnWaitText(cmd);
            return result.stdout.trim();
        };

        try {
            const model = await runShell('getprop ro.product.model');
            const androidVer = await runShell('getprop ro.build.version.release');

            let batLevel = "Unknown";
            try {
                batLevel = await runShell('cmd battery get level');
            } catch (e) { }

            return { model, androidVer, batLevel };
        } catch (e) {
            console.error("Fetch Info Failed:", e);
            throw e;
        }
    }

    async rebootSystem(): Promise<void> {
        if (!this.adb) throw new Error("ADB not connected");
        try {
            await this.adb.power.reboot();
        } catch (e: any) {
            console.warn("Reboot system warning:", e);
        }
    }

    /**
     * Reboots the device to bootloader.
     */
    async rebootToBootloader(): Promise<void> {
        if (!this.adb) throw new Error("ADB not connected");
        try {
            await this.adb.power.bootloader();
        } catch (e: any) {
            if (!e.message.includes('NetworkError') && !e.message.includes('transferIn')) {
                console.warn("Reboot command warning:", e);
            }
        }
    }

    async dispose() {
        if (this.adb) {
            try {
                await this.adb.close();
            } catch (e) {
                console.warn("ADB Close Error:", e);
            }
            this.adb = null;
        }
    }
}
