import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { App } from '../src/App';
import { getHealth } from '../src/api';

vi.mock('../src/api', () => ({
  getHealth: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);

describe('App', () => {
  it('renders live service health', async () => {
    mockedGetHealth.mockResolvedValue({
      status: 'ok',
      service: 'AgentFlow',
      version: '1.0.0a0',
      environment: 'development',
      database: { status: 'ok', engine: 'sqlite' },
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText('Healthy')).toBeInTheDocument());
    expect(screen.getByText('development')).toBeInTheDocument();
    expect(screen.getByText('1.0.0a0')).toBeInTheDocument();
    expect(screen.getByText('ok')).toBeInTheDocument();
  });

  it('renders disconnected state when health cannot be loaded', async () => {
    mockedGetHealth.mockRejectedValue(new Error('network unavailable'));

    render(<App />);

    await waitFor(() => expect(screen.getByText('Disconnected')).toBeInTheDocument());
  });
});
