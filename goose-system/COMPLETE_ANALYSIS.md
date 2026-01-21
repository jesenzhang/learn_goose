# Goose-RS Agent Skill System - Complete Analysis

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Core Design Patterns](#core-design-patterns)
4. [Implementation Details](#implementation-details)
5. [Comparison with Python Replica](#comparison-with-python-replica)
6. [Key Design Decisions](#key-design-decisions)
7. [Testing Strategy](#testing-strategy)
8. [Security Considerations](#security-considerations)

---

## Executive Summary

Goose-RS implements a comprehensive Agent Skill System as part of its MCP (Model Context Protocol) platform extensions. The system follows a **Platform Extension pattern** where skills are declaratively defined using Markdown files with YAML frontmatter, discovered from multiple directories with override semantics, and exposed through a unified MCP client interface.

### Key Characteristics

| Aspect | Description |
|---------|-------------|
| **Paradigm** | Declarative skill definition (YAML + Markdown) |
| **Discovery** | Multi-directory with priority-based override |
| **Protocol** | MCP (Model Context Protocol) compliant |
| **Extensibility** | Platform Extension pattern with pluggable clients |
| **Testing** | Comprehensive unit and integration tests |
| **Security** | Environment variable allowlist for sandboxing |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ExtensionManager                         │
│  (Central coordinator for all extensions)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                              │
│        ┌──────────────────┬──────────────────┬──────────────┐ │
│        │                  │                  │              │ │
│   ┌────▼────┐      │      ┌─────────▼───┐      │ │
│   │  Skills  │      │      │Extension    │      │ │
│   │  Client  │      │      │Manager     │      │ │
│   │          │      │      │             │      │ │
│   │  loadSkill│      │      │discover/    │      │ │
│   │  tool    │      │      │enable       │      │ │
│   └──────────┘      │      │extensions   │      │ │
│                      │      └──────────────┘      │ │
│                      │                             │ │
│                      └─────────────┬─────────────┘ │
│                                    │                   │
└────────────────────────────┴───────────────────┘
```

### Component Hierarchy

```
crates/goose/src/agents/
├── extension.rs              # Extension definitions and configs
├── extension_manager.rs      # Central manager for all extensions
├── mcp_client.rs             # MCP client trait and base implementation
├── skills_extension.rs       # SKILL SYSTEM IMPLEMENTATION (835 lines)
├── mod.rs                    # Module exports
├── platform_tools.rs         # Built-in platform tools
└── [other extensions]
    ├── todo_extension.rs
    ├── chatrecall_extension.rs
    └── code_execution_extension.rs
```

---

## Core Design Patterns

### 1. Platform Extension Pattern

```rust
pub struct PlatformExtensionDef {
    pub name: &'static str,
    pub description: &'static str,
    pub default_enabled: bool,
    pub client_factory: fn(PlatformExtensionContext) -> Box<dyn McpClientTrait>,
}

// Global registry
pub static PLATFORM_EXTENSIONS: Lazy<HashMap<&'static str, PlatformExtensionDef>> = Lazy::new(|| {
    let mut map = HashMap::new();
    map.insert("skills", PlatformExtensionDef { ... });
    map.insert("todo", PlatformExtensionDef { ... });
    // ...
    map
});
```

**Benefits**:
- Centralized registration
- Lazy initialization
- Type-safe factory functions
- Enable/disable at runtime

### 2. MCP Protocol Pattern

```rust
#[async_trait]
pub trait McpClientTrait: Send + Sync {
    async fn list_tools(&self, ...) -> Result<ListToolsResult, Error>;
    async fn call_tool(&self, ...) -> Result<CallToolResult, Error>;
    fn get_info(&self) -> Option<&InitializeResult>;
    async fn list_resources(...) -> Result<ListResourcesResult, Error>;
    async fn read_resource(...) -> Result<ReadResourceResult, Error>;
    async fn list_prompts(...) -> Result<ListPromptsResult, Error>;
    async fn get_prompt(...) -> Result<GetPromptResult, Error>;
    async fn subscribe(&self) -> mpsc::Receiver<ServerNotification>;
}
```

**Implementation in SkillsClient**:
```rust
impl McpClientTrait for SkillsClient {
    async fn list_tools(...) -> Result<ListToolsResult, Error> {
        let tools = if self.skills.is_empty() {
            Vec::new()
        } else {
            Self::get_tools()
        };
        Ok(ListToolsResult { tools, next_cursor: None, meta: None })
    }
    
    async fn call_tool(...) -> Result<CallToolResult, Error> {
        let content = match name {
            "loadSkill" => self.handle_load_skill(arguments).await,
            _ => Err(format!("Unknown tool: {}", name)),
        };
        // ...
    }
    
    fn get_info(&self) -> Option<&InitializeResult> {
        Some(&self.info)
    }
}
```

### 3. Skill Declaration Pattern

**Format**: YAML frontmatter + Markdown body

```markdown
---
name: file-operations
description: Perform file operations like read, write, delete
author: AI Assistant
version: 1.0.0
tags:
  - file
  - io
---

# File Operations Skill

This skill provides capabilities for working with files.

## Available Tools

Use these tools to:
- Read files
- Write files
- List directories
- Delete files
```

**Metadata Schema**:
```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
struct SkillMetadata {
    name: String,
    description: String,
}

#[derive(Debug, Clone)]
struct Skill {
    metadata: SkillMetadata,
    body: String,
    directory: PathBuf,
    supporting_files: Vec<PathBuf>,
}
```

### 4. Multi-Directory Discovery Pattern

**Priority Order** (low to high priority for override):
1. `~/.claude/skills` - Global Claude (lowest)
2. `~/.config/agents/skills` - Global agents
3. `<config_dir>/skills` - XDG config directory
4. `<working_dir>/.claude/skills` - Working dir Claude
5. `<working_dir>/.goose/skills` - Working dir Goose
6. `<working_dir>/.agents/skills` - Working dir agents (highest)

**Implementation**:
```rust
fn discover_skills_in_directories(directories: &[PathBuf]) -> HashMap<String, Skill> {
    let mut skills = HashMap::new();
    
    for dir in directories {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let skill_file = path.join("SKILL.md");
                    if skill_file.exists() {
                        if let Ok(skill) = Self::parse_skill_file(&skill_file) {
                            // Override: later directories overwrite earlier ones
                            skills.insert(skill.metadata.name.clone(), skill);
                        }
                    }
                }
            }
        }
    }
    
    skills
}
```

**Override Semantics**: HashMap `insert` replaces existing entries, so later directories override earlier ones with the same skill name.

### 5. Session ID Injection Pattern

```rust
#[derive(Clone, Debug)]
pub struct McpMeta {
    pub session_id: String,
}

fn inject_session_id_into_extensions(mut extensions: Extensions, session_id: &str) -> Extensions {
    let mut meta_map = extensions.get::<Meta>().map(|meta| meta.0.clone()).unwrap_or_default();
    meta_map.insert(SESSION_ID_HEADER.to_string(), Value::String(session_id.to_string()));
    extensions.insert(Meta(meta_map));
    extensions
}
```

**Purpose**: Track which session is making MCP requests for logging and debugging.

---

## Implementation Details

### SkillsClient Structure (835 lines total)

```rust
pub struct SkillsClient {
    info: InitializeResult,
    skills: HashMap<String, Skill>,
}

impl SkillsClient {
    // 1. Initialize with discovered skills
    pub fn new(_context: PlatformExtensionContext) -> Result<Self> { ... }
    
    // 2. Parse SKILL.md files
    fn parse_skill_file(path: &Path) -> Result<Skill> { ... }
    fn parse_frontmatter(content: &str) -> Result<(SkillMetadata, String)> { ... }
    fn find_supporting_files(directory: &Path, skill_file: &Path) -> Result<Vec<PathBuf>> { ... }
    
    // 3. Discover skills from directories
    fn get_default_skill_directories() -> Vec<PathBuf> { ... }
    fn discover_skills_in_directories(directories: &[PathBuf]) -> HashMap<String, Skill> { ... }
    
    // 4. Generate LLM instructions
    fn generate_instructions(&self) -> String { ... }
    
    // 5. Handle tool calls
    async fn handle_load_skill(&self, arguments: Option<JsonObject>) -> Result<Vec<Content>, String> { ... }
    fn get_tools() -> Vec<Tool> { ... }
}
```

### Test Coverage (434 lines of tests)

| Test Category | Tests | Coverage |
|--------------|-------|----------|
| Frontmatter parsing | 5 tests | Valid, missing delimiter, unclosed, extra fields |
| Skill file parsing | 1 test | Full skill with supporting files |
| Multi-directory discovery | 2 tests | Single directory, multiple directories |
| Override semantics | 1 test | Working dir overrides global |
| Instructions generation | 3 tests | Empty, with skills, alphabetical sorting |
| Tool availability | 2 tests | No skills → no tools, skills → tools available |

**Total**: 14 test cases, comprehensive coverage.

---

## Comparison with Python Replica

| Aspect | Goose-RS (Rust) | Python Replica (goose-skill-system) |
|---------|---------------------|-----------------------------------|
| **Language** | Rust (performance, type safety) | Python (rapid dev, ecosystem) |
| **Protocol** | Full MCP (7 methods) | Partial MCP (3 methods) |
| **Discovery dirs** | 6 default directories | 7 directories (includes `skills/` plain dir) |
| **Testing** | 14 tests (inline) | 15 tests (separate files) |
| **Async** | tokio-based | Currently synchronous |
| **Error types** | Custom Error enum + anyhow::Result | Python exceptions |
| **Session ID** | Automatic injection | Not implemented |
| **Security** | DISALLOWED_KEYS allowlist | Basic validation |

### Alignment Status

✅ **Aligned**:
- Skill file format (YAML frontmatter + Markdown)
- loadSkill tool implementation
- Multi-directory discovery with override
- Supporting files collection

⚠️ **Partially Aligned**:
- MCP protocol (basic methods, missing resources/prompts/subscribe)
- Testing (separate test files, less inline)
- Caching (has cache but inconsistent)

❌ **Not Aligned**:
- Async/await patterns
- Session ID injection
- Security allowlist
- Complete MCP protocol (resources, prompts, notifications)

---

## Key Design Decisions

### 1. Why HashMap for Skills?

**Decision**: Use `HashMap<String, Skill>` for skill storage

**Rationale**:
- O(1) lookup by name
- Automatic override on insert
- No need for explicit merge logic

**Trade-off**: No way to detect conflicts (silent override)

### 2. Why String Splitting for Frontmatter?

**Decision**: `content.split("---").collect::<Vec<&str>>()`

**Rationale**: Simple, no dependencies

**Trade-off**: If body contains `---`, it gets split incorrectly

**Better approach**: Use a proper frontmatter parser (e.g., `frontmatter` crate)

### 3. Why Separate Extension Types?

**Decision**: Multiple extension types (Stdio, SSE, Builtin, Platform, Frontend, InlinePython)

**Rationale**:
- Different communication patterns
- Different initialization requirements
- Different capabilities

**Trade-off**: Increased complexity in ExtensionConfig enum

### 4. Why Session ID in Extensions?

**Decision**: Inject session ID into MCP request extensions

**Rationale**:
- Track which session made which request
- Debugging and logging
- No impact on skill functionality

**Trade-off**: Tightly coupled to session management system

---

## Testing Strategy

### Goose-RS Test Philosophy

1. **Inline Tests**: All tests in `#[cfg(test)]` module at bottom of file
2. **TempDir**: Uses `tempfile::TempDir` for isolated test environments
3. **Isolation**: Each test creates fresh directories and skills
4. **Assertions**: Clear, specific assertions for expected behavior

### Test Naming Convention

```rust
fn test_<feature>()         // Basic feature test
fn test_<feature>_with_<condition>()  // Conditional test
fn test_<feature>_when_<event>()   // Event-driven test
async fn test_<feature>()     // Async test
```

### Example: Discovery Override Test (lines 746-833)

```rust
#[test]
fn test_discover_skills_working_dir_overrides_global() {
    let temp_dir = TempDir::new().unwrap();
    
    // Create skills in 4 directories with same name
    let global_claude = temp_dir.path().join("global-claude");
    // ... (create skill in global)
    
    let working_goose = temp_dir.path().join("working-goose");
    // ... (create skill in working dir)
    
    // Test: working dir overrides global
    let skills = SkillsClient::discover_skills_in_directories(&[
        global_claude, working_goose  // working_goose comes last
    ]);
    
    assert_eq!(skills.len(), 1);
    assert_eq!(
        skills.get("my-skill").unwrap().metadata.description,
        "From working dir goose"  // Last directory wins
    );
}
```

---

## Security Considerations

### Environment Variable Allowlist (31 keys)

**Purpose**: Prevent code execution extensions from hijacking critical system paths and environment variables.

**Blocked Categories**:
- 🧬 Binary path manipulation (PATH, PATHEXT, SystemRoot)
- 🧬 Dynamic linker hijacking (LD_LIBRARY_PATH, LD_PRELOAD, DYLD_LIBRARY_PATH)
- 🐍 Language runtimes (PYTHONPATH, PYTHONHOME, NODE_OPTIONS, RUBYOPT, GEM_PATH)
- 🍎 Classpaths (CLASSPATH)
- 🐧 Compilers (GO111MODULE, GOROOT)
- 🖥️ Windows-specific (APPINIT_DLLS, SESSIONNAME, ComSpec)
- 💾 Temp directories (TEMP, TMP, LOCALAPPDATA, USERPROFILE)

**Implementation**:
```rust
pub fn new(map: HashMap<String, String>) -> Self {
    let mut validated = HashMap::new();
    for (key, value) in map {
        if Self::is_disallowed(&key) {
            warn!("Skipping disallowed env var: {}", key);
            continue;
        }
        validated.insert(key, value);
    }
    Self { map: validated }
}
```

**Python Equivalent Needed**: Create similar allowlist in Python replica.

---

## Future Enhancement Opportunities

### For Goose-RS

1. **Proper Frontmatter Parser**: Use `frontmatter` crate instead of string splitting
2. **Conflict Detection**: Warn when a skill is overridden
3. **Skill Validation**: Schema validation for metadata fields
4. **Hot Reload**: Watch directories and reload on change
5. **Skill Dependencies**: Declare and resolve skill dependencies

### For Python Replica

1. **Complete MCP Protocol**: Implement resources, prompts, subscribe methods
2. **Async/Await Pattern**: Add async/await support
3. **Session ID Injection**: Track requests across sessions
4. **Security Allowlist**: Implement environment variable filtering
5. **Better Testing**: Add more edge case tests, inline tests
6. **Type Hints**: Add Python type hints throughout

---

## Conclusion

Goose-RS implements a well-designed, extensible skill system with:

- ✅ Clean separation of concerns (discovery, parsing, tooling)
- ✅ Comprehensive MCP protocol compliance
- ✅ Extensive test coverage
- ✅ Multi-directory discovery with sensible overrides
- ✅ Security-conscious design

The Python replica in `goose-skill-system` successfully captures the core concepts and should be enhanced to align with the advanced features shown above.

---

**Next Steps**: See `OPTIMIZATION_PLAN.md` for detailed improvement plan for the Python replica.
