/**
 * VncView — end-to-end rendering tests.
 *
 * Verifies that:
 *   - placeholder shows when sandboxId is null
 *   - VNC canvas container renders with proper layout when sandboxId is set
 *   - connection status indicator shows correct state
 *   - interactive toggle works
 *   - component cleans up on unmount
 */

import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Shared state for capturing mock RFB instances
const rfbState = {
  instances: [] as Array<{
    container: HTMLElement;
    url: string;
    options?: Record<string, unknown>;
    scaleViewport: boolean;
    resizeSession: boolean;
    viewOnly: boolean;
    focusOnClick: boolean;
    qualityLevel: number;
    compressionLevel: number;
    disconnect: ReturnType<typeof vi.fn>;
    listeners: Record<string, Array<(...args: unknown[]) => void>>;
  }>,
};

vi.mock('@novnc/novnc/lib/rfb', () => {
  return {
    default: class MockRFB {
      scaleViewport = false;
      resizeSession = false;
      viewOnly = false;
      focusOnClick = false;
      qualityLevel = 0;
      compressionLevel = 0;
      disconnect = vi.fn();
      listeners: Record<string, Array<(...args: unknown[]) => void>> = {};

      constructor(
        public container: HTMLElement,
        public url: string,
        public options?: Record<string, unknown>,
      ) {
        rfbState.instances.push(this as typeof rfbState.instances[0]);
      }

      addEventListener(event: string, handler: (...args: unknown[]) => void) {
        if (!this.listeners[event]) {
          this.listeners[event] = [];
        }
        this.listeners[event].push(handler);
      }
    },
  };
});

// Mock getAuthToken
vi.mock('../../api/client', () => ({
  getAuthToken: vi.fn(() => 'mock-token'),
}));

import { VncView } from './VncView';

describe('VncView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    rfbState.instances = [];

    Object.defineProperty(window, 'location', {
      value: { protocol: 'http:', host: 'localhost:3000' },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows placeholder when sandboxId is null', () => {
    render(<VncView sandboxId={null} />);
    expect(screen.getByText('Select an agent with a sandbox to view its screen.')).toBeInTheDocument();
  });

  it('placeholder uses flex-1 for proper layout in flex parent', () => {
    const { container } = render(<VncView sandboxId={null} />);
    const placeholder = container.firstElementChild;
    expect(placeholder?.className).toContain('flex-1');
  });

  it('renders VNC container when sandboxId is provided', async () => {
    let container: HTMLElement;
    await act(async () => {
      const result = render(<VncView sandboxId="sandbox-123" />);
      container = result.container;
    });

    expect(screen.queryByText('Select an agent with a sandbox to view its screen.')).not.toBeInTheDocument();
    const vncContainer = container!.querySelector('.bg-black');
    expect(vncContainer).toBeInTheDocument();
  });

  it('creates RFB connection with correct URL when sandboxId is set', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-abc" />);
    });

    expect(rfbState.instances).toHaveLength(1);
    const instance = rfbState.instances[0];
    expect(instance.url).toContain('ws://localhost:3000/ws/vnc');
    expect(instance.url).toContain('token=mock-token');
    expect(instance.url).toContain('sandbox_id=sandbox-abc');
    expect(instance.options).toEqual({ shared: true });
  });

  it('configures RFB with scaleViewport and correct settings', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" />);
    });

    expect(rfbState.instances).toHaveLength(1);
    const instance = rfbState.instances[0];
    expect(instance.scaleViewport).toBe(true);
    expect(instance.resizeSession).toBe(false);
    expect(instance.viewOnly).toBe(false);
    expect(instance.focusOnClick).toBe(true);
    expect(instance.qualityLevel).toBe(6);
    expect(instance.compressionLevel).toBe(2);
  });

  it('registers connect and disconnect event listeners on RFB', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" />);
    });

    const instance = rfbState.instances[0];
    expect(instance.listeners['connect']?.length).toBeGreaterThanOrEqual(1);
    expect(instance.listeners['disconnect']?.length).toBeGreaterThanOrEqual(1);
  });

  it('updates status to connected when RFB connects', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" />);
    });

    await act(async () => {
      rfbState.instances[0].listeners['connect']?.forEach((h) => h());
    });

    expect(screen.getByText('VNC Live')).toBeInTheDocument();
  });

  it('sets viewOnly when viewOnly prop is true', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" viewOnly />);
    });

    expect(rfbState.instances[0].viewOnly).toBe(true);
  });

  it('toggles interactive mode when button is clicked', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" />);
    });

    const toggleBtn = screen.getByText('Interactive');
    expect(toggleBtn).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByText('View Only')).toBeInTheDocument();
  });

  it('disconnects RFB when sandboxId changes to null', async () => {
    let rerender: (ui: React.ReactNode) => void;
    await act(async () => {
      const result = render(<VncView sandboxId="sandbox-123" />);
      rerender = result.rerender;
    });

    const firstInstance = rfbState.instances[0];

    await act(async () => {
      rerender!(<VncView sandboxId={null} />);
    });

    expect(firstInstance.disconnect).toHaveBeenCalled();
    expect(screen.getByText('Select an agent with a sandbox to view its screen.')).toBeInTheDocument();
  });

  it('VNC outer container has proper flex layout classes', async () => {
    let container: HTMLElement;
    await act(async () => {
      const result = render(<VncView sandboxId="sandbox-123" />);
      container = result.container;
    });

    const outer = container!.querySelector('.bg-black');
    expect(outer).toBeInTheDocument();
    expect(outer?.className).toContain('flex');
    expect(outer?.className).toContain('flex-col');
    expect(outer?.className).toContain('flex-1');
    expect(outer?.className).toContain('min-h-0');
  });

  it('canvas container has overflow-hidden to contain noVNC content', async () => {
    let container: HTMLElement;
    await act(async () => {
      const result = render(<VncView sandboxId="sandbox-123" />);
      container = result.container;
    });

    // The containerRef div should have overflow-hidden
    const canvasContainers = container!.querySelectorAll('.overflow-hidden');
    const hasFlexOverflow = Array.from(canvasContainers).some(
      (el) => el.className.includes('flex-1') && el.className.includes('min-h-0')
    );
    expect(hasFlexOverflow).toBe(true);
  });

  it('shows disconnected overlay after VNC disconnect event', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" />);
    });

    await act(async () => {
      rfbState.instances[0].listeners['disconnect']?.forEach((h) => h());
    });

    expect(screen.getByText(/Connecting to sandbox display/)).toBeInTheDocument();
  });

  it('noVNC RFB is created with the container element', async () => {
    await act(async () => {
      render(<VncView sandboxId="sandbox-123" />);
    });

    expect(rfbState.instances).toHaveLength(1);
    expect(rfbState.instances[0].container).toBeInstanceOf(HTMLElement);
  });
});
