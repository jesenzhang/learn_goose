/**
 * Workflow type definitions for Pho workflow editor
 * Aligned with backend API and workflow protocol
 */

import { Node, Edge } from '@xyflow/react';

// ============================================================================
// Component Types
// ============================================================================

export interface ComponentDefinition {
  type: string;
  label: string;
  group: string;
  description: string;
  icon: string;
  config_schema: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  ports: ComponentPorts;
}

export interface ComponentPorts {
  inputs: PortDefinition[];
  outputs: PortDefinition[];
}

export interface PortDefinition {
  id: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'any';
  required?: boolean;
}

export interface ComponentListItem {
  type: string;
  label: string;
  group: string;
  description: string;
  icon: string;
}

// ============================================================================
// Workflow Types
// ============================================================================

export interface WorkflowDefinition {
  name: string;
  description?: string;
  nodes: WorkflowNodeConfig[];
  edges: WorkflowEdgeConfig[];
  entry_point?: string;
}

export interface WorkflowNodeConfig {
  id: string;
  component_type: string;
  label?: string;
  config?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
}

export interface WorkflowEdgeConfig {
  source: string;
  target: string;
  source_handle?: string;
  target_handle?: string;
  condition?: string;
}

// ============================================================================
// React Flow Extensions
// ============================================================================

export interface WorkflowNodeData {
  id: string;
  type: string;
  label: string;
  componentType: string;
  config?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
  isValid?: boolean;
  errors?: string[];
}

export type WorkflowNode = Node<WorkflowNodeData>;

export interface WorkflowEdgeData {
  condition?: string;
  isValid?: boolean;
}

export type WorkflowEdge = Edge<WorkflowEdgeData>;

// ============================================================================
// API Response Types
// ============================================================================

export interface ComponentListResponse {
  components: ComponentListItem[];
}

export interface ComponentDetailResponse extends ComponentDefinition {}

export interface ComponentGroupsResponse {
  [group: string]: ComponentListItem[];
}

export interface WorkflowExecuteRequest {
  workflow_id?: string;
  workflow?: WorkflowDefinition;
  inputs?: Record<string, unknown>;
}

export interface WorkflowExecuteResponse {
  execution_id: string;
  status: 'running' | 'completed' | 'failed';
  result?: Record<string, unknown>;
  error?: string;
}

// ============================================================================
// UI State Types
// ============================================================================

export interface WorkflowEditorState {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  viewport: {
    x: number;
    y: number;
    zoom: number;
  };
}

export interface ComponentPaletteState {
  searchTerm: string;
  selectedGroup: string | null;
  expandedGroups: Set<string>;
}

export interface NodeEditorState {
  nodeId: string | null;
  tab: 'config' | 'inputs' | 'outputs';
  hasChanges: boolean;
}

// ============================================================================
// Example Workflow Types
// ============================================================================

export interface ExampleWorkflow {
  id: string;
  name: string;
  description: string;
  workflow: WorkflowDefinition;
}

// ============================================================================
// Validation Types
// ============================================================================

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
}

export interface ValidationError {
  type: 'node' | 'edge' | 'workflow';
  id?: string;
  message: string;
  severity: 'error' | 'warning';
}
