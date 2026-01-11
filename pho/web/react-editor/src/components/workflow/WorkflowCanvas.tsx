/**
 * Workflow Canvas - Main React Flow editor canvas
 * Provides drag-and-drop workflow editing with React Flow
 */

import React, { useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useWorkflowStore } from '@/stores/workflow';
import { nodeTypes } from './nodes/CustomNode';
import { cn } from '@/lib/utils';

// ============================================================================
// MiniMap Node
// ============================================================================

function MiniMapNode({ data }: { data?: { label?: string; type?: string } }) {
  const getNodeColor = (type: string) => {
    const colors: Record<string, string> = {
      entry: '#a3d795',
      exit: '#ff6b6b',
      llm: '#7cacff',
      code: '#c084fc',
      loop: '#ffd966',
      selector: '#ffd966',
      api: '#ff4f00',
      transform: '#e3e6ea',
      merge: '#e3e6ea',
      split: '#e3e6ea',
      validate: '#e3e6ea',
    };
    return colors[type] || '#e3e6ea';
  };

  // Handle undefined data
  const type = data?.type || 'default';
  const label = data?.label || 'Node';

  return (
    <div
      style={{
        background: getNodeColor(type),
        padding: '4px 8px',
        borderRadius: '4px',
        fontSize: '10px',
        color: '#2c2e33',
      }}
    >
      {label}
    </div>
  );
}

// ============================================================================
// Workflow Canvas Component
// ============================================================================

export function WorkflowCanvas() {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    viewport,
    setViewport,
    showMinimap,
    showGrid,
    selectedNodeId,
    selectedEdgeId,
    setSelectedNode,
    setSelectedEdge,
  } = useWorkflowStore();

  const { fitView, zoomIn, zoomOut } = useReactFlow();

  // Handle node selection
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: { id: string }) => {
      setSelectedNode(node.id);
    },
    [setSelectedNode]
  );

  // Handle edge selection
  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: { id: string }) => {
      setSelectedEdge(edge.id);
    },
    [setSelectedEdge]
  );

  // Handle pane click (deselect)
  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, [setSelectedNode, setSelectedEdge]);

  // Handle delete key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeId) {
        useWorkflowStore.getState().removeNode(selectedNodeId);
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedEdgeId) {
        useWorkflowStore.getState().removeEdge(selectedEdgeId);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedNodeId, selectedEdgeId]);

  // Fit view on mount
  useEffect(() => {
    if (nodes.length > 0) {
      setTimeout(() => fitView(), 100);
    }
  }, [nodes.length, fitView]);

  return (
    <div className="workflow-canvas relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={2}
        defaultViewport={viewport}
        onViewportChange={setViewport}
        className="workflow-canvas"
        deleteKeyCode="Delete"
      >
        {showGrid && (
          <Background
            variant={BackgroundVariant.Dots}
            gap={16}
            size={1}
            color="var(--color-neutral-300)"
          />
        )}

        <Controls
          className={cn(
            'flex flex-col gap-1 p-2 bg-background border border-border rounded-lg shadow-lg',
            '[&_.react-flow__controls-button]:w-7 [&_.react-flow__controls-button]:h-7 [&_.react-flow__controls-button]:border-border [&_.react-flow__controls-button]:bg-background [&_.react-flow__controls-button]:hover:bg-muted [&_.react-flow__controls-button]:text-text',
            '[&_.react-flow__controls-button]:transition-colors'
          )}
        />

        {showMinimap && (
          <MiniMap
            nodeComponent={MiniMapNode}
            className="bg-background border border-border rounded-lg shadow-lg"
            maskColor="rgba(0, 0, 0, 0.05)"
            pannable
            zoomable
          />
        )}
      </ReactFlow>
    </div>
  );
}
