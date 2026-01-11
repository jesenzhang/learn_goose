/**
 * JSON Schema Parser - Parse UI component definitions from JSON Schema
 *
 * Handles x-ui-component extensions and filters out internal JSON Schema fields
 */

import { ReactNode } from 'react';

// ============================================================================
// Types
// ============================================================================

export interface UIComponent {
  type: string;
  label: string;
  description?: string;
  props: Record<string, unknown>;
  group?: string;
  hidden?: boolean;
}

export interface ParsedField {
  key: string;
  title: string;
  description?: string;
  type: string;
  default?: unknown;
  enum?: string[];
  ui?: UIComponent;
  required: boolean;
  properties?: Record<string, ParsedField>;
  items?: ParsedField;
  // Array of fields for InputTable
  columns?: Array<{
    title: string;
    dataIndex: string;
    type: string;
    options?: string[];
  }>;
}

export interface ParsedSchema {
  title?: string;
  description?: string;
  type: string;
  fields: Record<string, ParsedField>;
  required: string[];
  definitions?: Record<string, unknown>;
}

// ============================================================================
// Schema Parser
// ============================================================================

/**
 * Internal JSON Schema fields that should be filtered out
 */
const INTERNAL_FIELDS = [
  '$id',
  '$schema',
  '$defs',
  'definitions',
  'allOf',
  'anyOf',
  'oneOf',
  'not',
  'additionalProperties',
  'patternProperties',
  'dependencies',
  'propertyNames',
  'if',
  'then',
  'else',
];

/**
 * Extract UI component metadata from JSON Schema
 */
function extractUIComponent(schema: Record<string, unknown>): UIComponent | undefined {
  const extra = schema.json_schema_extra as Record<string, unknown> | undefined;
  if (!extra) return undefined;

  // Check for x-ui-component (commonly used in backend)
  const xComponent = extra['x-ui-component'] as string | undefined;
  if (xComponent) {
    return {
      type: xComponent,
      label: extra['x-ui-label'] as string | undefined || '',
      description: schema.description as string | undefined,
      props: (extra['x-ui-props'] as Record<string, unknown>) || {},
      group: extra['x-ui-group'] as string | undefined,
      hidden: extra['x-ui-hidden'] as boolean | undefined,
    };
  }

  return undefined;
}

/**
 * Parse a single field schema
 */
function parseField(
  key: string,
  schema: Record<string, unknown>,
  required: string[] = []
): ParsedField {
  const fieldType = (schema.type as string) || 'string';
  const fieldTitle = (schema.title as string) || key;
  const fieldDesc = schema.description as string | undefined;
  const fieldDefault = schema.default;
  const fieldEnum = schema.enum as string[] | undefined;

  // Extract UI component metadata
  const ui = extractUIComponent(schema);

  // Handle array types
  let items: ParsedField | undefined;
  if (fieldType === 'array' && schema.items) {
    const itemsSchema = schema.items as Record<string, unknown>;
    items = parseField('item', itemsSchema);
  }

  // Handle object types with properties
  let properties: Record<string, ParsedField> | undefined;
  if (fieldType === 'object' && schema.properties) {
    const propsSchema = schema.properties as Record<string, Record<string, unknown>>;
    const requiredProps = (schema.required as string[]) || [];
    properties = {};
    for (const [propKey, propSchema] of Object.entries(propsSchema)) {
      // Skip internal fields
      if (INTERNAL_FIELDS.includes(propKey)) continue;
      properties[propKey] = parseField(propKey, propSchema, requiredProps);
    }
  }

  // Check for InputTable columns (from UI.InputTable)
  const columns = ui?.props.columns as Array<{
    title: string;
    dataIndex: string;
    type: string;
    options?: string[];
  }> | undefined;

  return {
    key,
    title: fieldTitle,
    description: fieldDesc,
    type: fieldType,
    default: fieldDefault,
    enum: fieldEnum,
    ui,
    required: required.includes(key),
    properties,
    items,
    columns,
  };
}

/**
 * Parse JSON Schema into a structured format for form rendering
 *
 * @param schema - JSON Schema object
 * @param required - List of required field names
 * @returns Parsed schema with UI component metadata
 */
export function parseSchema(
  schema: Record<string, unknown>,
  required: string[] = []
): ParsedSchema {
  const title = schema.title as string | undefined;
  const description = schema.description as string | undefined;
  const type = (schema.type as string) || 'object';

  const fields: Record<string, ParsedField> = {};
  const requiredFields = (schema.required as string[]) || [];

  // Parse properties
  if (schema.properties) {
    const propsSchema = schema.properties as Record<string, Record<string, unknown>>;
    for (const [key, propSchema] of Object.entries(propsSchema)) {
      // Skip internal JSON Schema fields
      if (INTERNAL_FIELDS.includes(key)) continue;
      fields[key] = parseField(key, propSchema, requiredFields);
    }
  }

  // Extract definitions (for reference)
  const definitions: Record<string, unknown> = {};
  if (schema.$defs) {
    Object.assign(definitions, schema.$defs);
  }
  if (schema.definitions) {
    Object.assign(definitions, schema.definitions);
  }

  return {
    title,
    description,
    type,
    fields,
    required: requiredFields,
    definitions: Object.keys(definitions).length > 0 ? definitions : undefined,
  };
}

/**
 * Get display type for a field (fallback from UI component if available)
 */
export function getFieldType(field: ParsedField): string {
  // Use UI component type if available
  if (field.ui?.type) {
    return field.ui.type;
  }
  // Fallback to JSON Schema type
  return field.type;
}

/**
 * Check if a field should be rendered as a specific component type
 */
export function isComponentType(field: ParsedField, componentType: string): boolean {
  return getFieldType(field) === componentType || field.type === componentType;
}

/**
 * Get all fields from a schema (including nested properties)
 */
export function flattenFields(fields: Record<string, ParsedField>, prefix = ''): ParsedField[] {
  const result: ParsedField[] = [];

  for (const field of Object.values(fields)) {
    const fullKey = prefix ? `${prefix}.${field.key}` : field.key;

    result.push({
      ...field,
      key: fullKey,
    });

    // Recursively handle nested properties
    if (field.properties) {
      result.push(...flattenFields(field.properties, fullKey));
    }

    // Handle array items
    if (field.items && field.items.properties) {
      result.push(...flattenFields(field.items.properties, `${fullKey}[]`));
    }
  }

  return result;
}

/**
 * Extract variable references from a template string
 * e.g., "{{nodeId.field}}" -> ["nodeId.field"]
 */
export function extractVariables(template: string): string[] {
  const pattern = /\{\{([^}]+)\}\}/g;
  const variables: string[] = [];
  let match;

  while ((match = pattern.exec(template)) !== null) {
    const varPath = match[1].trim();
    variables.push(varPath);
  }

  return variables;
}

/**
 * Format a variable path for display
 * e.g., "nodeId.field.subfield" -> "节点名称 > field > subfield"
 */
export function formatVariablePath(path: string, nodeNames: Record<string, string>): string {
  const parts = path.split('.');
  const nodeId = parts[0];
  const nodeName = nodeNames[nodeId] || nodeId;

  if (parts.length === 1) {
    return nodeName;
  }

  return `${nodeName} > ${parts.slice(1).join(' > ')}`;
}
