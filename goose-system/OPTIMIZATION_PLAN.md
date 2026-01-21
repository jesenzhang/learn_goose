# Goose Skill System - Optimization Plan

## Overview

This document outlines the optimization plan for the Python replica of the Goose-RS Agent Skill System (`goose-skill-system`).

---

## Current Status

### What Works ✅
- Skill file parsing (YAML frontmatter + Markdown body)
- Multi-directory discovery with override semantics
- `loadSkill` tool implementation
- Basic test coverage (15 tests for loader, 15 tests for client)
- Supporting files collection

### Gaps and Issues ❌

| Area | Issue | Impact |
|-------|--------|---------|
| **MCP Protocol** | Missing `list_resources`, `read_resource`, `list_prompts`, `get_prompt`, `subscribe` methods | Cannot use full MCP features |
| **Async/Await** | All methods are synchronous | No async/await patterns |
| **Session ID** | No session tracking/injection | Cannot debug cross-session requests |
| **Caching** | `_skills_cache` exists but inconsistent usage | Instructions generation may not use cache |
| **Testing** | Tests split across files, not inline | Harder to maintain and run |
| **Documentation** | ANALYSIS.md replaced with basic content | Loss of original analysis |
| **Security** | No environment variable allowlist | Potential security risks |
| **Type Hints** | Minimal type hints | Poor IDE support |

---

## Optimization Plan

### Phase 1: MCP Protocol Enhancement

**Goal**: Complete MCP protocol compliance

| Task | File | Description |
|-------|-------|-------------|
| 1.1 | `protocol.py` | Add `list_resources`, `read_resource`, `list_prompts`, `get_prompt`, `subscribe` to `McpClientTrait` |
| 1.2 | `client.py` | Implement all MCP methods in `SkillsClient` |
| 1.3 | `models.py` | Add `ListResourcesResult`, `ReadResourceResult`, `ListPromptsResult`, `GetPromptResult` dataclasses |

**Rust Reference**:
```rust
#[async_trait]
pub trait McpClientTrait: Send + Sync {
    async fn list_tools(...) -> Result<ListToolsResult, Error>;
    async fn call_tool(...) -> Result<CallToolResult, Error>;
    fn get_info(&self) -> Option<&InitializeResult>;
    async fn list_resources(...) -> Result<ListResourcesResult, Error>;
    async fn read_resource(...) -> Result<ReadResourceResult, Error>;
    async fn list_prompts(...) -> Result<ListPromptsResult, Error>;
    async fn get_prompt(...) -> Result<GetPromptResult, Error>;
    async fn subscribe(&self) -> mpsc::Receiver<ServerNotification>;
}
```

**Expected Outcome**: Full MCP compliance, compatible with any MCP client

---

### Phase 2: Async/Await Support

**Goal**: Add async/await patterns throughout the codebase

| Task | File | Description |
|-------|-------|-------------|
| 2.1 | `client.py` | Convert all public methods to `async` |
| 2.2 | `loader.py` | Add async version of discovery methods |
| 2.3 | Tests | Update tests to use `pytest-asyncio` |

**Implementation Pattern**:
```python
import asyncio
from typing import Optional

class SkillsClient:
    async def list_tools(self, next_cursor: Optional[str] = None) -> ListToolsResult:
        # ... implementation ...
        await asyncio.sleep(0)  # Yield to event loop if needed
    
    async def call_tool(self, name: str, arguments: Optional[dict] = None) -> ToolCallResult:
        # ... implementation ...
```

**Expected Outcome**: Non-blocking operations, better performance, async/await compatible

---

### Phase 3: Session ID Injection

**Goal**: Track session ID and inject into MCP requests

| Task | File | Description |
|-------|-------|-------------|
| 3.1 | `models.py` | Add `McpMeta` dataclass with `session_id` field |
| 3.2 | `client.py` | Add `_meta: Optional[McpMeta]` field |
| 3.3 | `client.py` | Implement `inject_session_id` method |
| 3.4 | `client.py` | Call `inject_session_id` before all MCP requests |

**Rust Reference**:
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

**Python Implementation**:
```python
@dataclass
class McpMeta:
    session_id: str

    def inject_into_extensions(self, extensions: dict) -> dict:
        meta = extensions.get("_meta", {})
        meta_copy = dict(meta)
        meta_copy["GOOSE-SESSION-ID"] = self.session_id
        extensions["_meta"] = meta_copy
        return extensions
```

**Expected Outcome**: Request traceability, improved debugging

---

### Phase 4: Security Enhancements

**Goal**: Implement environment variable allowlist

| Task | File | Description |
|-------|-------|-------------|
| 4.1 | `loader.py` | Add `Envs` class with `DISALLOWED_KEYS` constant |
| 4.2 | `loader.py` | Add `validate_env` method |
| 4.3 | Tests | Add tests for environment variable filtering |

**Rust Reference** (31 keys):
```rust
pub const DISALLOWED_KEYS: [&'static str; 31] = [
    "PATH", "PATHEXT", "SystemRoot", "windir",
    "LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT",
    "DYLD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS",
    "RUBYOPT", "GEM_PATH", "GEM_HOME",
    "CLASSPATH", "GO111MODULE", "GOROOT",
    "APPINIT_DLLS", "SESSIONNAME", "ComSpec",
    "TEMP", "TMP", "LOCALAPPDATA",
    "USERPROFILE", "HOMedRIVE", "HOMEPATH",
];
```

**Python Implementation**:
```python
class Envs:
    """Environment variables with security filtering."""
    
    DISALLOWED_KEYS = {
        # Binary path manipulation
        "PATH", "PATHEXT", "SystemRoot", "windir",
        # Dynamic linker hijacking
        "LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT", "LD_DEBUG",
        "LD_BIND_NOW", "LD_ASSUME_KERNEL",
        # macOS dynamic linker
        "DYLD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_FRAMEWORK_PATH",
        # Language runtimes
        "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "RUBYOPT",
        "GEM_PATH", "GEM_HOME", "CLASSPATH",
        # Compilers
        "GO111MODULE", "GOROOT",
        # Windows-specific
        "APPINIT_DLLS", "SESSIONNAME", "ComSpec",
        # Temp directories
        "TEMP", "TMP", "LOCALAPPDATA",
        # User directories
        "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    }
    
    def __init__(self, env_map: dict[str, str]):
        validated = {}
        for key, value in env_map.items():
            if key in self.DISALLOWED_KEYS:
                print(f"Warning: Skipping disallowed env var: {key}")
                continue
            validated[key] = value
        self.map = validated
```

**Expected Outcome**: Improved security posture for code execution extensions

---

### Phase 5: Testing Enhancement

**Goal**: Inline tests, improve coverage

| Task | File | Description |
|-------|-------|-------------|
| 5.1 | `loader.py` | Add inline tests at module level (14 tests) |
| 5.2 | `client.py` | Add inline tests at module level (8 tests) |
| 5.3 | `models.py` | Add inline tests for dataclasses (5 tests) |
| 5.4 | Tests | Update to use inline test pattern |

**Rust Pattern**:
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_parse_frontmatter() {
        let content = r#"---
name: test-skill
description: A test skill
---

# Test Skill
This is body.
"#;
        let (metadata, body) = SkillsClient::parse_frontmatter(content).unwrap();
        assert_eq!(metadata.name, "test-skill");
        assert_eq!(metadata.description, "A test skill");
        assert!(body.contains("# Test Skill"));
        assert!(body.contains("This is body."));
    }
    
    #[test]
    fn test_discover_skills_from_multiple_directories() {
        // ... test implementation
    }
}
```

**Python Pattern**:
```python
# Inline tests at module level
def test_parse_frontmatter_valid() -> None:
    """Test parsing valid frontmatter."""
    content = '''---
name: test-skill
description: A test skill
---

# Test Skill

This is body.
'''
    metadata, body = SkillLoader.parse_frontmatter(content)
    assert metadata.name == "test-skill"
    assert metadata.description == "A test skill"
    assert "# Test Skill" in body

def test_discover_skills_multiple_dirs() -> None:
    """Test discovery from multiple directories."""
    # ... test implementation
```

**Expected Outcome**: Easier test maintenance, better CI/CD support

---

### Phase 6: Documentation Improvement

**Goal**: Restore and enhance analysis documentation

| Task | File | Description |
|-------|-------|-------------|
| 6.1 | `COMPLETE_ANALYSIS.md` | Create comprehensive analysis (done) |
| 6.2 | `README.md` | Update with usage examples and API reference |
| 6.3 | `OPTIMIZATION_PLAN.md` | Create this file |
| 6.4 | `CHANGELOG.md` | Document changes and improvements |

**Expected Outcome**: Better documentation for users and contributors

---

### Phase 7: Example Skills

**Goal**: Add diverse example skills

| Skill | Directory | Description |
|--------|-----------|-------------|
| `git-operations` | `examples/skills/git-operations/` | Git workflow skills |
| `web-search` | `examples/skills/web-search/` | Web search capabilities |
| `code-runner` | `examples/skills/code-runner/` | Code execution patterns |
| `test-helper` | `examples/skills/test-helper/` | Testing utilities |

**Expected Outcome**: Better demonstration of capabilities

---

## Implementation Order

### Priority 1: Critical (Must Have)
1. ✅ Complete analysis document (`COMPLETE_ANALYSIS.md`)
2. ⚠️ MCP protocol completion (Phase 1)
3. ⚠️ Async/await support (Phase 2)
4. ⚠️ Session ID injection (Phase 3)
5. ⚠️ Security allowlist (Phase 4)

### Priority 2: Important (Should Have)
6. Testing enhancement (Phase 5)
7. Documentation improvement (Phase 6)
8. Example skills (Phase 7)

### Priority 3: Nice to Have
9. Hot reload capability (watch directories)
10. Skill dependencies and versioning
11. Conflict detection and warnings
12. Skill marketplace simulator

---

## Success Criteria

### Completion Checklist

- [ ] All MCP protocol methods implemented
- [ ] Async/await patterns throughout
- [ ] Session ID tracking and injection
- [ ] Environment variable allowlist implemented
- [ ] 22+ inline tests (matching Rust coverage)
- [ ] Comprehensive documentation
- [ ] 3+ example skills
- [ ] All tests passing
- [ ] Type hints throughout
- [ ] No LSP errors

### Metrics

| Metric | Current | Target |
|---------|---------|--------|
| MCP methods | 3/7 | 7/7 |
| Async support | 0% | 100% |
| Inline tests | 0% | 100% |
| Documentation quality | Basic | Comprehensive |
| Example skills | 1 | 4+ |

---

## Next Steps

1. Execute Phase 1 (MCP Protocol) first
2. Test Phase 1 before moving to Phase 2
3. Incrementally implement each phase
4. Run full test suite after each phase
5. Update documentation continuously

---

**Document Status**: ✅ Complete
**Next Action**: Begin Phase 1 implementation
