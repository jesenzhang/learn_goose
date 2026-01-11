/**
 * Dynamic Form Component - Renders form fields based on JSON Schema
 *
 * Supports x-ui-component extensions:
 * - Input, TextArea, Secret
 * - Number, Slider
 * - Select, Radio, Checkbox, Switch
 * - JsonEditor, CodeEditor
 * - InputTable, TypeBuilder, ListEditor
 */

import React, { useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  parseSchema,
  ParsedField,
  getFieldType,
  isComponentType,
  flattenFields,
} from '@/lib/schemaParser';

// ============================================================================
// Field Renderer Props
// ============================================================================

interface FieldRendererProps {
  field: ParsedField;
  value: unknown;
  onChange: (value: unknown) => void;
  nodeId?: string;
  availableVars?: Array<{ path: string; label: string }>;
}

// ============================================================================
// Field Renderer Component
// ============================================================================

function FieldRenderer({ field, value, onChange, nodeId, availableVars }: FieldRendererProps) {
  const fieldType = getFieldType(field);
  const fieldValue = value ?? field.default ?? '';

  const handleChange = useCallback(
    (newValue: unknown) => {
      onChange(newValue);
    },
    [onChange]
  );

  // Render based on UI component type
  switch (fieldType) {
    case 'Input':
      return (
        <Input
          type="text"
          value={fieldValue as string}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={(field.ui?.props.placeholder as string) || field.description}
          className="h-8"
        />
      );

    case 'TextArea':
      return (
        <Textarea
          value={fieldValue as string}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={(field.ui?.props.placeholder as string) || field.description}
          rows={(field.ui?.props.rows as number) || 3}
        />
      );

    case 'Secret':
      return (
        <Input
          type="password"
          value={fieldValue as string}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={(field.ui?.props.placeholder as string) || '********'}
          className="h-8"
        />
      );

    case 'InputNumber':
    case 'Number':
      return (
        <Input
          type="number"
          value={fieldValue as number}
          onChange={(e) => handleChange(Number(e.target.value))}
          min={field.ui?.props.min as number | undefined}
          max={field.ui?.props.max as number | undefined}
          step={field.ui?.props.step as number | undefined}
          className="h-8"
        />
      );

    case 'Slider':
      return (
        <div className="flex items-center gap-3">
          <input
            type="range"
            value={fieldValue as number}
            onChange={(e) => handleChange(Number(e.target.value))}
            min={field.ui?.props.min as number | 0}
            max={field.ui?.props.max as number | 100}
            step={field.ui?.props.step as number | 1}
            className="flex-1"
          />
          <span className="text-sm text-muted-foreground w-12 text-right">
            {fieldValue}
          </span>
        </div>
      );

    case 'Select':
      const selectOptions = field.enum || (field.ui?.props.options as string[]) || [];
      return (
        <select
          value={fieldValue as string}
          onChange={(e) => handleChange(e.target.value)}
          className="w-full px-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {!fieldValue && <option value="">请选择...</option>}
          {selectOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );

    case 'Radio':
      const radioOptions = field.enum || (field.ui?.props.options as Array<{label: string; value: string}>) || [];
      return (
        <div className="space-y-2">
          {radioOptions.map((opt) => {
            const label = typeof opt === 'string' ? opt : opt.label;
            const val = typeof opt === 'string' ? opt : opt.value;
            return (
              <label key={val} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name={field.key}
                  value={val}
                  checked={fieldValue === val}
                  onChange={() => handleChange(val)}
                  className="w-4 h-4"
                />
                <span className="text-sm">{label}</span>
              </label>
            );
          })}
        </div>
      );

    case 'Checkbox':
      const checkboxOptions = field.ui?.props.options as Array<{label: string; value: string}> || [];
      const selectedValues = fieldValue as string[] || [];
      return (
        <div className="space-y-2">
          {checkboxOptions.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                value={opt.value}
                checked={selectedValues.includes(opt.value)}
                onChange={(e) => {
                  const newValues = e.target.checked
                    ? [...selectedValues, opt.value]
                    : selectedValues.filter((v) => v !== opt.value);
                  handleChange(newValues);
                }}
                className="w-4 h-4"
              />
              <span className="text-sm">{opt.label}</span>
            </label>
          ))}
        </div>
      );

    case 'Switch':
      return (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={fieldValue as boolean}
            onChange={(e) => handleChange(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-sm">{field.title}</span>
        </label>
      );

    case 'JsonEditor':
    case 'Json':
      try {
        const jsonStr = typeof fieldValue === 'string' ? fieldValue : JSON.stringify(fieldValue || {}, null, 2);
        return (
          <Textarea
            value={jsonStr}
            onChange={(e) => {
              try {
                handleChange(JSON.parse(e.target.value));
              } catch {
                // Invalid JSON, keep as string
                handleChange(e.target.value);
              }
            }}
            placeholder="Enter JSON..."
            rows={(field.ui?.props.rows as number) || 5}
            className="font-mono text-xs"
          />
        );
      } catch {
        return (
          <Textarea
            value={String(fieldValue)}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="Enter JSON..."
            rows={5}
            className="font-mono text-xs"
          />
        );
      }

    case 'CodeEditor':
    case 'Code':
      return (
        <Textarea
          value={fieldValue as string}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={`Enter ${field.ui?.props.language || 'python'} code...`}
          rows={(field.ui?.props.rows as number) || 5}
          className="font-mono text-xs"
        />
      );

    case 'TypeBuilder':
      // Special component for building nested type definitions
      return (
        <Card>
          <CardContent className="p-3">
            <div className="text-sm text-muted-foreground mb-2">
              {field.description || 'Configure parameters'}
            </div>
            <div className="text-xs text-muted-foreground">
              TypeBuilder component - for parameter configuration
            </div>
          </CardContent>
        </Card>
      );

    case 'InputTable':
    case 'ListEditor':
      // Table/List editor for array items
      return (
        <Card>
          <CardContent className="p-3">
            <div className="text-sm text-muted-foreground mb-2">
              {field.description || 'Configure items'}
            </div>
            <div className="text-xs text-muted-foreground">
              {fieldType === 'InputTable' ? 'InputTable' : 'ListEditor'} component
            </div>
          </CardContent>
        </Card>
      );

    default:
      // Default fallback to text input
      return (
        <Input
          type="text"
          value={fieldValue as string}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={field.description}
          className="h-8"
        />
      );
  }
}

// ============================================================================
// Form Field Component
// ============================================================================

interface FormFieldProps {
  field: ParsedField;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
  nodeId?: string;
  availableVars?: Array<{ path: string; label: string }>;
}

function FormField({ field, value, onChange, nodeId, availableVars }: FormFieldProps) {
  const fieldType = getFieldType(field);

  return (
    <div className={cn('space-y-1', field.ui?.hidden && 'hidden')}>
      {/* Label */}
      <div className="flex items-center gap-2">
        <label className={cn(
          'text-xs font-medium text-text',
          fieldType === 'Switch' && 'cursor-pointer'
        )}>
          {field.title}
          {field.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      </div>

      {/* Description */}
      {field.description && fieldType !== 'Switch' && (
        <p className="text-xs text-muted-foreground">{field.description}</p>
      )}

      {/* Field Input */}
      <FieldRenderer
        field={field}
        value={value}
        onChange={(newValue) => onChange(field.key, newValue)}
        nodeId={nodeId}
        availableVars={availableVars}
      />
    </div>
  );
}

// ============================================================================
// Dynamic Form Component
// ============================================================================

export interface DynamicFormProps {
  schema: Record<string, unknown>;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  nodeId?: string;
  availableVars?: Array<{ path: string; label: string }>;
  className?: string;
}

export function DynamicForm({
  schema,
  value,
  onChange,
  nodeId,
  availableVars,
  className,
}: DynamicFormProps) {
  const parsed = parseSchema(schema);
  const fields = Object.values(parsed.fields);

  // Filter out hidden fields
  const visibleFields = fields.filter((f) => !f.ui?.hidden);

  if (visibleFields.length === 0) {
    return (
      <div className={cn('text-center py-4', className)}>
        <p className="text-sm text-muted-foreground">No configuration options</p>
      </div>
    );
  }

  const handleFieldChange = useCallback(
    (key: string, fieldValue: unknown) => {
      onChange({ ...value, [key]: fieldValue });
    },
    [value, onChange]
  );

  return (
    <div className={cn('space-y-3', className)}>
      {visibleFields.map((field) => (
        <FormField
          key={field.key}
          field={field}
          value={value[field.key]}
          onChange={handleFieldChange}
          nodeId={nodeId}
          availableVars={availableVars}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Variable Picker Component (for {{}} syntax support)
// ============================================================================

export interface VariablePickerProps {
  value: string;
  onChange: (value: string) => void;
  availableVars: Array<{ path: string; label: string }>;
  placeholder?: string;
}

export function VariablePicker({ value, onChange, availableVars, placeholder }: VariablePickerProps) {
  return (
    <div className="space-y-2">
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder || 'Use {{nodeId.field}} to reference values'}
        rows={3}
        className="font-mono text-xs"
      />
      {availableVars.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-text">
            Available variables
          </summary>
          <div className="mt-2 pl-4 space-y-1">
            {availableVars.map((v) => (
              <div
                key={v.path}
                className="cursor-pointer hover:text-primary"
                onClick={() => onChange(value + `{{${v.path}}}`)}
              >
                <code className="text-xs">{`{{${v.path}}}`}</code>
                <span className="ml-2 text-muted-foreground">{v.label}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
