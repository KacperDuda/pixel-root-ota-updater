/// <reference types="vite/client" />

declare module 'android-fastboot' {
    export class FastbootDevice {
        connect(): Promise<void>;
        getVariable(name: string): Promise<string>;
        runCommand(cmd: string): Promise<void>;
        waitForConnect(): Promise<void>;
        upload(blob: Blob): Promise<void>;
        flashZip(device: any, blob: Blob, wipe: boolean, onReconnect: any, onProgress: any): Promise<void>;
    }
}
