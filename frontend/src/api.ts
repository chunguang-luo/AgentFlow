export type Health = {
  status: string;
  service: string;
  version: string;
  environment: string;
  database: { status: string; engine: string };
};

export type CurrentUser = {
  id: string;
  username: string;
  email: string | null;
  display_name: string | null;
  role: string;
};

export type LoginResponse = CurrentUser & { token: string; token_type: string };

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type FlowInputDefinition = {
  name: string;
  label?: string | null;
  type: 'string' | 'number' | 'boolean' | 'json';
  required: boolean;
  default?: unknown;
  description?: string | null;
};

export type StepType =
  'input' | 'template' | 'agent' | 'condition' | 'parallel' | 'join' | 'analysis';

export type StepDefinition = {
  id: string;
  name: string;
  type: StepType;
  depends_on: string[];
  config: Record<string, unknown>;
};

export type FlowDefinition = {
  schema_version?: '1.0';
  name: string;
  description?: string | null;
  inputs: FlowInputDefinition[];
  execution?: {
    failure_strategy?: 'fail_fast' | 'continue';
  };
  steps: StepDefinition[];
};

export type FlowSummary = {
  id: string;
  name: string;
  description: string | null;
  status: 'draft' | 'published' | 'archived';
  current_version: number | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
};

export type FlowDetail = FlowSummary & { draft_definition: FlowDefinition | null };

export type FlowVersion = {
  id: string;
  flow_id: string;
  version: number;
  definition: FlowDefinition;
  schema_version: string;
  created_by: string;
  created_at: string;
};

export type RunResponse = {
  id: string;
  flow_id: string;
  flow_version: number;
  status: string;
  inputs: Record<string, unknown>;
  result: { analysis?: unknown; steps?: Record<string, unknown> } | null;
  error: string | null;
};

export type StepRun = {
  id: string;
  step_id: string;
  step_type: string;
  status: string;
  attempt: number;
  error: string | null;
  input_snapshot: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
};

export type AgentLog = {
  id: string;
  step_run_id: string;
  stream: string;
  sequence: number;
  content: string;
};

export type Artifact = {
  id: string;
  run_id: string;
  step_run_id: string;
  relative_path: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
};

export type Provider = {
  name: string;
  available: boolean | null;
  version: string | null;
  message: string | null;
};

export type AuditLog = {
  id: string;
  user_id: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
};

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type ErrorResponse = {
  error?: { code?: string; message?: string; details?: unknown };
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  headers.set('Accept', 'application/json');

  const response = await fetch(path, { ...options, headers, credentials: 'include' });
  if (!response.ok) {
    let code = 'request_failed';
    let message = `Request failed with ${response.status}`;
    let details: unknown = null;
    try {
      const body = (await response.json()) as ErrorResponse;
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
      details = body.error?.details ?? details;
    } catch {
      // Keep the HTTP status fallback.
    }
    throw new ApiError(response.status, code, message, details);
  }
  return (await response.json()) as T;
}

export function getHealth(signal?: AbortSignal) {
  return request<Health>('/api/health', { signal });
}

export function login(username: string, password: string) {
  return request<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request<CurrentUser>('/api/auth/logout', { method: 'POST' });
}

export function getCurrentUser() {
  return request<CurrentUser>('/api/auth/me');
}

export function getFlows(params: {
  page?: number;
  pageSize?: number;
  name?: string;
  status?: string;
  sort?: string;
}) {
  const search = new URLSearchParams();
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('page_size', String(params.pageSize));
  if (params.name) search.set('name', params.name);
  if (params.status) search.set('status', params.status);
  if (params.sort) search.set('sort', params.sort);
  return request<Page<FlowSummary>>(`/api/flows?${search.toString()}`);
}

export function getFlow(flowId: string) {
  return request<FlowDetail>(`/api/flows/${flowId}`);
}

export function createFlow(definition: FlowDefinition) {
  return request<FlowDetail>('/api/flows', {
    method: 'POST',
    body: JSON.stringify(definition),
  });
}

export function updateFlow(flowId: string, definition: FlowDefinition) {
  return request<FlowDetail>(`/api/flows/${flowId}`, {
    method: 'PUT',
    body: JSON.stringify(definition),
  });
}

export function validateFlow(definition: FlowDefinition) {
  return request<{ valid: boolean; definition: FlowDefinition }>('/api/flows/validate', {
    method: 'POST',
    body: JSON.stringify(definition),
  });
}

export function publishFlow(flowId: string) {
  return request<FlowVersion>(`/api/flows/${flowId}/publish`, { method: 'POST' });
}

export function getFlowVersions(flowId: string) {
  return request<FlowVersion[]>(`/api/flows/${flowId}/versions`);
}

export function getFlowVersion(flowId: string, version: number) {
  return request<FlowVersion>(`/api/flows/${flowId}/versions/${version}`);
}

export function exportFlow(flowId: string, version?: number, draft = false) {
  const search = new URLSearchParams();
  if (version) search.set('version', String(version));
  if (draft) search.set('draft', 'true');
  const suffix = search.size ? `?${search.toString()}` : '';
  return request<FlowDefinition>(`/api/flows/${flowId}/export${suffix}`);
}

export function getRuns(params: {
  page?: number;
  pageSize?: number;
  status?: string;
  flowId?: string;
  sort?: string;
}) {
  const search = new URLSearchParams();
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('page_size', String(params.pageSize));
  if (params.status) search.set('status', params.status);
  if (params.flowId) search.set('flow_id', params.flowId);
  if (params.sort) search.set('sort', params.sort);
  return request<Page<RunResponse>>(`/api/runs?${search.toString()}`);
}

export function getRun(runId: string) {
  return request<RunResponse>(`/api/runs/${runId}`);
}

export function getRunSteps(runId: string) {
  return request<StepRun[]>(`/api/runs/${runId}/steps`);
}

export function getRunLogs(runId: string, stepId?: string) {
  const suffix = stepId ? `?step_id=${encodeURIComponent(stepId)}` : '';
  return request<AgentLog[]>(`/api/runs/${runId}/logs${suffix}`);
}

export function getRunArtifacts(runId: string) {
  return request<Artifact[]>(`/api/runs/${runId}/artifacts`);
}

export function createRun(input: {
  flow_id: string;
  flow_version?: number;
  inputs: Record<string, unknown>;
  idempotency_key?: string;
}) {
  return request<RunResponse>('/api/runs', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function cancelRun(runId: string) {
  return request<RunResponse>(`/api/runs/${runId}/cancel`, { method: 'POST' });
}

export function retryRun(runId: string) {
  return request<RunResponse>(`/api/runs/${runId}/retry`, { method: 'POST' });
}

export function getProviders() {
  return request<Provider[]>('/api/providers');
}

export function checkProviderHealth(providerName: string) {
  return request<Provider>(`/api/providers/${providerName}/health-check`, {
    method: 'POST',
  });
}

export function getAuditLogs(params: {
  page?: number;
  pageSize?: number;
  action?: string;
  targetType?: string;
}) {
  const search = new URLSearchParams();
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('page_size', String(params.pageSize));
  if (params.action) search.set('action', params.action);
  if (params.targetType) search.set('target_type', params.targetType);
  return request<Page<AuditLog>>(`/api/audit-logs?${search.toString()}`);
}
