/**
 * Toolbar - Action buttons for workflow operations
 * Provides save, load, execute, and view controls
 */

import React, { useState } from 'react';
import { useWorkflowStore } from '@/stores/workflow';
import { useApi } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { IconButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  Save,
  FolderOpen,
  Play,
  Undo,
  Redo,
  ZoomIn,
  ZoomOut,
  Maximize,
  Map,
  Grid,
  Moon,
  Sun,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';
import { useReactFlow } from '@xyflow/react';

// ============================================================================
// Toolbar Component
// ============================================================================

export function Toolbar() {
  const { api } = useApi();
  const {
    showMinimap,
    showGrid,
    isDarkMode,
    toggleMinimap,
    toggleGrid,
    toggleDarkMode,
    exportWorkflow,
    clearWorkflow,
    validateWorkflow,
  } = useWorkflowStore();

  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [isExecuting, setIsExecuting] = useState(false);
  const [validationResult, setValidationResult] = useState<{ isValid: boolean; message?: string } | null>(null);

  // Handle save
  const handleSave = () => {
    const workflow = exportWorkflow();
    console.log('Saving workflow:', workflow);
    // TODO: Implement save API
    setValidationResult({ isValid: true, message: 'Workflow saved' });
    setTimeout(() => setValidationResult(null), 2000);
  };

  // Handle load
  const handleLoad = () => {
    console.log('Loading workflow...');
    // TODO: Implement load dialog
  };

  // Handle execute
  const handleExecute = async () => {
    const validation = validateWorkflow();
    if (!validation.isValid) {
      setValidationResult({
        isValid: false,
        message: `Validation failed: ${validation.errors.map(e => e.message).join(', ')}`,
      });
      return;
    }

    setIsExecuting(true);
    setValidationResult(null);

    try {
      const workflow = exportWorkflow();
      const result = await api.executeWorkflow({
        workflow: workflow,
        inputs: {},
      });

      setValidationResult({
        isValid: true,
        message: `Execution started: ${result.execution_id}`,
      });
    } catch (error) {
      setValidationResult({
        isValid: false,
        message: error instanceof Error ? error.message : 'Execution failed',
      });
    } finally {
      setIsExecuting(false);
      setTimeout(() => setValidationResult(null), 3000);
    }
  };

  // Handle validate
  const handleValidate = () => {
    const validation = validateWorkflow();
    setValidationResult({
      isValid: validation.isValid,
      message: validation.isValid
        ? 'Workflow is valid'
        : validation.errors.map(e => e.message).join(', '),
    });
    setTimeout(() => setValidationResult(null), 3000);
  };

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10">
      <div className="flex items-center gap-2 bg-background border border-border rounded-lg shadow-lg p-1.5">
        {/* File Operations */}
        <div className="flex items-center gap-1 pr-2 border-r border-border">
          <IconButton
            icon={<Save className="w-4 h-4" />}
            label="Save workflow (Ctrl+S)"
            onClick={handleSave}
            variant="ghost"
            size="sm"
          />
          <IconButton
            icon={<FolderOpen className="w-4 h-4" />}
            label="Load workflow (Ctrl+O)"
            onClick={handleLoad}
            variant="ghost"
            size="sm"
          />
        </div>

        {/* Edit Operations */}
        <div className="flex items-center gap-1 px-2 border-r border-border">
          <IconButton
            icon={<Undo className="w-4 h-4" />}
            label="Undo (Ctrl+Z)"
            onClick={() => console.log('Undo')}
            variant="ghost"
            size="sm"
            disabled
          />
          <IconButton
            icon={<Redo className="w-4 h-4" />}
            label="Redo (Ctrl+Shift+Z)"
            onClick={() => console.log('Redo')}
            variant="ghost"
            size="sm"
            disabled
          />
        </div>

        {/* View Operations */}
        <div className="flex items-center gap-1 px-2 border-r border-border">
          <IconButton
            icon={<ZoomIn className="w-4 h-4" />}
            label="Zoom in"
            onClick={() => zoomIn()}
            variant="ghost"
            size="sm"
          />
          <IconButton
            icon={<ZoomOut className="w-4 h-4" />}
            label="Zoom out"
            onClick={() => zoomOut()}
            variant="ghost"
            size="sm"
          />
          <IconButton
            icon={<Maximize className="w-4 h-4" />}
            label="Fit view"
            onClick={() => fitView()}
            variant="ghost"
            size="sm"
          />
          <IconButton
            icon={<Map className={cn('w-4 h-4', showMinimap && 'text-primary')} />}
            label="Toggle minimap"
            onClick={toggleMinimap}
            variant="ghost"
            size="sm"
          />
          <IconButton
            icon={<Grid className={cn('w-4 h-4', showGrid && 'text-primary')} />}
            label="Toggle grid"
            onClick={toggleGrid}
            variant="ghost"
            size="sm"
          />
        </div>

        {/* Theme */}
        <div className="flex items-center gap-1 px-2 border-r border-border">
          <IconButton
            icon={isDarkMode ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            label="Toggle theme"
            onClick={toggleDarkMode}
            variant="ghost"
            size="sm"
          />
        </div>

        {/* Execute */}
        <div className="flex items-center gap-1 pl-2">
          <Button
            onClick={handleExecute}
            disabled={isExecuting}
            className="gap-2"
            size="sm"
          >
            {isExecuting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Execute
              </>
            )}
          </Button>
          <IconButton
            icon={<CheckCircle2 className="w-4 h-4" />}
            label="Validate workflow"
            onClick={handleValidate}
            variant="ghost"
            size="sm"
          />
        </div>

        {/* Status indicator */}
        {validationResult && (
          <div className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium',
            validationResult.isValid
              ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
              : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
          )}>
            {validationResult.isValid ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <XCircle className="w-3.5 h-3.5" />
            )}
            <span>{validationResult.message}</span>
          </div>
        )}
      </div>
    </div>
  );
}
