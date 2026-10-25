import { ArrowLeft, Ban, RotateCcw } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  cancelRun,
  getFlowVersion,
  getRun,
  getRunArtifacts,
  getRunLogs,
  getRunSteps,
  retryRun,
  type AgentLog,
  type Artifact,
  type FlowDefinition,
  type RunResponse,
  type StepRun,
} from '../api';
import { StatusBadge } from '../components/StatusBadge';

const eventTypes = [
  'run.created',
  'run.started',
  'run.succeeded',
  'run.failed',
  'run.cancelled',
  'step.ready',
  'step.started',
  'step.succeeded',
  'step.failed',
  'step.timeout',
  'step.cancelled',
  'step.skipped',
];

const terminalEventTypes = new Set(['run.succeeded', 'run.failed', 'run.cancelled']);

type Tab = 'overview' | 'steps' | 'logs' | 'artifacts' | 'report';

export function RunDetailPage() {
  const runId = useParams().runId ?? '';
  const navigate = useNavigate();
  const [run, setRun] = useState<RunResponse | null>(null);
  const [steps, setSteps] = useState<StepRun[]>([]);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [definition, setDefinition] = useState<FlowDefinition | null>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loadRef = useRef<() => void>(() => undefined);

  const load = useCallback(async () => {
    try {
      const [currentRun, currentSteps, currentLogs, currentArtifacts] = await Promise.all([
        getRun(runId),
        getRunSteps(runId),
        getRunLogs(runId),
        getRunArtifacts(runId),
      ]);
      setRun(currentRun);
      setSteps(currentSteps);
      setLogs(currentLogs);
      setArtifacts(currentArtifacts);
      setError(null);
      try {
        const version = await getFlowVersion(currentRun.flow_id, currentRun.flow_version);
        setDefinition(version.definition);
      } catch {
        setDefinition(null);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Failed to load run');
    }
  }, [runId]);

  loadRef.current = () => void load();

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/events`);
    const refresh = (event: MessageEvent) => {
      if (terminalEventTypes.has(event.type)) {
        source.close();
      }
      loadRef.current();
    };
    eventTypes.forEach((eventType) => source.addEventListener(eventType, refresh));
    return () => source.close();
  }, [runId]);

  const terminal = run?.status
    ? ['succeeded', 'failed', 'cancelled', 'timeout'].includes(run.status)
    : false;

  useEffect(() => {
    if (terminal) return;
    const timer = window.setInterval(() => loadRef.current(), 1500);
    return () => window.clearInterval(timer);
  }, [terminal]);

  const statusByStepId = useMemo(
    () => new Map(steps.map((step) => [step.step_id, step.status])),
    [steps],
  );

  const nodes = useMemo<Node[]>(
    () =>
      (definition?.steps ?? []).map((step, index) => ({
        id: step.id,
        position: { x: (index % 3) * 230, y: Math.floor(index / 3) * 160 },
        data: {
          label: (
            <div className={`run-flow-node ${statusByStepId.get(step.id) ?? 'pending'}`}>
              <strong>{step.name}</strong>
              <span>{statusByStepId.get(step.id) ?? 'pending'}</span>
            </div>
          ),
        },
      })),
    [definition?.steps, statusByStepId],
  );

  const edges = useMemo<Edge[]>(
    () =>
      (definition?.steps ?? []).flatMap((step) =>
        step.depends_on.map((source) => ({
          id: `${source}-${step.id}`,
          source,
          target: step.id,
          animated: !terminal,
        })),
      ),
    [definition?.steps, terminal],
  );

  const cancel = async () => {
    setBusy(true);
    try {
      setRun(await cancelRun(runId));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Cancel failed');
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    setBusy(true);
    try {
      const nextRun = await retryRun(runId);
      navigate(`/runs/${nextRun.id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Retry failed');
      setBusy(false);
    }
  };

  if (!run) {
    return (
      <div className="page">
        <p className="muted">{error ?? 'Loading run'}</p>
        {error && <div className="page-error">{error}</div>}
      </div>
    );
  }

  const analysis = run.result?.analysis as { text?: string } | undefined;

  return (
    <div className="page run-page">
      <div className="breadcrumb">
        <Link className="ghost-button" to="/runs">
          <ArrowLeft size={16} />
          <span>Runs</span>
        </Link>
        <StatusBadge status={run.status} />
        <span className="muted">Version {run.flow_version}</span>
      </div>

      <header className="run-header">
        <div>
          <h1>Run {run.id}</h1>
          <p>
            Flow <code>{run.flow_id}</code>
          </p>
        </div>
        <div className="page-actions">
          {!terminal && (
            <button className="danger-button" disabled={busy} onClick={cancel} type="button">
              <Ban size={15} />
              <span>Cancel</span>
            </button>
          )}
          {terminal && run.status !== 'succeeded' && (
            <button className="primary-button" disabled={busy} onClick={retry} type="button">
              <RotateCcw size={15} />
              <span>Retry</span>
            </button>
          )}
        </div>
      </header>

      {error && <div className="page-error">{error}</div>}

      <div className="run-layout">
        <section className="run-graph">
          <ReactFlow
            edges={edges}
            fitView
            nodes={nodes}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} />
            <Controls showInteractive={false} />
            <MiniMap />
          </ReactFlow>
        </section>

        <section className="run-panel">
          <div className="segmented">
            {(['overview', 'steps', 'logs', 'artifacts', 'report'] as const).map((item) => (
              <button
                className={tab === item ? 'active' : ''}
                key={item}
                onClick={() => setTab(item)}
                type="button"
              >
                {item}
              </button>
            ))}
          </div>

          {tab === 'overview' && (
            <div className="detail-list">
              <div>
                <span>Run ID</span>
                <strong>{run.id}</strong>
              </div>
              <div>
                <span>Status</span>
                <strong>{run.status}</strong>
              </div>
              <div>
                <span>Inputs</span>
                <pre>{JSON.stringify(run.inputs, null, 2)}</pre>
              </div>
              {run.error && (
                <div>
                  <span>Error</span>
                  <pre>{run.error}</pre>
                </div>
              )}
            </div>
          )}

          {tab === 'steps' && (
            <div className="table-wrap compact">
              <table>
                <thead>
                  <tr>
                    <th>Step</th>
                    <th>Status</th>
                    <th>Attempt</th>
                    <th>Input</th>
                    <th>Output</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map((step) => (
                    <tr key={step.id}>
                      <td>{step.step_id}</td>
                      <td>
                        <StatusBadge status={step.status} />
                      </td>
                      <td>{step.attempt}</td>
                      <td>
                        {step.input_snapshot ? (
                          <details className="cell-json">
                            <summary>JSON</summary>
                            <pre>{JSON.stringify(step.input_snapshot, null, 2)}</pre>
                          </details>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td>
                        {step.output ? (
                          <details className="cell-json">
                            <summary>JSON</summary>
                            <pre>{JSON.stringify(step.output, null, 2)}</pre>
                          </details>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td>{step.error ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'logs' && (
            <div className="log-list">
              {logs.length === 0 && <p className="muted">No provider logs.</p>}
              {logs.map((log) => (
                <article key={log.id}>
                  <span>{log.stream}</span>
                  <pre>{log.content}</pre>
                </article>
              ))}
            </div>
          )}

          {tab === 'artifacts' && (
            <div className="artifact-list">
              {artifacts.length === 0 && <p className="muted">No artifacts.</p>}
              {artifacts.map((artifact) => (
                <article key={artifact.id}>
                  <div>
                    <strong>{artifact.relative_path}</strong>
                    <small>
                      {artifact.content_type} / {artifact.size_bytes} bytes
                    </small>
                  </div>
                  <a className="ghost-button" href={`/api/artifacts/${artifact.id}/download`}>
                    Download
                  </a>
                </article>
              ))}
            </div>
          )}

          {tab === 'report' && (
            <div className="report-panel">
              {analysis ? (
                <pre>{analysis.text ?? JSON.stringify(analysis, null, 2)}</pre>
              ) : (
                <p className="muted">No final analysis output.</p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
