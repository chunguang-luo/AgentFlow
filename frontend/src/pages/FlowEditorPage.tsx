import { ArrowLeft, CheckCircle2, Download, Play, Plus, Save, Send, Upload } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  createFlow,
  createRun,
  exportFlow,
  getFlow,
  getFlowVersions,
  publishFlow,
  updateFlow,
  validateFlow,
  type FlowDefinition,
  type FlowVersion,
  type StepDefinition,
  type StepType,
} from '../api';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';
import { FlowInputsPanel } from './FlowInputsPanel';
import { FlowInspectorPanel } from './FlowInspectorPanel';
import { FlowVersionsPanel } from './FlowVersionsPanel';
import { defaultConfig, emptyDefinition, nextStepId, stepTypes } from './flowEditorModel';

export function FlowEditorPage() {
  const routeFlowId = useParams().flowId;
  const isNew = !routeFlowId;
  const flowId = routeFlowId ?? null;
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);

  const [definition, setDefinition] = useState<FlowDefinition>(emptyDefinition);
  const [flowStatus, setFlowStatus] = useState('draft');
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const [selectedStepId, setSelectedStepId] = useState('analyze');
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [loading, setLoading] = useState(!isNew);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<FlowVersion[] | null>(null);
  const [panel, setPanel] = useState<'inspector' | 'inputs' | 'versions'>(
    searchParams.get('panel') === 'versions' ? 'versions' : 'inspector',
  );

  useEffect(() => {
    if (!flowId) return;
    let active = true;
    setLoading(true);
    getFlow(flowId)
      .then((flow) => {
        if (!active) return;
        const loaded = flow.draft_definition ?? emptyDefinition();
        setDefinition(loaded);
        setFlowStatus(flow.status);
        setCurrentVersion(flow.current_version);
        setSelectedStepId(loaded.steps[0]?.id ?? '');
      })
      .catch((exc: unknown) => {
        if (active) setError(exc instanceof Error ? exc.message : 'Failed to load flow');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [flowId]);

  useEffect(() => {
    if (panel !== 'versions' || !flowId || versions) return;
    getFlowVersions(flowId)
      .then(setVersions)
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : 'Failed to load versions');
      });
  }, [flowId, panel, versions]);

  const selectedStep = definition.steps.find((step) => step.id === selectedStepId) ?? null;

  const nodes = useMemo<Node[]>(
    () =>
      definition.steps.map((step, index) => ({
        id: step.id,
        position: positions[step.id] ?? {
          x: (index % 3) * 240,
          y: Math.floor(index / 3) * 170,
        },
        data: {
          label: (
            <div className="flow-node">
              <strong>{step.name}</strong>
              <span>{step.type}</span>
            </div>
          ),
        },
      })),
    [definition.steps, positions],
  );

  const edges = useMemo<Edge[]>(
    () =>
      definition.steps.flatMap((step) =>
        step.depends_on.map((source) => ({
          id: `${source}-${step.id}`,
          source,
          target: step.id,
          animated: true,
        })),
      ),
    [definition.steps],
  );

  const updateDefinition = useCallback((updater: (current: FlowDefinition) => FlowDefinition) => {
    setDefinition(updater);
    setMessage(null);
    setError(null);
  }, []);

  const updateStep = useCallback(
    (stepId: string, updater: (step: StepDefinition) => StepDefinition) => {
      updateDefinition((current) => ({
        ...current,
        steps: current.steps.map((step) => (step.id === stepId ? updater(step) : step)),
      }));
    },
    [updateDefinition],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target || connection.source === connection.target)
        return;
      updateDefinition((current) => ({
        ...current,
        steps: current.steps.map((step) =>
          step.id === connection.target && !step.depends_on.includes(connection.source)
            ? { ...step, depends_on: [...step.depends_on, connection.source] }
            : step,
        ),
      }));
    },
    [updateDefinition],
  );

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    const dragStop = changes.find((change) => change.type === 'position' && !change.dragging);
    if (dragStop?.type !== 'position') return;
    const position = dragStop.position;
    if (!position) return;
    setPositions((current) => ({
      ...current,
      [dragStop.id]: { x: position.x, y: position.y },
    }));
  }, []);

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      const removed = new Set(deleted.map((edge) => `${edge.source}-${edge.target}`));
      updateDefinition((current) => ({
        ...current,
        steps: current.steps.map((step) => ({
          ...step,
          depends_on: step.depends_on.filter(
            (dependency) => !removed.has(`${dependency}-${step.id}`),
          ),
        })),
      }));
    },
    [updateDefinition],
  );

  const addStep = (type: StepType) => {
    const id = nextStepId(definition.steps);
    updateDefinition((current) => ({
      ...current,
      steps: [
        ...current.steps,
        {
          id,
          name: type.charAt(0).toUpperCase() + type.slice(1),
          type,
          depends_on: [],
          config: defaultConfig(type),
        },
      ],
    }));
    setSelectedStepId(id);
    setPanel('inspector');
  };

  const removeStep = (stepId: string) => {
    const nextSelected = definition.steps.find((step) => step.id !== stepId)?.id ?? '';
    updateDefinition((current) => ({
      ...current,
      steps: current.steps
        .filter((step) => step.id !== stepId)
        .map((step) => ({ ...step, depends_on: step.depends_on.filter((id) => id !== stepId) })),
    }));
    setSelectedStepId(nextSelected);
  };

  const validate = async () => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await validateFlow(definition);
      setMessage('Flow definition is valid.');
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Validation failed');
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      if (!flowId) {
        const created = await createFlow(definition);
        navigate(`/flows/${created.id}/edit`, { replace: true });
        return;
      }
      const result = await updateFlow(flowId, definition);
      setFlowStatus(result.status);
      setMessage('Draft saved.');
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!flowId) {
      setError('Save the flow before publishing.');
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await updateFlow(flowId, definition);
      const version = await publishFlow(flowId);
      setCurrentVersion(version.version);
      setFlowStatus('published');
      setVersions(null);
      setMessage(`Published version ${version.version}.`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Publish failed');
    } finally {
      setBusy(false);
    }
  };

  const tryRun = async () => {
    if (!flowId || !currentVersion) {
      setError('Publish the flow before running it.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const inputs: Record<string, unknown> = {};
      definition.inputs.forEach((input) => {
        if (input.default !== undefined && input.default !== null) {
          inputs[input.name] = input.default;
        }
      });
      const run = await createRun({ flow_id: flowId, inputs });
      navigate(`/runs/${run.id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Run failed');
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setBusy(true);
    try {
      const data = flowId ? await exportFlow(flowId, undefined, true) : definition;
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${definition.name.toLowerCase().replace(/\s+/g, '-')}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Export failed');
    } finally {
      setBusy(false);
    }
  };

  const importFile = async (file: File) => {
    try {
      const imported = JSON.parse(await file.text()) as FlowDefinition;
      setDefinition(imported);
      setSelectedStepId(imported.steps[0]?.id ?? '');
      setMessage('Definition imported.');
    } catch {
      setError('Import failed: invalid JSON');
    }
  };

  return (
    <div className="page flow-editor-page">
      <div className="breadcrumb">
        <Link className="ghost-button" to="/flows">
          <ArrowLeft size={16} />
          <span>Flows</span>
        </Link>
        <StatusBadge status={flowStatus} />
        <span className="muted">Version {currentVersion ?? '-'}</span>
      </div>

      <PageHeader
        title={isNew ? 'New Flow' : definition.name}
        actions={
          <>
            <button type="button" className="ghost-button" onClick={validate} disabled={busy}>
              <CheckCircle2 size={16} />
              <span>Validate</span>
            </button>
            <button type="button" className="ghost-button" onClick={save} disabled={busy}>
              <Save size={16} />
              <span>Save</span>
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={publish}
              disabled={busy || isNew}
            >
              <Send size={16} />
              <span>Publish</span>
            </button>
            <button type="button" className="ghost-button" onClick={tryRun} disabled={busy}>
              <Play size={16} />
              <span>Try run</span>
            </button>
          </>
        }
      />

      {message && <div className="page-success">{message}</div>}
      {error && <div className="page-error">{error}</div>}

      <div className="editor-layout">
        <aside className="editor-side">
          <label>
            <span>Flow name</span>
            <input
              value={definition.name}
              onChange={(event) =>
                updateDefinition((current) => ({ ...current, name: event.target.value }))
              }
            />
          </label>
          <label>
            <span>Description</span>
            <textarea
              rows={4}
              value={definition.description ?? ''}
              onChange={(event) =>
                updateDefinition((current) => ({ ...current, description: event.target.value }))
              }
            />
          </label>

          <div className="side-section">
            <strong>Add step</strong>
            <div className="step-buttons">
              {stepTypes.map((type) => (
                <button key={type} type="button" onClick={() => addStep(type)}>
                  <Plus size={13} />
                  <span>{type}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="side-section">
            <strong>Definition</strong>
            <button type="button" className="ghost-button" onClick={download} disabled={busy}>
              <Download size={15} />
              <span>Export</span>
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={15} />
              <span>Import</span>
            </button>
            <input
              ref={fileInput}
              hidden
              type="file"
              accept="application/json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importFile(file);
                event.target.value = '';
              }}
            />
          </div>
        </aside>

        <section className="canvas-panel">
          {loading ? (
            <div className="canvas-loading">Loading flow</div>
          ) : (
            <ReactFlow
              edges={edges}
              fitView
              minZoom={0.35}
              nodes={nodes}
              onConnect={onConnect}
              onEdgesDelete={onEdgesDelete}
              onNodeClick={(_, node) => {
                setSelectedStepId(node.id);
                setPanel('inspector');
              }}
              onNodesChange={onNodesChange}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} />
              <Controls showInteractive={false} />
              <MiniMap />
            </ReactFlow>
          )}
        </section>

        <aside className="inspector">
          <div className="segmented">
            {(['inspector', 'inputs', 'versions'] as const).map((item) => (
              <button
                key={item}
                type="button"
                className={panel === item ? 'active' : ''}
                onClick={() => {
                  setPanel(item);
                  setSearchParams(item === 'versions' ? { panel: item } : {});
                }}
              >
                {item}
              </button>
            ))}
          </div>

          {panel === 'inspector' && (
            <FlowInspectorPanel
              definition={definition}
              selectedStep={selectedStep}
              stepTypes={stepTypes}
              onRemove={removeStep}
              onUpdateStep={updateStep}
            />
          )}
          {panel === 'inputs' && (
            <FlowInputsPanel definition={definition} onUpdateDefinition={updateDefinition} />
          )}
          {panel === 'versions' && <FlowVersionsPanel flowId={flowId} versions={versions} />}
        </aside>
      </div>
    </div>
  );
}
