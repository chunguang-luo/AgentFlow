import { RefreshCw, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

import { getAuditLogs, type AuditLog } from '../api';
import { PageHeader } from '../components/PageHeader';

export function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState('');
  const [targetType, setTargetType] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getAuditLogs({
      page,
      pageSize: 20,
      action: action || undefined,
      targetType: targetType || undefined,
    })
      .then((result) => {
        if (!active) return;
        setLogs(result.items);
        setTotal(result.total);
        setError(null);
      })
      .catch((exc: unknown) => {
        if (active) setError(exc instanceof Error ? exc.message : 'Failed to load audit log');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [action, page, targetType]);

  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="page">
      <PageHeader
        title="Audit"
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
            aria-label="Filter audit action"
            placeholder="auth.login_failed"
            value={action}
            onChange={(event) => {
              setPage(1);
              setAction(event.target.value);
            }}
          />
        </div>
        <select
          aria-label="Audit target"
          value={targetType}
          onChange={(event) => {
            setPage(1);
            setTargetType(event.target.value);
          }}
        >
          <option value="">All targets</option>
          <option value="user">User</option>
          <option value="flow">Flow</option>
          <option value="run">Run</option>
          <option value="provider">Provider</option>
        </select>
      </section>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Target</th>
              <th>User</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="muted">
                  Loading audit entries
                </td>
              </tr>
            )}
            {!loading && logs.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No audit entries match the current filters.
                </td>
              </tr>
            )}
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{new Date(log.created_at).toLocaleString()}</td>
                <td>
                  <code>{log.action}</code>
                </td>
                <td>
                  {log.target_type}
                  {log.target_id ? ` / ${log.target_id}` : ''}
                </td>
                <td>{log.user_id ?? '-'}</td>
                <td>{log.ip_address ?? '-'}</td>
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
