import { RefreshCw, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { getRuns, type RunResponse } from '../api';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';

export function RunsPage() {
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [flowId, setFlowId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getRuns({
      page,
      pageSize: 20,
      status: status || undefined,
      flowId: flowId || undefined,
    })
      .then((result) => {
        if (!active) return;
        setRuns(result.items);
        setTotal(result.total);
        setError(null);
      })
      .catch((exc: unknown) => {
        if (active) setError(exc instanceof Error ? exc.message : 'Failed to load runs');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [flowId, page, status]);

  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="page">
      <PageHeader
        title="Runs"
        actions={
          <button className="ghost-button" onClick={() => setPage(1)} type="button">
            <RefreshCw size={16} />
            <span>Refresh</span>
          </button>
        }
      />

      <section className="toolbar">
        <div className="input-icon search">
          <Search size={16} />
          <input
            placeholder="Filter by flow ID"
            value={flowId}
            onChange={(event) => {
              setPage(1);
              setFlowId(event.target.value);
            }}
          />
        </div>
        <select
          aria-label="Run status"
          value={status}
          onChange={(event) => {
            setPage(1);
            setStatus(event.target.value);
          }}
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="running">Running</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </section>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Flow</th>
              <th>Status</th>
              <th>Version</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="muted">
                  Loading runs
                </td>
              </tr>
            )}
            {!loading && runs.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No runs match the current filters.
                </td>
              </tr>
            )}
            {runs.map((run) => (
              <tr key={run.id}>
                <td>
                  <Link to={`/runs/${run.id}`}>
                    <code>{run.id}</code>
                  </Link>
                </td>
                <td>
                  <code>{run.flow_id}</code>
                </td>
                <td>
                  <StatusBadge status={run.status} />
                </td>
                <td>{run.flow_version}</td>
                <td className="result-cell">
                  {run.error ?? JSON.stringify(run.result ?? {}).slice(0, 120)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="pagination">
        <button
          className="ghost-button"
          disabled={page <= 1}
          onClick={() => setPage((value) => value - 1)}
          type="button"
        >
          Previous
        </button>
        <span>
          Page {page} / {pageCount}
        </span>
        <button
          className="ghost-button"
          disabled={page >= pageCount}
          onClick={() => setPage((value) => value + 1)}
          type="button"
        >
          Next
        </button>
      </footer>
    </div>
  );
}
