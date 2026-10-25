import { Tag } from 'lucide-react';

import type { FlowVersion } from '../api';

export function FlowVersionsPanel({
  flowId,
  versions,
}: {
  flowId: string | null;
  versions: FlowVersion[] | null;
}) {
  if (!flowId) return <p className="muted">Save the flow to create versions.</p>;
  if (!versions) return <p className="muted">Loading versions</p>;
  if (versions.length === 0) return <p className="muted">No published versions.</p>;

  return (
    <div className="versions-panel">
      {versions.map((version) => (
        <article key={version.id}>
          <div>
            <strong>Version {version.version}</strong>
            <small>{new Date(version.created_at).toLocaleString()}</small>
          </div>
          <a
            className="ghost-button"
            href={`/api/flows/${flowId}/export?version=${version.version}`}
          >
            <Tag size={14} />
            <span>JSON</span>
          </a>
        </article>
      ))}
    </div>
  );
}
