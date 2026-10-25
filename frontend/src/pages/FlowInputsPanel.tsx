import { Plus, Trash2 } from 'lucide-react';

import type { FlowDefinition, FlowInputDefinition } from '../api';
import { parseValue, stringifyValue } from './flowEditorModel';

type Props = {
  definition: FlowDefinition;
  onUpdateDefinition: (updater: (current: FlowDefinition) => FlowDefinition) => void;
};

export function FlowInputsPanel({ definition, onUpdateDefinition }: Props) {
  const updateInput = (
    index: number,
    updater: (input: FlowInputDefinition) => FlowInputDefinition,
  ) => {
    onUpdateDefinition((current) => ({
      ...current,
      inputs: current.inputs.map((input, inputIndex) =>
        inputIndex === index ? updater(input) : input,
      ),
    }));
  };

  return (
    <div className="inputs-editor">
      <button
        className="ghost-button"
        onClick={() =>
          onUpdateDefinition((current) => ({
            ...current,
            inputs: [
              ...current.inputs,
              { name: `input_${current.inputs.length + 1}`, type: 'string', required: true },
            ],
          }))
        }
        type="button"
      >
        <Plus size={15} />
        <span>Add input</span>
      </button>

      {definition.inputs.length === 0 && <p className="muted">No run inputs.</p>}

      {definition.inputs.map((input, index) => (
        <div className="input-definition" key={`${input.name}-${index}`}>
          <input
            aria-label="Input name"
            value={input.name}
            onChange={(event) =>
              updateInput(index, (item) => ({ ...item, name: event.target.value }))
            }
          />
          <select
            aria-label="Input type"
            value={input.type}
            onChange={(event) =>
              updateInput(index, (item) => ({
                ...item,
                type: event.target.value as FlowInputDefinition['type'],
              }))
            }
          >
            <option value="string">string</option>
            <option value="number">number</option>
            <option value="boolean">boolean</option>
            <option value="json">json</option>
          </select>
          <input
            aria-label="Default value"
            placeholder="Default"
            value={stringifyValue(input.default)}
            onChange={(event) =>
              updateInput(index, (item) => ({ ...item, default: parseValue(event.target.value) }))
            }
          />
          <button
            aria-label="Remove input"
            className="icon-button"
            onClick={() =>
              onUpdateDefinition((current) => ({
                ...current,
                inputs: current.inputs.filter((_, itemIndex) => itemIndex !== index),
              }))
            }
            type="button"
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
