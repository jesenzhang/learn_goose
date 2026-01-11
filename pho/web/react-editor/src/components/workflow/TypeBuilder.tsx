/**
 * TypeBuilder Component - Dynamic nested parameter configuration editor
 *
 * Similar to Coze's parameter configuration table.
 * Supports recursive type definitions for complex nested structures.
 */

import React, { useState, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface TypeInfo {
  type: string;
  description?: string;
  item_type?: string; // For array types
  properties?: Record<string, TypeInfo>; // For object types
}

export interface ParameterDefinition {
  key: string;
  label?: string;
  description?: string;
  type_info: TypeInfo;
}

export interface TypeBuilderProps {
  value: ParameterDefinition[];
  onChange: (value: ParameterDefinition[]) => void;
  allowedTypes?: string[];
  className?: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

const DEFAULT_TYPES = ['string', 'number', 'boolean', 'object', 'array'];

function createDefaultTypeInfo(type: string): TypeInfo {
  if (type === 'array') {
    return {
      type: 'array',
      item_type: 'string',
    };
  } else if (type === 'object') {
    return {
      type: 'object',
      properties: {},
    };
  }
  return { type };
}

function createEmptyParam(): ParameterDefinition {
  return {
    key: '',
    label: '',
    description: '',
    type_info: createDefaultTypeInfo('string'),
  };
}

// ============================================================================
// TypeEditor Component - Edit a single TypeInfo
// ============================================================================

interface TypeEditorProps {
  value: TypeInfo;
  onChange: (value: TypeInfo) => void;
  allowedTypes?: string[];
  level?: number;
}

function TypeEditor({ value, onChange, allowedTypes = DEFAULT_TYPES, level = 0 }: TypeEditorProps) {
  const [expanded, setExpanded] = useState(level === 0);

  const hasChildren = value.type === 'object' || value.type === 'array';

  const handleTypeChange = (newType: string) => {
    onChange(createDefaultTypeInfo(newType));
  };

  return (
    <div className={cn('space-y-2', level > 0 && 'ml-4 pl-4 border-l border-border')}>
      {/* Type Selector */}
      <div className="flex items-center gap-2">
        {hasChildren && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex-shrink-0 text-muted-foreground hover:text-text"
          >
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        )}
        <select
          value={value.type}
          onChange={(e) => handleTypeChange(e.target.value)}
          className="px-2 py-1 text-xs bg-background border border-input rounded"
        >
          {allowedTypes.map((type) => (
            <option key={type} value={type}>
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </option>
          ))}
        </select>
        <Input
          type="text"
          value={value.description || ''}
          onChange={(e) => onChange({ ...value, description: e.target.value })}
          placeholder="Description"
          className="h-7 flex-1 text-xs"
        />
      </div>

      {/* Nested: Array item type */}
      {expanded && value.type === 'array' && (
        <div className="ml-6 space-y-2">
          <div className="text-xs text-muted-foreground">Array Item Type:</div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Item type:</span>
            <select
              value={value.item_type || 'string'}
              onChange={(e) => onChange({ ...value, item_type: e.target.value })}
              className="px-2 py-1 text-xs bg-background border border-input rounded"
            >
              {allowedTypes.filter((t) => t !== 'array').map((type) => (
                <option key={type} value={type}>
                  {type.charAt(0).toUpperCase() + type.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Nested: Object properties */}
      {expanded && value.type === 'object' && (
        <div className="ml-6 space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted-foreground">Object Properties:</div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const newKey = `prop_${Object.keys(value.properties || {}).length + 1}`;
                onChange({
                  ...value,
                  properties: {
                    ...(value.properties || {}),
                    [newKey]: createDefaultTypeInfo('string'),
                  },
                });
              }}
              className="h-6 text-xs"
            >
              <Plus className="w-3 h-3 mr-1" />
              Add Property
            </Button>
          </div>
          <div className="space-y-1">
            {value.properties &&
              Object.entries(value.properties).map(([propKey, propInfo]) => (
                <div key={propKey} className="flex items-start gap-2 p-2 bg-muted/30 rounded">
                  <Input
                    type="text"
                    value={propKey}
                    onChange={(e) => {
                      const newProps = { ...value.properties };
                      delete newProps[propKey];
                      onChange({
                        ...value,
                        properties: { ...newProps, [e.target.value]: propInfo },
                      });
                    }}
                    className="h-7 text-xs w-24 flex-shrink-0"
                  />
                  <TypeEditor
                    value={propInfo}
                    onChange={(newInfo) => {
                      onChange({
                        ...value,
                        properties: { ...value.properties!, [propKey]: newInfo },
                      });
                    }}
                    allowedTypes={allowedTypes}
                    level={level + 1}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      const newProps = { ...value.properties };
                      delete newProps[propKey];
                      onChange({ ...value, properties: newProps });
                    }}
                    className="h-7 w-7 p-0 flex-shrink-0"
                  >
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// ParameterRow Component - Edit a single ParameterDefinition
// ============================================================================

interface ParameterRowProps {
  value: ParameterDefinition;
  onChange: (value: ParameterDefinition) => void;
  onDelete: () => void;
  allowedTypes?: string[];
}

function ParameterRow({ value, onChange, onDelete, allowedTypes }: ParameterRowProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Card className="overflow-hidden">
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 p-3 bg-muted/30 cursor-pointer hover:bg-muted/50"
      >
        <ChevronDown
          className={cn('w-4 h-4 text-muted-foreground transition-transform', !expanded && '-rotate-90')}
        />
        <Input
          type="text"
          value={value.key}
          onChange={(e) => onChange({ ...value, key: e.target.value })}
          placeholder="Variable name"
          className="h-7 text-xs w-32 flex-shrink-0"
          onClick={(e) => e.stopPropagation()}
        />
        <Input
          type="text"
          value={value.label || ''}
          onChange={(e) => onChange({ ...value, label: e.target.value })}
          placeholder="Label (optional)"
          className="h-7 text-xs flex-1"
          onClick={(e) => e.stopPropagation()}
        />
        <div className="text-xs text-muted-foreground flex-shrink-0">
          {value.type_info.type}
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={onDelete}
          className="h-7 w-7 p-0 flex-shrink-0 text-red-500 hover:text-red-600"
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>

      {expanded && (
        <CardContent className="p-3 pt-0">
          <TypeEditor
            value={value.type_info}
            onChange={(newTypeInfo) => onChange({ ...value, type_info: newTypeInfo })}
            allowedTypes={allowedTypes}
          />
        </CardContent>
      )}
    </Card>
  );
}

// ============================================================================
// TypeBuilder Component
// ============================================================================

export function TypeBuilder({
  value,
  onChange,
  allowedTypes = DEFAULT_TYPES,
  className,
}: TypeBuilderProps) {
  const handleAdd = useCallback(() => {
    onChange([...value, createEmptyParam()]);
  }, [value, onChange]);

  const handleUpdate = useCallback(
    (index: number, newValue: ParameterDefinition) => {
      const newValueArray = [...value];
      newValueArray[index] = newValue;
      onChange(newValueArray);
    },
    [value, onChange]
  );

  const handleDelete = useCallback(
    (index: number) => {
      onChange(value.filter((_, i) => i !== index));
    },
    [value, onChange]
  );

  return (
    <div className={cn('space-y-2', className)}>
      {value.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center">
            <p className="text-sm text-muted-foreground mb-3">No parameters defined</p>
            <Button size="sm" onClick={handleAdd}>
              <Plus className="w-4 h-4 mr-1" />
              Add Parameter
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="space-y-2">
            {value.map((param, index) => (
              <ParameterRow
                key={param.key || index}
                value={param}
                onChange={(newValue) => handleUpdate(index, newValue)}
                onDelete={() => handleDelete(index)}
                allowedTypes={allowedTypes}
              />
            ))}
          </div>
          <Button size="sm" variant="outline" onClick={handleAdd} className="w-full">
            <Plus className="w-4 h-4 mr-1" />
            Add Parameter
          </Button>
        </>
      )}
    </div>
  );
}
