import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConnectionStatus } from './ConnectionStatus';

describe('ConnectionStatus', () => {
  it('shows Connected when isConnected is true', () => {
    render(<ConnectionStatus isConnected />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('shows Connecting... when isConnected is false', () => {
    render(<ConnectionStatus isConnected={false} />);
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });
});
