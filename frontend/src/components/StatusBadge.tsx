const statusClassNames: Record<string, string> = {
  succeeded: 'success',
  published: 'success',
  running: 'info',
  pending: 'neutral',
  ready: 'info',
  draft: 'neutral',
  failed: 'danger',
  timeout: 'danger',
  cancelled: 'neutral',
  skipped: 'neutral',
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge ${statusClassNames[status] ?? 'neutral'}`}>{status}</span>;
}
