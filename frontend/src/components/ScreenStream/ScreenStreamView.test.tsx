/**
 * ScreenStreamView — rendering tests.
 *
 * Verifies:
 *   - placeholder when sandboxId is null
 *   - proper flex layout for containing stream content
 *   - connection status indicator
 *   - frame rendering
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock useScreenStream hook
const mockUseScreenStream = vi.fn();
vi.mock('../../hooks/useScreenStream', () => ({
  useScreenStream: (...args: unknown[]) => mockUseScreenStream(...args),
}));

import { ScreenStreamView } from './ScreenStreamView';

describe('ScreenStreamView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseScreenStream.mockReturnValue({ frameUrl: null, isConnected: false });
  });

  it('shows placeholder when sandboxId is null', () => {
    render(<ScreenStreamView sandboxId={null} />);
    expect(screen.getByText('Select an agent with a sandbox to view its screen.')).toBeInTheDocument();
  });

  it('placeholder uses flex-1 for proper flex layout', () => {
    const { container } = render(<ScreenStreamView sandboxId={null} />);
    const placeholder = container.firstElementChild;
    expect(placeholder?.className).toContain('flex-1');
  });

  it('shows connecting state when sandboxId is set but not connected', () => {
    mockUseScreenStream.mockReturnValue({ frameUrl: null, isConnected: false });
    render(<ScreenStreamView sandboxId="sandbox-123" />);
    expect(screen.getByText('Connecting to sandbox display...')).toBeInTheDocument();
  });

  it('shows waiting state when connected but no frames', () => {
    mockUseScreenStream.mockReturnValue({ frameUrl: null, isConnected: true });
    render(<ScreenStreamView sandboxId="sandbox-123" />);
    expect(screen.getByText('Waiting for frames...')).toBeInTheDocument();
  });

  it('shows Live indicator when connected', () => {
    mockUseScreenStream.mockReturnValue({ frameUrl: null, isConnected: true });
    render(<ScreenStreamView sandboxId="sandbox-123" />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('renders image when frameUrl is available', () => {
    mockUseScreenStream.mockReturnValue({ frameUrl: 'blob:http://localhost/abc', isConnected: true });
    render(<ScreenStreamView sandboxId="sandbox-123" />);
    const img = screen.getByAltText('Sandbox screen');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', 'blob:http://localhost/abc');
  });

  it('main container has proper layout classes for flex sizing', () => {
    mockUseScreenStream.mockReturnValue({ frameUrl: null, isConnected: false });
    const { container } = render(<ScreenStreamView sandboxId="sandbox-123" />);
    const mainContainer = container.querySelector('.bg-black');
    expect(mainContainer).toBeInTheDocument();
    expect(mainContainer?.className).toContain('flex-1');
    expect(mainContainer?.className).toContain('min-h-0');
    expect(mainContainer?.className).toContain('overflow-hidden');
  });

  it('passes sandboxId to useScreenStream hook', () => {
    render(<ScreenStreamView sandboxId="sandbox-xyz" />);
    expect(mockUseScreenStream).toHaveBeenCalledWith('sandbox-xyz');
  });

  it('passes null to useScreenStream when sandboxId is null', () => {
    render(<ScreenStreamView sandboxId={null} />);
    expect(mockUseScreenStream).toHaveBeenCalledWith(null);
  });
});
