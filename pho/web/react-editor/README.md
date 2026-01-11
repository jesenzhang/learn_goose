# Pho Workflow Editor

Modern React-based workflow editor for Pho - DAG-based workflow orchestration framework.

## Features

- **Visual Workflow Editor**: Drag-and-drop interface using React Flow
- **Component Palette**: Browse and search available workflow components
- **Property Editor**: Configure nodes with a comprehensive properties panel
- **Real-time Validation**: Validate workflows before execution
- **Dark/Light Mode**: Automatic theme switching based on system preferences
- **Responsive Design**: Clean, modern UI built with Tailwind CSS 4
- **Type-Safe**: Full TypeScript support with type-safe API calls

## Tech Stack

- **React 19** - Latest React with concurrent features
- **TypeScript** - Type-safe development
- **Vite** - Fast build tool and dev server
- **React Flow** - Powerful workflow visualization library
- **Tailwind CSS 4** - Modern utility-first CSS framework
- **Radix UI** - Headless component library
- **Zustand** - Lightweight state management
- **Lucide React** - Beautiful icon library

## Project Structure

```
react-editor/
├── src/
│   ├── components/
│   │   ├── ui/              # Radix UI base components
│   │   ├── workflow/        # Workflow-specific components
│   │   │   ├── nodes/       # Custom React Flow nodes
│   │   │   ├── WorkflowCanvas.tsx
│   │   │   ├── ComponentPalette.tsx
│   │   │   └── NodeEditor.tsx
│   │   └── layout/          # Layout components
│   │       └── Toolbar.tsx
│   ├── stores/
│   │   └── workflow.ts      # Zustand workflow store
│   ├── lib/
│   │   ├── api.ts           # Type-safe API client
│   │   └── utils.ts         # Utility functions
│   ├── types/
│   │   └── workflow.ts      # TypeScript type definitions
│   ├── styles/
│   │   └── index.css        # Tailwind CSS with design tokens
│   ├── App.tsx              # Main app component
│   └── main.tsx             # Entry point
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── tailwind.config.js
```

## Getting Started

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Pho API server running on `http://localhost:8000`

### Installation

```bash
cd pho/web/react-editor
npm install
```

### Development

```bash
# Start dev server (runs on http://localhost:3000)
npm run dev

# Type check
npm run type-check

# Lint
npm run lint

# Build for production
npm run build

# Preview production build
npm run preview
```

### API Server

The editor expects the Pho API server to be running on `http://localhost:8000`.

Start the API server:

```bash
cd pho
python -m pho.api.app
```

## Usage

### Creating a Workflow

1. **Add Components**: Click on components in the left palette to add them to the canvas
2. **Connect Nodes**: Drag from the output handle of one node to the input handle of another
3. **Configure Nodes**: Click on a node to edit its properties in the right panel
4. **Validate**: Click the validation button to check for errors
5. **Execute**: Click Execute to run the workflow

### Keyboard Shortcuts

- `Delete` / `Backspace` - Delete selected node or edge
- `Ctrl+S` - Save workflow (not yet implemented)
- `Ctrl+O` - Load workflow (not yet implemented)
- `Ctrl+Z` - Undo (not yet implemented)

## Design Tokens

The editor uses design tokens aligned with goose-rs:

```css
--color-block-teal: #13bbaf;
--color-block-orange: #ff4f00;

/* Node colors */
--color-node-entry: var(--color-green-100);
--color-node-exit: var(--color-red-100);
--color-node-llm: var(--color-blue-100);
--color-node-code: var(--color-purple-100);
--color-node-control: var(--color-yellow-100);
--color-node-api: var(--color-orange-100);
--color-node-data: var(--color-neutral-200);
```

## API Integration

The editor communicates with the Pho API server:

- `GET /components/` - List all available components
- `GET /components/{type}` - Get component details
- `POST /api/v1/workflows/execute` - Execute a workflow
- `GET /api/v1/workflows/examples` - Get example workflows

## Component Development

### Adding a New Node Type

1. Add the icon to `CustomNode.tsx`:

```typescript
const NodeIcons: Record<string, React.ReactNode> = {
  myNode: <svg>...</svg>,
};
```

2. Add styling:

```typescript
const getNodeStyles = (type: string) => {
  const styles: Record<string, string> = {
    myNode: 'bg-purple-100 border-purple-500',
  };
  return styles[type] || 'bg-node-data border-neutral-400';
};
```

3. Register the component in the backend Pho API

## Troubleshooting

### API Connection Issues

If you see "Connecting to Pho API..." message:

1. Ensure the API server is running on port 8000
2. Check browser console for CORS errors
3. Verify `VITE_API_BASE_URL` environment variable if API is on a different port

### Components Not Loading

1. Check browser console for errors
2. Verify API server endpoints are accessible
3. Try refreshing the page

## Future Enhancements

- [ ] Workflow save/load with persistence
- [ ] Undo/redo functionality
- [ ] Workflow templates library
- [ ] Real-time collaboration
- [ ] Workflow execution monitoring
- [ ] Custom node creation UI
- [ ] Export to YAML/JSON
- [ ] Import from other workflow formats

## License

MIT

## Contributing

Contributions welcome! Please read our contributing guidelines before submitting PRs.
