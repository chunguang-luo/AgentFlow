import { Trash2 } from 'lucide-react';

import type { FlowDefinition, StepDefinition, StepType } from '../api';
import { defaultConfig, stringifyValue } from './flowEditorModel';

type Props = {
  definition: FlowDefinition;
  selectedStep: StepDefinition | null;
  stepTypes: StepType[];
  onUpdateStep: (stepId: string, updater: (step: StepDefinition) => StepDefinition) => void;
  onRemove: (stepId: string) => void;
};

export function FlowInspectorPanel({
  definition,
  selectedStep,
  stepTypes,
  onUpdateStep,
  onRemove,
}: Props) {
  if (!selectedStep) {
    return <p className="muted">Select a step to configure it.</p>;
  }

  const setConfig = (key: string, value: unknown) => {
    onUpdateStep(selectedStep.id, (step) => ({
      ...step,
      config: { ...step.config, [key]: value },
    }));
  };

  const setDependencies = (dependency: string, checked: boolean) => {
    onUpdateStep(selectedStep.id, (step) => {
      const dependsOn = checked
        ? [...step.depends_on, dependency]
        : step.depends_on.filter((item) => item !== dependency);
      return {
        ...step,
        depends_on: dependsOn,
        config: step.type === 'parallel' ? { ...step.config, branches: dependsOn } : step.config,
      };
    });
  };

  return (
    <div className="form-grid">
      <label>
        <span>Step ID</span>
        <input readOnly value={selectedStep.id} />
      </label>

      <label>
        <span>Name</span>
        <input
          value={selectedStep.name}
          onChange={(event) =>
            onUpdateStep(selectedStep.id, (step) => ({ ...step, name: event.target.value }))
          }
        />
      </label>

      <label>
        <span>Type</span>
        <select
          value={selectedStep.type}
          onChange={(event) => {
            const type = event.target.value as StepType;
            onUpdateStep(selectedStep.id, (step) => ({
              ...step,
              type,
              config: defaultConfig(type),
            }));
          }}
        >
          {stepTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>

      <fieldset>
        <legend>Dependencies</legend>
        {definition.steps
          .filter((step) => step.id !== selectedStep.id)
          .map((step) => (
            <label key={step.id} className="checkbox">
              <input
                checked={selectedStep.depends_on.includes(step.id)}
                onChange={(event) => setDependencies(step.id, event.target.checked)}
                type="checkbox"
              />
              <span>{step.name}</span>
            </label>
          ))}
      </fieldset>

      {(selectedStep.type === 'agent' || selectedStep.type === 'analysis') && (
        <>
          {selectedStep.type === 'agent' && (
            <label>
              <span>Provider</span>
              <select
                value={String(selectedStep.config.provider ?? 'mock')}
                onChange={(event) => setConfig('provider', event.target.value)}
              >
                <option value="mock">mock</option>
                <option value="claude-cli">claude-cli</option>
                <option value="codex-cli">codex-cli</option>
              </select>
            </label>
          )}

          <label>
            <span>Prompt</span>
            <textarea
              rows={7}
              value={String(selectedStep.config.prompt ?? '')}
              onChange={(event) => setConfig('prompt', event.target.value)}
            />
          </label>

          {selectedStep.type === 'agent' && (
            <label>
              <span>Mock output</span>
              <input
                value={stringifyValue(
                  (selectedStep.config.mock as Record<string, unknown> | undefined)?.output ?? '',
                )}
                onChange={(event) =>
                  setConfig('mock', {
                    ...((selectedStep.config.mock as object) ?? {}),
                    output: event.target.value,
                  })
                }
              />
            </label>
          )}

          <div className="two-columns">
            <label>
              <span>Timeout</span>
              <input
                type="number"
                value={Number(selectedStep.config.timeoutSeconds ?? 900)}
                onChange={(event) => setConfig('timeoutSeconds', Number(event.target.value))}
              />
            </label>
            <label>
              <span>Retries</span>
              <input
                type="number"
                value={Number(selectedStep.config.maxRetries ?? 0)}
                onChange={(event) => setConfig('maxRetries', Number(event.target.value))}
              />
            </label>
          </div>
        </>
      )}

      {selectedStep.type === 'template' && (
        <label>
          <span>Template</span>
          <textarea
            rows={8}
            value={String(selectedStep.config.template ?? '')}
            onChange={(event) => setConfig('template', event.target.value)}
          />
        </label>
      )}

      {selectedStep.type === 'condition' && (
        <label>
          <span>Expression</span>
          <textarea
            rows={4}
            value={String(selectedStep.config.expression ?? '')}
            onChange={(event) => setConfig('expression', event.target.value)}
          />
        </label>
      )}

      <button className="danger-button" onClick={() => onRemove(selectedStep.id)} type="button">
        <Trash2 size={15} />
        <span>Delete step</span>
      </button>
    </div>
  );
}
