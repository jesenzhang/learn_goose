/**
 * Pho Workflow Editor - Main App Component
 * Modern React-based workflow editor with React Flow
 */

import { useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { WorkflowCanvas } from './components/workflow/WorkflowCanvas';
import { ComponentPalette } from './components/workflow/ComponentPalette';
import { NodeEditor } from './components/workflow/NodeEditor';
import { Toolbar } from './components/layout/Toolbar';
import { useWorkflowStore } from './stores/workflow';
import { useApi } from './lib/api';
import { cn } from './lib/utils';
import './styles/index.css';

// ============================================================================
// Main App Component
// ============================================================================

function AppContent() {
  const { api, isReady } = useApi();
  const { setComponents, toggleDarkMode } = useWorkflowStore();

  // Load components on mount
  useEffect(() => {
    if (isReady) {
      api.getComponents()
        .then((components) => {
          const componentInfos = components.map((c) => ({
            type: c.type,
            label: c.label,
            group: c.group,
            description: c.description,
            icon: c.icon,
            configSchema: {},
            inputSchema: {},
            outputSchema: {},
          }));
          setComponents(componentInfos);
        })
        .catch((err) => {
          console.error('Failed to load components:', err);
        });
    }
  }, [isReady, api, setComponents]);

  // Check for dark mode preference
  useEffect(() => {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (isDark) {
      toggleDarkMode();
    }
  }, [toggleDarkMode]);

  if (!isReady) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Connecting to Pho API...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-background text-text overflow-hidden">
      {/* Header */}
      <header className="h-14 border-b border-border bg-background flex items-center px-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-text">Pho Workflow Editor</h1>
            <p className="text-xs text-muted-foreground">DAG-based workflow orchestration</p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Component Palette */}
        <aside className="w-72 border-r border-border shrink-0">
          <ComponentPalette />
        </aside>

        {/* Center - Workflow Canvas */}
        <main className="flex-1 relative">
          <Toolbar />
          <WorkflowCanvas />
        </main>

        {/* Right Sidebar - Node Editor */}
        <aside className="w-80 border-l border-border shrink-0">
          <NodeEditor />
        </aside>
      </div>
    </div>
  );
}

// ============================================================================
// App Wrapper with ReactFlowProvider
// ============================================================================

function App() {
  return (
    <ReactFlowProvider>
      <AppContent />
    </ReactFlowProvider>
  );
}

export default App;
