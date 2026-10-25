import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getAuditLogs } from '../src/api';
import { AuditPage } from '../src/pages/AuditPage';

vi.mock('../src/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  getAuditLogs: vi.fn(),
}));

const mockedGetAuditLogs = vi.mocked(getAuditLogs);

describe('AuditPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders audit entries and filters by target', async () => {
    mockedGetAuditLogs.mockResolvedValue({
      items: [
        {
          id: 'audit-1',
          user_id: 'user-1',
          action: 'flow.published',
          target_type: 'flow',
          target_id: 'flow-1',
          details: {},
          ip_address: '127.0.0.1',
          user_agent: 'test',
          created_at: '2026-10-26T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(
      <MemoryRouter>
        <AuditPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('flow.published')).toBeInTheDocument();
    expect(screen.getByText('flow / flow-1')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Audit target'), { target: { value: 'run' } });
    await waitFor(() =>
      expect(mockedGetAuditLogs).toHaveBeenLastCalledWith({
        page: 1,
        pageSize: 20,
        targetType: 'run',
      }),
    );
    expect(await screen.findByText('flow.published')).toBeInTheDocument();
  });
});
