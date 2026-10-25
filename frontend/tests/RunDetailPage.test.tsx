import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { RunDetailPage } from '../src/pages/RunDetailPage';
import { getFlowVersion, getRun, getRunArtifacts, getRunLogs, getRunSteps } from '../src/api';

vi.mock('../src/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  getRun: vi.fn(),
  getRunSteps: vi.fn(),
  getRunLogs: vi.fn(),
  getRunArtifacts: vi.fn(),
  getFlowVersion: vi.fn(),
}));

const eventSourceInstances: {
  close: ReturnType<typeof vi.fn>;
  listeners: Map<string, (event: { type: string }) => void>;
}[] = [];

class EventSourceMock {
  close = vi.fn();
  listeners = new Map<string, (event: { type: string }) => void>();

  constructor() {
    eventSourceInstances.push(this);
  }

  addEventListener(type: string, listener: (event: { type: string }) => void) {
    this.listeners.set(type, listener);
  }
}

vi.stubGlobal('EventSource', EventSourceMock);

const mockedGetRun = vi.mocked(getRun);
const mockedGetRunSteps = vi.mocked(getRunSteps);
const mockedGetRunLogs = vi.mocked(getRunLogs);
const mockedGetRunArtifacts = vi.mocked(getRunArtifacts);
const mockedGetFlowVersion = vi.mocked(getFlowVersion);

describe('RunDetailPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
    eventSourceInstances.length = 0;
  });

  it('renders execution state, report, logs, and artifacts', async () => {
    mockedGetRun.mockResolvedValue({
      id: 'run-1',
      flow_id: 'flow-1',
      flow_version: 1,
      status: 'succeeded',
      inputs: { repository: 'agentflow' },
      result: {
        analysis: { text: 'Final analysis report' },
        steps: { analyze: { text: 'analysis output' } },
      },
      error: null,
    });
    mockedGetRunSteps.mockResolvedValue([
      {
        id: 'step-run-1',
        step_id: 'analyze',
        step_type: 'agent',
        status: 'succeeded',
        attempt: 1,
        error: null,
        input_snapshot: { prompt: 'Analyze repository' },
        output: { text: 'analysis output' },
      },
    ]);
    mockedGetRunLogs.mockResolvedValue([
      {
        id: 'log-1',
        step_run_id: 'step-run-1',
        stream: 'stdout',
        sequence: 1,
        content: 'provider stdout',
      },
    ]);
    mockedGetRunArtifacts.mockResolvedValue([
      {
        id: 'artifact-1',
        run_id: 'run-1',
        step_run_id: 'step-run-1',
        relative_path: 'report.md',
        content_type: 'text/markdown',
        size_bytes: 32,
        sha256: 'hash',
      },
    ]);
    mockedGetFlowVersion.mockResolvedValue({
      id: 'version-1',
      flow_id: 'flow-1',
      version: 1,
      schema_version: '1.0',
      created_by: 'user-1',
      created_at: '2026-10-26T00:00:00Z',
      definition: {
        name: 'Flow',
        inputs: [],
        steps: [
          {
            id: 'analyze',
            name: 'Analyze',
            type: 'agent',
            depends_on: [],
            config: {},
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={['/runs/run-1']}>
        <RunDetailPage />
      </MemoryRouter>,
    );

    const succeededElements = await screen.findAllByText('succeeded');
    expect(succeededElements.length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /report/i }));
    expect(await screen.findByText(/final analysis report/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /logs/i }));
    expect(await screen.findByText(/provider stdout/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /artifacts/i }));
    expect(await screen.findByText('report.md')).toBeInTheDocument();

    const eventSource = eventSourceInstances[0];
    await act(async () => {
      eventSource.listeners.get('run.succeeded')?.({ type: 'run.succeeded' });
    });
    expect(eventSource.close).toHaveBeenCalled();
  });
});
