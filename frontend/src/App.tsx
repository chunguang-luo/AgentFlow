import { useEffect, useState } from 'react';

import { getHealth, type Health } from './api';

type RequestState = 'loading' | 'ready' | 'error';

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [state, setState] = useState<RequestState>('loading');

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((result) => {
        setHealth(result);
        setState('ready');
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState('error');
        }
      });

    return () => controller.abort();
  }, []);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h1>AgentFlow</h1>
        </div>
        <span className={state === 'ready' ? 'status-pill ok' : 'status-pill'}>
          {state === 'loading' && 'Checking'}
          {state === 'ready' && health?.status === 'ok' && 'Healthy'}
          {state === 'ready' && health?.status !== 'ok' && 'Degraded'}
          {state === 'error' && 'Disconnected'}
        </span>
      </header>

      <section aria-label="Service status" className="status-panel">
        <div className="metric">
          <span>Environment</span>
          <strong>{state === 'ready' ? health?.environment : '-'}</strong>
        </div>
        <div className="metric">
          <span>API version</span>
          <strong>{state === 'ready' ? health?.version : '-'}</strong>
        </div>
        <div className="metric">
          <span>Database</span>
          <strong>{state === 'ready' ? health?.database.status : '-'}</strong>
        </div>
      </section>
    </main>
  );
}
