/**
 * Node Editor - Properties panel for editing selected node
 * Allows editing node configuration, inputs, and outputs
 * Uses DynamicForm with x-ui-component support
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useWorkflowStore, selectSelectedNode } from '@/stores/workflow';
import { useApi } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Trash2, Settings, ArrowRight, ArrowLeft } from 'lucide-react';
import type { ComponentDetailResponse } from '@/types/workflow';
import { DynamicForm } from './DynamicForm';
import { TypeBuilder, ParameterDefinition } from './TypeBuilder';

// ============================================================================
// Types
// ============================================================================

interface SchemaSection {
  title: string;
  description?: string;
  type: string;
  properties?: Record<string, unknown>;
  required?: string[];
  // Check for x-ui-component extensions
  ['x-ui-component']?: string;
  ['x-ui-props']?: Record<string, unknown>;
}

// ============================================================================
// Section Component
// ============================================================================

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function Section({ title, icon, children, defaultOpen = true }: SectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-3 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="flex-shrink-0 w-4 h-4 text-primary">{icon}</span>
          <span className="text-sm font-medium text-text">{title}</span>
        </div>
        <svg
          className={cn(
            'w-4 h-4 text-muted-foreground transition-transform',
            isOpen ? 'rotate-90' : ''
          )}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>
      {isOpen && <div className="p-3 pt-0">{children}</div>}
    </Card>
  );
}

// ============================================================================
// Node Editor Component
// ============================================================================

export function NodeEditor() {
  const { api } = useApi();
  const selectedNode = useWorkflowStore(selectSelectedNode);
  const updateNodeData = useWorkflowStore((state) => state.updateNodeData);
  const removeNode = useWorkflowStore((state) => state.removeNode);
  const setSelectedNode = useWorkflowStore((state) => state.setSelectedNode);

  const [componentDetail, setComponentDetail] = useState<ComponentDetailResponse | null>(null);
  const [localConfig, setLocalConfig] = useState<Record<string, unknown>>({});
  const [localInputs, setLocalInputs] = useState<Record<string, unknown>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load component detail when node is selected
  useEffect(() => {
    if (selectedNode) {
      setLocalConfig(selectedNode.data.config || {});
      setLocalInputs(selectedNode.data.inputs || {});
      setHasChanges(false);
      setIsLoading(true);
      setError(null);

      // Use componentType (original type) not the lowercase type
      const componentType = selectedNode.data.componentType || selectedNode.data.type;

      api.getComponentDetail(componentType)
        .then((detail) => {
          setComponentDetail(detail);
          setIsLoading(false);
        })
        .catch((err) => {
          console.error('Failed to load component detail:', err);
          setError(`Failed to load component: ${componentType}`);
          setIsLoading(false);
        });
    } else {
      setComponentDetail(null);
      setLocalConfig({});
      setLocalInputs({});
      setHasChanges(false);
      setIsLoading(false);
      setError(null);
    }
  }, [selectedNode, api]);

  // Handle config change
  const handleConfigChange = useCallback((value: Record<string, unknown>) => {
    setLocalConfig(value);
    setHasChanges(true);
  }, []);

  // Handle input change
  const handleInputChange = useCallback((value: Record<string, unknown>) => {
    setLocalInputs(value);
    setHasChanges(true);
  }, []);

  // Save changes
  const handleSave = useCallback(() => {
    if (selectedNode) {
      updateNodeData(selectedNode.id, {
        config: localConfig,
        inputs: localInputs,
      });
      setHasChanges(false);
    }
  }, [selectedNode, localConfig, localInputs, updateNodeData]);

  // Delete node
  const handleDelete = useCallback(() => {
    if (selectedNode) {
      removeNode(selectedNode.id);
      setSelectedNode(null);
    }
  }, [selectedNode, removeNode, setSelectedNode]);

  // Check if a schema has TypeBuilder component (for Start node's variables)
  const isTypeBuilderField = (key: string, schema: unknown): boolean => {
    const field = schema as Record<string, unknown>;
    const extra = field.json_schema_extra as Record<string, unknown> | undefined;
    return extra?.['x-ui-component'] === 'TypeBuilder';
  };

  // No node selected
  if (!selectedNode) {
    return (
      <div className="flex flex-col h-full bg-background border-l border-border">
        <div className="p-4 border-b border-border">
          <h2 className="text-sm font-semibold text-text">Properties</h2>
        </div>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center">
            <p className="text-sm text-muted-foreground mb-1">No node selected</p>
            <p className="text-xs text-muted-foreground">
              Click on a node to edit its properties
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Build config schema wrapper
  const configSchema = componentDetail?.config_schema
    ? {
        type: 'object',
        properties: componentDetail.config_schema,
        required: [],
      }
    : undefined;

  // Build input schema wrapper
  const inputSchema = componentDetail?.input_schema
    ? {
        type: 'object',
        properties: componentDetail.input_schema,
        required: [],
      }
    : undefined;

  // Check if config has TypeBuilder (variables field)
  const hasTypeBuilder = configSchema?.properties?.variables
    ? isTypeBuilderField('variables', configSchema.properties.variables)
    : false;

  return (
    <div className="flex flex-col h-full bg-background border-l border-border">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-text">Properties</h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleDelete}
            className="h-7 w-7 text-red-500 hover:text-red-600 hover:bg-red-50"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
        <Input
          value={selectedNode.data.label}
          onChange={(e) => updateNodeData(selectedNode.id, { label: e.target.value })}
          className="h-8 text-sm"
        />
        <p className="text-xs text-muted-foreground mt-1">
          {componentDetail?.description || selectedNode.data.label}
        </p>
      </div>

      {/* Content - Vertical stacked sections */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-3">
        {isLoading && (
          <div className="text-center py-8">
            <p className="text-sm text-muted-foreground">Loading component details...</p>
          </div>
        )}

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-3">
              <p className="text-sm text-red-600">{error}</p>
            </CardContent>
          </Card>
        )}

        {componentDetail && (
          <>
            {/* Configuration Section */}
            <Section
              title="Configuration"
              icon={<Settings className="w-4 h-4" />}
              defaultOpen={true}
            >
              {Object.keys(componentDetail.config_schema || {}).length === 0 ? (
                <p className="text-xs text-muted-foreground">No configuration options</p>
              ) : hasTypeBuilder ? (
                // Special handling for TypeBuilder (Start node variables)
                <div className="space-y-2">
                  <label className="text-xs font-medium text-text">
                    {(componentDetail.config_schema?.variables as Record<string, unknown>)?.title || 'Variables'}
                  </label>
                  <p className="text-xs text-muted-foreground">
                    {(componentDetail.config_schema?.variables as Record<string, unknown>)?.description || 'Define workflow input parameters'}
                  </p>
                  <TypeBuilder
                    value={(localConfig.variables as ParameterDefinition[]) || []}
                    onChange={(newValue) => handleConfigChange({ ...localConfig, variables: newValue })}
                  />
                </div>
              ) : (
                // Use DynamicForm for other configs
                <DynamicForm
                  schema={configSchema!}
                  value={localConfig}
                  onChange={handleConfigChange}
                  nodeId={selectedNode.id}
                />
              )}
            </Section>

            {/* Inputs Section */}
            {inputSchema && Object.keys(componentDetail.input_schema || {}).length > 0 && (
              <Section
                title="Inputs"
                icon={<ArrowRight className="w-4 h-4" />}
                defaultOpen={true}
              >
                <DynamicForm
                  schema={inputSchema}
                  value={localInputs}
                  onChange={handleInputChange}
                  nodeId={selectedNode.id}
                />
              </Section>
            )}

            {/* Outputs Section */}
            <Section
              title="Outputs"
              icon={<ArrowLeft className="w-4 h-4" />}
              defaultOpen={false}
            >
              <Card>
                <CardContent className="p-3">
                  <pre className="text-xs text-text overflow-x-auto">
                    {JSON.stringify(componentDetail.output_schema || {}, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            </Section>
          </>
        )}
      </div>

      {/* Footer */}
      {hasChanges && (
        <div className="p-4 border-t border-border">
          <Button onClick={handleSave} className="w-full" size="sm">
            Apply Changes
          </Button>
        </div>
      )}
    </div>
  );
}
