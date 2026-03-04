/**
 * Type declarations for @novnc/novnc — browser-side VNC client.
 * Only the public API surface used by our VncView component is declared.
 */
declare module '@novnc/novnc/lib/rfb' {
  interface RFBOptions {
    shared?: boolean;
    credentials?: { username?: string; password?: string; target?: string };
    repeaterID?: string;
    wsProtocols?: string[];
  }

  export default class RFB extends EventTarget {
    constructor(target: HTMLElement, urlOrChannel: string | WebSocket, options?: RFBOptions);

    /* ── Writable properties ────────────────────────────────────── */
    viewOnly: boolean;
    focusOnClick: boolean;
    clipViewport: boolean;
    dragViewport: boolean;
    scaleViewport: boolean;
    resizeSession: boolean;
    showDotCursor: boolean;
    background: string;
    qualityLevel: number;      // 0–9
    compressionLevel: number;  // 0–9

    /* ── Read-only properties ───────────────────────────────────── */
    readonly capabilities: { power: boolean };

    /* ── Methods ────────────────────────────────────────────────── */
    disconnect(): void;
    sendCredentials(credentials: { username?: string; password?: string; target?: string }): void;
    sendKey(keysym: number, code: string | null, down?: boolean): void;
    sendCtrlAltDel(): void;
    focus(): void;
    blur(): void;
    machineShutdown(): void;
    machineReboot(): void;
    machineReset(): void;
    clipboardPasteFrom(text: string): void;

    /* ── Events (CustomEvent<T>) ────────────────────────────────── */
    addEventListener(type: 'connect', listener: (ev: CustomEvent) => void): void;
    addEventListener(type: 'disconnect', listener: (ev: CustomEvent<{ clean: boolean }>) => void): void;
    addEventListener(type: 'credentialsrequired', listener: (ev: CustomEvent<{ types: string[] }>) => void): void;
    addEventListener(type: 'securityfailure', listener: (ev: CustomEvent<{ status: number; reason: string }>) => void): void;
    addEventListener(type: 'clipboard', listener: (ev: CustomEvent<{ text: string }>) => void): void;
    addEventListener(type: 'bell', listener: (ev: CustomEvent) => void): void;
    addEventListener(type: 'desktopname', listener: (ev: CustomEvent<{ name: string }>) => void): void;
    addEventListener(type: 'desktopresize', listener: (ev: CustomEvent<{ width: number; height: number }>) => void): void;
    addEventListener(type: string, listener: EventListenerOrEventListenerObject, options?: boolean | AddEventListenerOptions): void;

    removeEventListener(type: string, listener: EventListenerOrEventListenerObject, options?: boolean | EventListenerOptions): void;
  }
}
