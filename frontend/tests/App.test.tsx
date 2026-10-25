import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from '../src/App';
import { getCurrentUser, getFlows, login } from '../src/api';

vi.mock('../src/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  getCurrentUser: vi.fn(),
  getFlows: vi.fn(),
  login: vi.fn(),
}));

const mockedGetCurrentUser = vi.mocked(getCurrentUser);
const mockedGetFlows = vi.mocked(getFlows);
const mockedLogin = vi.mocked(login);

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('routes anonymous users to login', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('unauthenticated'));

    render(<App />);

    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('authenticates and renders the flows workspace', async () => {
    mockedGetCurrentUser.mockResolvedValue({
      id: 'user-1',
      username: 'admin',
      email: null,
      display_name: 'Admin',
      role: 'admin',
    });
    mockedGetFlows.mockResolvedValue({
      items: [
        {
          id: 'flow-1',
          name: 'Repository analysis',
          description: null,
          status: 'published',
          current_version: 2,
          owner_id: 'user-1',
          created_at: '2026-10-26T00:00:00Z',
          updated_at: '2026-10-26T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(<App />);

    expect(await screen.findByText('Repository analysis')).toBeInTheDocument();
    expect(screen.getByText('published')).toBeInTheDocument();
  });

  it('logs in and transitions to the flows workspace', async () => {
    mockedGetCurrentUser.mockRejectedValue(new Error('unauthenticated'));
    mockedLogin.mockResolvedValue({
      id: 'user-1',
      username: 'admin',
      email: null,
      display_name: 'Admin',
      role: 'admin',
      token: 'token',
      token_type: 'Bearer',
    });
    mockedGetFlows.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });

    render(<App />);
    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: 'agentflow-admin' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mockedLogin).toHaveBeenCalledWith('admin', 'agentflow-admin'));
    expect(await screen.findByText('No flows match the current filters.')).toBeInTheDocument();
  });
});
