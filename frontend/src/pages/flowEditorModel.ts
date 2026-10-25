import type { FlowDefinition, StepDefinition, StepType } from '../api';

export const stepTypes: StepType[] = [
  'agent',
  'template',
  'condition',
  'parallel',
  'join',
  'analysis',
  'input',
];

export function emptyDefinition(): FlowDefinition {
  return {
    name: 'New Flow',
    description: '',
    inputs: [],
    execution: { failure_strategy: 'fail_fast' },
    steps: [
      {
        id: 'analyze',
        name: 'Analyze',
        type: 'agent',
        depends_on: [],
        config: {
          prompt: 'Analyze the provided input.',
          provider: 'mock',
          timeoutSeconds: 900,
          maxRetries: 0,
        },
      },
    ],
  };
}

export function nextStepId(steps: StepDefinition[]) {
  let index = steps.length + 1;
  while (steps.some((step) => step.id === `step-${index}`)) index += 1;
  return `step-${index}`;
}

export function defaultConfig(type: StepType): Record<string, unknown> {
  if (type === 'agent' || type === 'analysis') {
    return {
      prompt: '',
      ...(type === 'agent' ? { provider: 'mock' } : {}),
      timeoutSeconds: 900,
      maxRetries: 0,
    };
  }
  if (type === 'template') return { template: '' };
  if (type === 'condition') return { expression: 'inputs.mode == "deep"' };
  if (type === 'parallel') return { branches: [] };
  return {};
}

export function parseValue(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

export function stringifyValue(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}
