/**
 * Component Palette - Sidebar with draggable workflow components
 * Allows users to drag components onto the canvas
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useWorkflowStore } from '@/stores/workflow';
import { useApi } from '@/lib/api';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { ComponentListItem } from '@/types/workflow';

// ============================================================================
// Component Icons
// ============================================================================

const ComponentIcons: Record<string, React.ReactNode> = {
  Entry: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
    </svg>
  ),
  Exit: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),
  LLM: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
    </svg>
  ),
  Code: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
    </svg>
  ),
  Loop: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  Selector: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
    </svg>
  ),
  HTTP: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
    </svg>
  ),
  Transform: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  Merge: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12M8 12h12M8 17h12M4 7h.01M4 12h.01M4 17h.01" />
    </svg>
  ),
  Split: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 12h16M4 8h8M4 16h8" />
    </svg>
  ),
  Validate: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  Batch: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
    </svg>
  ),
  Output: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
};

// ============================================================================
// Component Item Component
// ============================================================================

interface ComponentItemProps {
  component: ComponentListItem;
  onClick: () => void;
}

function ComponentItem({ component, onClick }: ComponentItemProps) {
  const icon = ComponentIcons[component.label] || ComponentIcons.Transform;

  return (
    <Card
      className="group cursor-pointer hover:bg-muted/50 transition-colors"
      onClick={onClick}
    >
      <div className="flex items-center gap-3 p-3">
        <div className="flex-shrink-0 text-text-muted group-hover:text-primary transition-colors">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-text truncate">{component.label}</p>
          <p className="text-xs text-muted-foreground truncate">{component.description}</p>
        </div>
      </div>
    </Card>
  );
}

// ============================================================================
// Component Palette Component
// ============================================================================

export function ComponentPalette() {
  const { api } = useApi();
  const { addNode } = useWorkflowStore();
  const [components, setComponents] = useState<ComponentListItem[]>([]);
  const [groupedComponents, setGroupedComponents] = useState<Record<string, ComponentListItem[]>>({});
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['Basic', 'Code', 'AI']));

  // Load components from API
  useEffect(() => {
    api.getComponents()
      .then((data) => {
        setComponents(data);
        // Group by category
        const grouped = data.reduce((acc, comp) => {
          if (!acc[comp.group]) {
            acc[comp.group] = [];
          }
          acc[comp.group].push(comp);
          return acc;
        }, {} as Record<string, ComponentListItem[]>);
        setGroupedComponents(grouped);
      })
      .catch((err) => {
        console.error('Failed to load components:', err);
      });
  }, [api]);

  // Filter by search term
  const filteredGroups = useCallback(() => {
    if (!searchTerm) return groupedComponents;

    const lowerSearch = searchTerm.toLowerCase();
    const filtered: Record<string, ComponentListItem[]> = {};

    Object.entries(groupedComponents).forEach(([group, comps]) => {
      const matching = comps.filter(c =>
        c.label.toLowerCase().includes(lowerSearch) ||
        c.description.toLowerCase().includes(lowerSearch) ||
        c.type.toLowerCase().includes(lowerSearch)
      );
      if (matching.length > 0) {
        filtered[group] = matching;
      }
    });

    return filtered;
  }, [groupedComponents, searchTerm]);

  // Toggle group expansion
  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
  };

  // Add node to workflow
  const handleAddComponent = (component: ComponentListItem) => {
    const id = `${component.type}-${Date.now()}`;
    // Normalize type to lowercase for styling consistency
    const normalizedType = component.type.toLowerCase();
    const newNode = {
      id,
      type: 'custom',
      position: { x: Math.random() * 400 + 100, y: Math.random() * 300 + 100 },
      data: {
        id,
        type: normalizedType,
        label: component.label,
        componentType: component.type,
        isValid: true,
      },
    };
    addNode(newNode);
  };

  const groups = filteredGroups();

  return (
    <div className="flex flex-col h-full bg-background border-l border-border">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <h2 className="text-sm font-semibold text-text mb-3">Components</h2>
        <Input
          type="search"
          placeholder="Search components..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="h-8"
        />
      </div>

      {/* Component List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-4">
        {Object.entries(groups).map(([group, comps]) => (
          <div key={group}>
            <button
              onClick={() => toggleGroup(group)}
              className="flex items-center gap-2 w-full text-xs font-semibold text-text-muted hover:text-text transition-colors mb-2"
            >
              <svg
                className={cn(
                  'w-3 h-3 transition-transform',
                  expandedGroups.has(group) ? 'rotate-90' : ''
                )}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              {group}
              <span className="ml-auto text-xs">({comps.length})</span>
            </button>

            {expandedGroups.has(group) && (
              <div className="space-y-2 ml-1">
                {comps.map((comp) => (
                  <ComponentItem
                    key={comp.type}
                    component={comp}
                    onClick={() => handleAddComponent(comp)}
                  />
                ))}
              </div>
            )}
          </div>
        ))}

        {Object.keys(groups).length === 0 && (
          <div className="text-center py-8">
            <p className="text-sm text-muted-foreground">No components found</p>
          </div>
        )}
      </div>
    </div>
  );
}
