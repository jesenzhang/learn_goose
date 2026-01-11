/**
 * API client for Pho workflow backend
 * Type-safe API calls to FastAPI backend
 */

import type {
  ComponentListItem,
  ComponentDetailResponse,
  ComponentGroupsResponse,
  WorkflowExecuteRequest,
  WorkflowExecuteResponse,
  ExampleWorkflow,
} from '@/types/workflow';

// ============================================================================
// API Configuration
// ============================================================================

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8300';

// ============================================================================
// Types
// ============================================================================

interface ApiError {
  code: number;
  message: string;
  detail?: string;
}

class ApiException extends Error {
  constructor(public error: ApiError) {
    super(error.message);
    this.name = 'ApiException';
  }
}

// ============================================================================
// API Client
// ============================================================================

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({
        code: response.status,
        message: response.statusText || 'Unknown error',
      }));
      throw new ApiException(error);
    }

    return response.json();
  }

  // ========================================================================
  // Component API
  // ========================================================================

  /**
   * Get all registered components
   */
  async getComponents(): Promise<ComponentListItem[]> {
    return this.request<ComponentListItem[]>('/components/');
  }

  /**
   * Get detailed component definition
   */
  async getComponentDetail(type: string): Promise<ComponentDetailResponse> {
    return this.request<ComponentDetailResponse>(`/components/${encodeURIComponent(type)}`);
  }

  /**
   * Get components grouped by category
   */
  async getComponentGroups(): Promise<ComponentGroupsResponse> {
    return this.request<ComponentGroupsResponse>('/components/groups');
  }

  // ========================================================================
  // Workflow API
  // ========================================================================

  /**
   * List all workflows
   */
  async listWorkflows(): Promise<WorkflowInfo[]> {
    return this.request<WorkflowInfo[]>('/api/v1/workflows/');
  }

  /**
   * Get workflow details
   */
  async getWorkflow(workflowId: string): Promise<WorkflowDetail> {
    return this.request<WorkflowDetail>(`/api/v1/workflows/${encodeURIComponent(workflowId)}`);
  }

  /**
   * Create a new workflow
   */
  async createWorkflow(data: CreateWorkflowRequest): Promise<WorkflowDetail> {
    return this.request<WorkflowDetail>('/api/v1/workflows/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Update a workflow
   */
  async updateWorkflow(
    workflowId: string,
    data: UpdateWorkflowRequest
  ): Promise<WorkflowDetail> {
    return this.request<WorkflowDetail>(`/api/v1/workflows/${encodeURIComponent(workflowId)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * Delete a workflow
   */
  async deleteWorkflow(workflowId: string): Promise<void> {
    return this.request<void>(`/api/v1/workflows/${encodeURIComponent(workflowId)}`, {
      method: 'DELETE',
    });
  }

  /**
   * Execute a workflow
   */
  async executeWorkflow(request: WorkflowExecuteRequest): Promise<WorkflowExecuteResponse> {
    const endpoint = request.workflow_id
      ? `/api/v1/workflows/${encodeURIComponent(request.workflow_id)}/execute`
      : '/api/v1/workflows/execute';

    return this.request<WorkflowExecuteResponse>(endpoint, {
      method: 'POST',
      body: JSON.stringify({
        inputs: request.inputs,
        workflow: request.workflow,
      }),
    });
  }

  /**
   * Validate a workflow
   */
  async validateWorkflow(workflow: WorkflowDefinition): Promise<ValidationResult> {
    return this.request<ValidationResult>('/api/v1/workflows/validate', {
      method: 'POST',
      body: JSON.stringify(workflow),
    });
  }

  /**
   * Export workflow to YAML
   */
  async exportWorkflow(workflowId: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/api/v1/workflows/${encodeURIComponent(workflowId)}/export`);
    if (!response.ok) {
      throw new ApiException({
        code: response.status,
        message: response.statusText,
      });
    }
    return response.text();
  }

  /**
   * Import workflow from YAML
   */
  async importWorkflow(yaml: string): Promise<WorkflowDetail> {
    return this.request<WorkflowDetail>('/api/v1/workflows/import', {
      method: 'POST',
      headers: {
        'Content-Type': 'text/yaml',
      },
      body: yaml,
    });
  }

  // ========================================================================
  // Example Workflows
  // ========================================================================

  /**
   * Get all example workflows
   */
  async getExamples(): Promise<ExampleWorkflow[]> {
    return this.request<ExampleWorkflow[]>('/api/v1/workflows/examples');
  }

  /**
   * Get a specific example workflow
   */
  async getExample(exampleId: string): Promise<ExampleWorkflow> {
    return this.request<ExampleWorkflow>(`/api/v1/workflows/examples/${encodeURIComponent(exampleId)}`);
  }

  // ========================================================================
  // Health Check
  // ========================================================================

  /**
   * Check API health
   */
  async healthCheck(): Promise<{ status: string; service: string; version: string }> {
    return this.request('/health');
  }
}

// ============================================================================
// Additional Types
// ============================================================================

interface WorkflowInfo {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface WorkflowDetail {
  id: string;
  name: string;
  description?: string;
  definition: WorkflowDefinition;
  created_at: string;
  updated_at: string;
}

interface CreateWorkflowRequest {
  name: string;
  description?: string;
  definition: WorkflowDefinition;
}

interface UpdateWorkflowRequest {
  name?: string;
  description?: string;
  definition?: WorkflowDefinition;
}

interface WorkflowDefinition {
  name: string;
  nodes: WorkflowNodeConfig[];
  edges: WorkflowEdgeConfig[];
  entry_point?: string;
}

interface WorkflowNodeConfig {
  id: string;
  component_type: string;
  label?: string;
  config?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
}

interface WorkflowEdgeConfig {
  source: string;
  target: string;
  source_handle?: string;
  target_handle?: string;
  condition?: string;
}

interface ValidationResult {
  is_valid: boolean;
  errors: ValidationError[];
}

interface ValidationError {
  type: 'node' | 'edge' | 'workflow';
  id?: string;
  message: string;
  severity: 'error' | 'warning';
}

// ============================================================================
// Singleton Instance
// ============================================================================

export const api = new ApiClient();

// ============================================================================
// React Hook
// ============================================================================

import { useEffect, useState, useCallback } from 'react';

export function useApi() {
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api
      .healthCheck()
      .then(() => setIsReady(true))
      .catch((err) => {
        if (err instanceof ApiException) {
          setError(err.error);
        } else {
          setError({
            code: 0,
            message: 'Failed to connect to API',
          });
        }
      });
  }, []);

  const executeWorkflow = useCallback(async (request: WorkflowExecuteRequest) => {
    return api.executeWorkflow(request);
  }, []);

  return {
    api,
    isReady,
    error,
    executeWorkflow,
  };
}
