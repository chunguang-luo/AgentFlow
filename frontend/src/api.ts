export type Health = {
  status: string;
  service: string;
  version: string;
  environment: string;
  database: {
    status: string;
    engine: string;
  };
};

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch('/api/health', {
    signal,
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Health request failed with ${response.status}`);
  }

  return response.json() as Promise<Health>;
}
