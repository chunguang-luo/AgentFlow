import { HeartPulse } from 'lucide-react';
import { useEffect, useState } from 'react';

import { checkProviderHealth, getProviders, type Provider } from '../api';
import { PageHeader } from '../components/PageHeader';

export function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getProviders()
      .then((result) => active && setProviders(result))
      .catch((exc: unknown) => {
        if (active) setError(exc instanceof Error ? exc.message : 'Failed to load providers');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const checkAll = async () => {
    setChecking(true);
    setError(null);
    try {
      const checked = await Promise.all(
        providers.map((provider) => checkProviderHealth(provider.name)),
      );
      setProviders(checked);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Health check failed');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Providers"
        actions={
          <button className="primary-button" onClick={checkAll} disabled={checking} type="button">
            <HeartPulse size={16} />
            <span>{checking ? 'Checking' : 'Check health'}</span>
          </button>
        }
      />

      {error && <div className="page-error">{error}</div>}
      <div className="provider-grid">
        {loading && <p className="muted">Loading providers</p>}
        {!loading &&
          providers.map((provider) => (
            <article className="provider-row" key={provider.name}>
              <div>
                <strong>{provider.name}</strong>
                <small>{provider.version ?? provider.message ?? 'Not checked'}</small>
              </div>
              <span
                className={`status-badge ${
                  provider.available === true
                    ? 'success'
                    : provider.available === false
                      ? 'danger'
                      : 'neutral'
                }`}
              >
                {provider.available === null
                  ? 'unknown'
                  : provider.available
                    ? 'available'
                    : 'unavailable'}
              </span>
            </article>
          ))}
      </div>
    </div>
  );
}
