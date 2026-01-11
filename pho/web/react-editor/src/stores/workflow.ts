/**
 * Workflow store using Zustand
 * Manages workflow nodes, edges, and UI state
 */

import { create } from 'zustand';
import { applyNodeChanges, applyEdgeChanges, addEdge, Connection, Edge, Node, NodeChange, EdgeChange } from '@xyflow/react';
import type { WorkflowNode, WorkflowEdge, WorkflowNodeData, WorkflowEdgeData } from '@/types/workflow';

// ============================================================================
// Store State
// ============================================================================

interface WorkflowState {
  // Workflow data
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport: {
    x: number;
    y: number;
    zoom: number;
  };

  // Selection state
  selectedNodeId: string | null;
  selectedEdgeId: string | null;

  // Component library
  components: Map<string, ComponentInfo>;
  componentGroups: Map<string, string[]>;

  // UI state
  showMinimap: boolean;
  showGrid: boolean;
  isDarkMode: boolean;

  // Actions
  onNodesChange: (changes: NodeChange<WorkflowNodeData>[]) => void;
  onEdgesChange: (changes: EdgeChange<WorkflowEdgeData>[]) => void;
  onConnect: (connection: Connection) => void;
  setNodes: (nodes: WorkflowNode[]) => void;
  setEdges: (edges: WorkflowEdge[]) => void;
  addNode: (node: WorkflowNode) => void;
  removeNode: (nodeId: string) => void;
  updateNode: (nodeId: string, updates: Partial<WorkflowNode>) => void;
  updateNodeData: (nodeId: string, updates: Partial<WorkflowNodeData>) => void;
  removeEdge: (edgeId: string) => void;
  setSelectedNode: (nodeId: string | null) => void;
  setSelectedEdge: (edgeId: string | null) => void;
  setViewport: (viewport: { x: number; y: number; zoom: number }) => void;

  // Component actions
  setComponents: (components: ComponentInfo[]) => void;
  getComponent: (type: string) => ComponentInfo | undefined;

  // UI actions
  toggleMinimap: () => void;
  toggleGrid: () => void;
  toggleDarkMode: () => void;

  // Workflow actions
  clearWorkflow: () => void;
  loadWorkflow: (workflow: WorkflowData) => void;
  exportWorkflow: () => WorkflowData;
  validateWorkflow: () => ValidationResult;
}

// ============================================================================
// Types
// ============================================================================

interface ComponentInfo {
  type: string;
  label: string;
  group: string;
  description: string;
  icon: string;
  configSchema: Record<string, unknown>;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
}

interface WorkflowData {
  name: string;
  nodes: Array<{
    id: string;
    component_type: string;
    label?: string;
    config?: Record<string, unknown>;
    inputs?: Record<string, unknown>;
    position: { x: number; y: number };
  }>;
  edges: Array<{
    source: string;
    target: string;
    source_handle?: string;
    target_handle?: string;
  }>;
}

interface ValidationResult {
  isValid: boolean;
  errors: Array<{
    type: 'node' | 'edge' | 'workflow';
    id?: string;
    message: string;
  }>;
}

// ============================================================================
// Store Implementation
// ============================================================================

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  // Initial state
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
  selectedNodeId: null,
  selectedEdgeId: null,
  components: new Map(),
  componentGroups: new Map(),
  showMinimap: true,
  showGrid: true,
  isDarkMode: false,

  // React Flow handlers
  onNodesChange: (changes) => {
    set({
      nodes: applyNodeChanges(changes, get().nodes),
    });
  },

  onEdgesChange: (changes) => {
    set({
      edges: applyEdgeChanges(changes, get().edges),
    });
  },

  onConnect: (connection) => {
    set({
      edges: addEdge(
        {
          ...connection,
          type: 'smoothstep',
          animated: true,
          style: { stroke: 'var(--color-edge-default)', strokeWidth: 2 },
        },
        get().edges
      ),
    });
  },

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  // Node operations
  addNode: (node) => {
    set((state) => ({
      nodes: [...state.nodes, node],
    }));
  },

  removeNode: (nodeId) => {
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== nodeId),
      edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
    }));
  },

  updateNode: (nodeId, updates) => {
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)),
    }));
  },

  updateNodeData: (nodeId, updates) => {
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === nodeId
          ? {
              ...n,
              data: {
                ...n.data,
                ...updates,
              },
            }
          : n
      ),
    }));
  },

  removeEdge: (edgeId) => {
    set((state) => ({
      edges: state.edges.filter((e) => e.id !== edgeId),
      selectedEdgeId: state.selectedEdgeId === edgeId ? null : state.selectedEdgeId,
    }));
  },

  setSelectedNode: (nodeId) => set({ selectedNodeId: nodeId }),
  setSelectedEdge: (edgeId) => set({ selectedEdgeId: edgeId }),
  setViewport: (viewport) => set({ viewport }),

  // Component operations
  setComponents: (components) => {
    const componentMap = new Map(components.map((c) => [c.type, c]));
    const groupMap = new Map<string, string[]>();

    components.forEach((c) => {
      if (!groupMap.has(c.group)) {
        groupMap.set(c.group, []);
      }
      groupMap.get(c.group)!.push(c.type);
    });

    set({
      components: componentMap,
      componentGroups: groupMap,
    });
  },

  getComponent: (type) => {
    return get().components.get(type);
  },

  // UI actions
  toggleMinimap: () => set((state) => ({ showMinimap: !state.showMinimap })),
  toggleGrid: () => set((state) => ({ showGrid: !state.showGrid })),
  toggleDarkMode: () => set((state) => {
    const newMode = !state.isDarkMode;
    if (newMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    return { isDarkMode: newMode };
  }),

  // Workflow operations
  clearWorkflow: () => {
    set({
      nodes: [],
      edges: [],
      selectedNodeId: null,
      selectedEdgeId: null,
    });
  },

  loadWorkflow: (workflow) => {
    const nodes: WorkflowNode[] = workflow.nodes.map((n) => ({
      id: n.id,
      type: 'custom',
      position: n.position,
      data: {
        id: n.id,
        type: n.component_type,
        label: n.label || n.component_type,
        componentType: n.component_type,
        config: n.config,
        inputs: n.inputs,
        isValid: true,
      },
    }));

    const edges: WorkflowEdge[] = workflow.edges.map((e, i) => ({
      id: `edge-${i}`,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle,
      targetHandle: e.target_handle,
      type: 'smoothstep',
      animated: true,
    }));

    set({ nodes, edges });
  },

  exportWorkflow: () => {
    const { nodes, edges } = get();

    return {
      name: 'Untitled Workflow',
      nodes: nodes.map((n) => ({
        id: n.id,
        component_type: n.data.componentType,
        label: n.data.label,
        config: n.data.config,
        inputs: n.data.inputs,
        position: n.position,
      })),
      edges: edges.map((e) => ({
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle,
        target_handle: e.targetHandle,
      })),
    };
  },

  validateWorkflow: () => {
    const { nodes, edges } = get();
    const errors: ValidationResult['errors'] = [];

    // Check for empty workflow
    if (nodes.length === 0) {
      errors.push({
        type: 'workflow',
        message: 'Workflow must have at least one node',
      });
    }

    // Check for entry point
    const hasEntry = nodes.some((n) => n.data.componentType === 'entry');
    if (!hasEntry) {
      errors.push({
        type: 'workflow',
        message: 'Workflow must have an Entry node',
      });
    }

    // Check for disconnected nodes
    const connectedNodes = new Set<string>();
    edges.forEach((e) => {
      connectedNodes.add(e.source);
      connectedNodes.add(e.target);
    });

    nodes.forEach((n) => {
      if (!connectedNodes.has(n.id) && nodes.length > 1) {
        errors.push({
          type: 'node',
          id: n.id,
          message: `Node "${n.data.label}" is not connected`,
        });
      }
    });

    // Check for cycles
    const visited = new Set<string>();
    const recursionStack = new Set<string>();

    const hasCycle = (nodeId: string): boolean => {
      visited.add(nodeId);
      recursionStack.add(nodeId);

      const outgoingEdges = edges.filter((e) => e.source === nodeId);
      for (const edge of outgoingEdges) {
        if (!visited.has(edge.target)) {
          if (hasCycle(edge.target)) {
            return true;
          }
        } else if (recursionStack.has(edge.target)) {
          return true;
        }
      }

      recursionStack.delete(nodeId);
      return false;
    };

    for (const node of nodes) {
      if (!visited.has(node.id)) {
        if (hasCycle(node.id)) {
          errors.push({
            type: 'workflow',
            message: 'Workflow contains cycles',
          });
          break;
        }
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
    };
  },
}));

// ============================================================================
// Selectors
// ============================================================================

export const selectSelectedNode = (state: WorkflowState) => {
  if (!state.selectedNodeId) return null;
  return state.nodes.find((n) => n.id === state.selectedNodeId) || null;
};

export const selectSelectedEdge = (state: WorkflowState) => {
  if (!state.selectedEdgeId) return null;
  return state.edges.find((e) => e.id === state.selectedEdgeId) || null;
};

export const selectComponentGroups = (state: WorkflowState) => {
  return Array.from(state.componentGroups.entries()).map(([group, types]) => ({
    group,
    components: types.map((type) => state.components.get(type)!).filter(Boolean),
  }));
};
