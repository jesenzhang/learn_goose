/**
 * Custom React Flow node component for Pho workflows
 * Supports multiple node types with different styling
 */

import React, { memo } from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';
import { cn } from '@/lib/utils';
import type { WorkflowNodeData } from '@/types/workflow';

// ============================================================================
// Node Type Icons
// ============================================================================

const NodeIcons: Record<string, React.ReactNode> = {
  entry: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
    </svg>
  ),
  exit: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),
  llm: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
    </svg>
  ),
  code: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
    </svg>
  ),
  loop: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  selector: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
    </svg>
  ),
  api: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
    </svg>
  ),
  transform: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m0 0a8.001 8.001 0 0115.356 2M4.582 9H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  merge: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12M8 12h12M8 17h12M4 7h.01M4 12h.01M4 17h.01" />
    </svg>
  ),
  split: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 12h16M4 8h8M4 16h8" />
    </svg>
  ),
  validate: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  batch: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
    </svg>
  ),
  default: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  ),
};

// ============================================================================
// Node Type Styling
// ============================================================================

const getNodeStyles = (type: string) => {
  const styles: Record<string, string> = {
    entry: 'bg-node-entry border-green-500',
    exit: 'bg-node-exit border-red-500',
    llm: 'bg-node-llm border-blue-500',
    code: 'bg-node-code border-purple-500',
    loop: 'bg-node-control border-yellow-600',
    selector: 'bg-node-control border-yellow-600',
    batch: 'bg-node-control border-yellow-600',
    api: 'bg-node-api border-orange-500',
    transform: 'bg-node-data border-neutral-400',
    merge: 'bg-node-data border-neutral-400',
    split: 'bg-node-data border-neutral-400',
    validate: 'bg-node-data border-neutral-400',
  };
  return styles[type] || 'bg-node-data border-neutral-400';
};

// ============================================================================
// Custom Node Component
// ============================================================================

export const CustomNode = memo(({ data, selected }: NodeProps<WorkflowNodeData>) => {
  // Handle undefined data gracefully
  const nodeType = data?.type || 'default';
  const nodeLabel = data?.label || 'Node';
  const isValid = data?.isValid;
  const nodeStyles = getNodeStyles(nodeType);
  const icon = NodeIcons[nodeType] || NodeIcons.default;

  return (
    <div
      className={cn(
        'workflow-node min-w-[160px] max-w-[240px]',
        nodeStyles,
        selected && 'selected'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50">
        <span className="flex-shrink-0 text-text-muted">{icon}</span>
        <span className="text-sm font-medium text-text truncate">{nodeLabel}</span>
      </div>

      {/* Body */}
      <div className="px-3 py-2">
        <p className="text-xs text-muted-foreground truncate">
          {nodeType}
        </p>
      </div>

      {/* Status indicator */}
      {isValid === false && (
        <div className="absolute top-2 right-2">
          <div className="w-2 h-2 rounded-full bg-red-500" title="Has errors" />
        </div>
      )}

      {/* Input Handle (top) */}
      {nodeType !== 'entry' && (
        <Handle
          type="target"
          position={Position.Top}
          className="workflow-handle"
        />
      )}

      {/* Output Handle (bottom) */}
      {nodeType !== 'exit' && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="workflow-handle"
        />
      )}

      {/* Side Handles for branching nodes */}
      {(nodeType === 'selector' || nodeType === 'split') && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            className="workflow-handle"
          />
          <Handle
            type="source"
            position={Position.Left}
            id="false"
            className="workflow-handle"
          />
        </>
      )}
    </div>
  );
});

CustomNode.displayName = 'CustomNode';

// ============================================================================
// Node Type Registry for React Flow
// ============================================================================

export const nodeTypes = {
  custom: CustomNode,
};
