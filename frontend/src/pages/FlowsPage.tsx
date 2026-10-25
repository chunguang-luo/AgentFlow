import { History, Pencil, Play, Plus, RefreshCw, Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import {
  createRun,
  getFlow,
  getFlowVersion,
  getFlows,
  type FlowDefinition,
  type FlowSummary,
} from '../api';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function RunDialog({ flow, onClose }: { flow: FlowSummary; onClose: () => void }) {
  const [inputDefinitions, setInputDefinitions] = useState<FlowDefinition['inputs']>([]);
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    const definitionRequest = flow.current_version
      ? getFlowVersion(flow.id, flow.current_version).then((version) => version.definition)
      : getFlow(flow.id).then((detail) => detail.draft_definition);
    definitionRequest
      .then((definition) => {
        if (!active) return;
        setInputDefinitions(definition?.inputs ?? []);
        const initial: Record<string, unknown> = {};
        (definition?.inputs ?? []).forEach((input) => {
          if (input.default !== undefined && input.default !== null) {
            initial[input.name] = input.default;
          } else if (input.type === 'boolean') {
            initial[input.name] = false;
          }
        });
        setInputs(initial);
      })
      .catch((exc: unknown) => active && setError(exc instanceof Error ? exc.message : 'Failed'));
    return () => {
      active = false;
    };
  }, [flow.current_version, flow.id]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun({ flow_id: flow.id, inputs });
      navigate(`/runs/${run.id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Run failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <section className="modal">
        <header>
          <div>
            <strong>Run {flow.name}</strong>
            <p>Version {flow.current_version ?? 'latest'}</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>

        {inputDefinitions.length === 0 && <p className="muted">This flow has no inputs.</p>}

        <div className="form-grid">
          {inputDefinitions.map((input) => (
            <label key={input.name}>
              <span>
                {input.label ?? input.name}
                {input.required ? ' *' : ''}
              </span>
              {input.type === 'boolean' ? (
                <select
                  value={String(inputs[input.name] ?? false)}
                  onChange={(event) =>
                    setInputs((current) => ({
                      ...current,
                      [input.name]: event.target.value === 'true',
                    }))
                  }
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : input.type === 'json' ? (
                <textarea
                  rows={4}
                  value={String(inputs[input.name] ?? '')}
                  onChange={(event) => {
                    try {
                      setInputs((current) => ({
                        ...current,
                        [input.name]: event.target.value ? JSON.parse(event.target.value) : {},
                      }));
                    } catch {
                      // Keep the last valid value while the user edits JSON.
                    }
                  }}
                />
              ) : (
                <input
                  type={input.type === 'number' ? 'number' : 'text'}
                  value={String(inputs[input.name] ?? '')}
                  onChange={(event) =>
                    setInputs((current) => ({
                      ...current,
                      [input.name]:
                        input.type === 'number' ? Number(event.target.value) : event.target.value,
                    }))
                  }
                />
              )}
            </label>
          ))}
        </div>

        {error && <div className="form-error">{error}</div>}
        <footer>
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="primary-button" onClick={submit} disabled={submitting}>
            <Play size={16} />
            <span>{submitting ? 'Starting' : 'Start run'}</span>
          </button>
        </footer>
      </section>
    </div>
  );
}

export function FlowsPage() {
  const listNavigate = useNavigate();
  const [flows, setFlows] = useState<FlowSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runFlow, setRunFlow] = useState<FlowSummary | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = setTimeout(() => {
      getFlows({ page, pageSize: 20, name: search || undefined, status: status || undefined })
        .then((result) => {
          if (!active) return;
          setFlows(result.items);
          setTotal(result.total);
          setError(null);
        })
        .catch((exc: unknown) => {
          if (active) setError(exc instanceof Error ? exc.message : 'Failed to load flows');
        })
        .finally(() => active && setLoading(false));
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [page, search, status]);

  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="page">
      <PageHeader
        title="Flows"
        actions={
          <>
            <button
              type="button"
              className="ghost-button"
              onClick={() => setPage(1)}
              aria-label="Refresh"
            >
              <RefreshCw size={16} />
            </button>
            <Link className="primary-button" to="/flows/new">
              <Plus size={16} />
              <span>New Flow</span>
            </Link>
          </>
        }
      />

      <section className="toolbar">
        <div className="input-icon search">
          <Search size={16} />
          <input
            value={search}
            onChange={(event) => {
              setPage(1);
              setSearch(event.target.value);
            }}
            placeholder="Search flows"
          />
        </div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label="Status"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
        </select>
      </section>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Version</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="muted">
                  Loading flows
                </td>
              </tr>
            )}
            {!loading && flows.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No flows match the current filters.
                </td>
              </tr>
            )}
            {flows.map((flow) => (
              <tr key={flow.id} onClick={() => listNavigate(`/flows/${flow.id}/edit`)}>
                <td>
                  <strong>{flow.name}</strong>
                  {flow.description && <small>{flow.description}</small>}
                </td>
                <td>
                  <StatusBadge status={flow.status} />
                </td>
                <td>{flow.current_version ?? '-'}</td>
                <td>{formatDate(flow.updated_at)}</td>
                <td>
                  <div className="row-actions" onClick={(event) => event.stopPropagation()}>
                    <Link className="icon-button" to={`/flows/${flow.id}/edit`} aria-label="Edit">
                      <Pencil size={15} />
                    </Link>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => setRunFlow(flow)}
                      aria-label="Run"
                    >
                      <Play size={15} />
                    </button>
                    <Link
                      className="icon-button"
                      to={`/flows/${flow.id}/edit?panel=versions`}
                      aria-label="Versions"
                    >
                      <History size={15} />
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="pagination">
        <button
          type="button"
          className="ghost-button"
          onClick={() => setPage((v) => v - 1)}
          disabled={page <= 1}
        >
          Previous
        </button>
        <span>
          Page {page} / {pageCount}
        </span>
        <button
          type="button"
          className="ghost-button"
          onClick={() => setPage((v) => v + 1)}
          disabled={page >= pageCount}
        >
          Next
        </button>
      </footer>

      {runFlow && <RunDialog flow={runFlow} onClose={() => setRunFlow(null)} />}
    </div>
  );
}
