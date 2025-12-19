import { Adb } from '@yume-chan/adb';
import { log } from './ui-utils';

export class SideloadService {
    constructor(private adb: Adb) { }

    /**
     * Performs the sideload of the given Blob.
     */
    async sideload(blob: Blob) {
        const size = blob.size;
        log(`Starting Sideload. File size: ${(size / 1024 / 1024).toFixed(2)} MB`);

        const socket = await this.adb.createSocket(`sideload:${size}`);

        const writer = socket.writable.getWriter();

        const CHUNK_SIZE = 64 * 1024;
        let offset = 0;

        const progressBar = document.getElementById('progress-bar') as HTMLProgressElement;

        try {
            while (offset < size) {
                const end = Math.min(offset + CHUNK_SIZE, size);
                const chunk = blob.slice(offset, end);
                const arrayBuffer = await chunk.arrayBuffer();
                const u8 = new Uint8Array(arrayBuffer);

                await writer.write(u8);

                offset += u8.byteLength;

                if (progressBar) {
                    progressBar.value = (offset / size) * 100;
                }
            }
            log("Sideload Transfer Complete. Waiting for device to verify...", "success");
        } catch (e: any) {
            log(`Sideload Transfer Interrupted: ${e.message}`, "error");
            throw e;
        } finally {
            writer.releaseLock();
            try { socket.close(); } catch (e) { }
        }
    }
}
