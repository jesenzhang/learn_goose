"""
Skill Loader - Discovery, registration, and management of skills.
"""

import os
import sys
import importlib.util
import inspect
import logging
import frontmatter  # pip install python-frontmatter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable, Type

from .base import SkillBase, SkillType, ToolMetadata
from .generic import GenericSkill
from .config import SkillConfig, SkillsConfig, ToolConfig

logger = logging.getLogger(__name__)

class SkillLoader:
    """
    Central manager for skill discovery, loading, and runtime retrieval.
    """

    def __init__(
        self,
        skills_dir: str = "agent_skills",
        skills_config: Optional[SkillsConfig] = None, 
        global_sensitive_tools: Optional[Set[str]] = None,
    ):
        self.skills_dir = Path(skills_dir)
        # 如果没传配置，就用空的默认值
        self.skills_config = skills_config or SkillsConfig({})
        self.global_sensitive_tools = global_sensitive_tools or set()

        # Registry
        self._skills: Dict[str, SkillBase] = {}           # skill_id -> SkillInstance
        self._global_tools: Dict[str, ToolMetadata] = {}  # tool_name -> Metadata (Global only)
        self._skill_tools: Dict[str, Dict[str, ToolMetadata]] = {} # skill_id -> {tool_name: Metadata}

        # Built-in tools registry
        self._builtin_tools: Dict[str, Callable] = {}

        # Track per-skill sensitive tools from config
        self._skill_sensitive_tools: Dict[str, Set[str]] = {}

        # Register builtin skill tools (activate_skill, exit_skill)
        self._register_builtin_skill_tools()

        self.load_from_directory()

    # =========================================================================
    # Loading Logic
    # =========================================================================

    def load_from_directory(self) -> None:
        """Scan and load all skills from the configured directory."""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return

        logger.info(f"📂 Scanning skills in '{self.skills_dir}'...")

        for skill_path in self.skills_dir.iterdir():
            if not skill_path.is_dir() or skill_path.name.startswith(('.', '_')):
                continue
            skill_id = skill_path.name
            try:
                self._load_single_skill(skill_id, skill_path)
            except Exception as e:
                logger.error(f"❌ Error loading skill '{skill_id}': {e}", exc_info=True)

        logger.info(f"✅ Loaded {len(self._skills)} skills.")
        for skill_id, skill in self._skills.items():
            logger.info(f"✅ Loaded skill '{skill_id}': {skill.name}")

    def _load_single_skill(self, skill_id: str, path: Path) -> None:
        """Load a specific skill folder."""
        # 1. Check skills_config for enabled/disabled status
        specific_config:SkillConfig = self.skills_config.get(skill_id)
        # 策略：显式启用 (enabled=true) 才加载
        if not specific_config or (specific_config and specific_config.enabled is False):
            logger.info(f"⏭️  Skipping disabled skill '{skill_id}'")
            return

        # 2. Parse Metadata (SKILL.md) - 这是 Layer 1 (本质属性)
        meta = self._load_metadata(path)
        
        # 3. 决定最终属性 (Layer 2 覆盖 Layer 1)
        # 名称优先用文件夹名或配置名，最后用 markdown 里的
        skill_name = meta.get("name", skill_id)
        
        # 描述：配置里的描述 > SKILL.md 的描述
        description =  meta.get("description", f"Skill {skill_name}")
        if specific_config and specific_config.description:
            description = specific_config.description

        # Determine Type: 'global' or 'contextual' (default)
        # 3. 决定 Skill Type (关键修改)
        # 优先级：Config (Layer 2) > Metadata (Layer 1) > Default
        # A. 尝试从配置中获取
        config_mode = specific_config.mode.lower() if specific_config and specific_config.mode else None
        # B. 尝试从 SKILL.md 获取
        meta_mode = meta.get("type", "contextual").lower()
        # C. 决策
        final_mode_str = config_mode or meta_mode
        # 转换为枚举
        skill_type = SkillType.GLOBAL if final_mode_str == "global" else SkillType.CONTEXTUAL

        # 3. Scan for Functions (scripts/*.py AND impl.py)
        functions = self._scan_functions(skill_id, path)

        # 4. Try Loading Class (impl.py)
        skill_instance = self._try_load_skill_class(skill_id, path)

        if skill_instance:
            # === Class-based Skill ===
            # Override instance properties with SKILL.md metadata
            skill_instance.name = skill_name
            skill_instance.description = description
            skill_instance.skill_type = skill_type

            # [新增] 技能中文显示名称：配置覆盖 > 代码定义 > SKILL.md
            skill_label = None
            if specific_config and specific_config.label:
                skill_label = specific_config.label
            elif skill_instance.label:
                skill_label = skill_instance.label
            if skill_label:
                skill_instance.label = skill_label

            # Attach loose functions found in scripts/ to the class instance
            self._attach_functions_to_instance(skill_instance, functions)
        else:
            # === Function-based Skill ===
            if not functions:
                logger.debug(f"Skipping '{skill_id}': No class and no scripts found.")
                return

            # 从配置中获取 label
            skill_label = None
            if specific_config and specific_config.label:
                skill_label = specific_config.label

            skill_instance = GenericSkill(
                name=skill_name,
                description=description,
                functions=functions,
                label=skill_label
            )
            skill_instance.skill_type = skill_type

        # 5. Filter Allowed Tools (Security)
        allowed = meta.get("allowed_tools") or meta.get("allowed-tools")
        if allowed:
            self._filter_allowed_tools(skill_instance, allowed)

        # 6. 工具配置覆盖（新增）
        # 从技能配置中获取工具级别的覆盖配置
        if specific_config and specific_config.tools_config:
            self._apply_tools_config(skill_instance, specific_config.tools_config)

        # 7. 敏感工具合并策略 (关键修改)
        # 获取 Layer 2: 全局配置定义的 sensitive
        config_sensitive = set(specific_config.sensitive_tools) if specific_config else set()

        # 获取 Layer 3: 全局安全策略
        global_sensitive = self.global_sensitive_tools

        # 应用到 Skill 实例
        # 我们需要遍历 skill 里的所有 tool，更新它们的 metadata
        for tool_name, tool_meta in skill_instance._tools.items():
            is_sensitive = (
                tool_meta.is_sensitive or   # Layer 1 (Code/Decorator)
                tool_name in config_sensitive or # Layer 2 (App Config)
                tool_name in global_sensitive    # Layer 3 (Global Security)
            )
            tool_meta.is_sensitive = is_sensitive

            if is_sensitive:
                logger.info(f"🔒 Tool '{tool_name}' marked as sensitive.")

        # 8. Register
        self._register_skill_instance(skill_instance)

    def _load_metadata(self, path: Path) -> Dict[str, Any]:
        """Read SKILL.md frontmatter."""
        md_path = path / "SKILL.md"
        if md_path.exists():
            try:
                return frontmatter.load(md_path).metadata
            except Exception as e:
                logger.warning(f"Metadata parse error in {path.name}: {e}")
        return {}

    def _import_funcs_from_file(self, name: str, path: Path) -> Dict[str, Callable]:
        """Import module and return public functions."""
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if not spec or not spec.loader:
                return {}
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            return {
                n: f for n, f in inspect.getmembers(module, inspect.isfunction)
                if not n.startswith("_") and f.__module__ == module.__name__
            }
        except Exception as e:
            logger.warning(f"Import error {path}: {e}")
            return {}

    def _check_dependencies(self, meta: Dict[str, Any], skill_id: str):
        """Log warnings if dependencies are required."""
        # Claude Skills often list PyPI requirements
        deps = meta.get("requirements") or meta.get("dependencies")
        if deps:
            logger.info(f"ℹ️  Skill '{skill_id}' lists dependencies: {deps}")
            
            # 可以在这里做自动 pip install (慎用) 或仅检查 import
    # -------------------------------------------------------------------------
    # FIXED: Package-based Loading (Resolves Relative Import Issues)
    # -------------------------------------------------------------------------

    def _prepare_sys_path(self, path: Path) -> str:
        """Helper to inject parent dir into sys.path."""
        # path is ".../agent_skills/skill_name"
        # we need ".../agent_skills" in sys.path
        skills_root = path.parent.resolve()
        str_root = str(skills_root)
        if str_root not in sys.path:
            sys.path.insert(0, str_root)
        return str_root

    def _try_load_skill_class(self, skill_id: str, path: Path) -> Optional[SkillBase]:
        """Attempt to instantiate SkillBase from impl.py using import_module."""
        impl_path = path / "impl.py"
        if not impl_path.exists():
            return None

        self._prepare_sys_path(path)

        try:
            # e.g. "google_conductor.impl"
            module_name = f"{skill_id}.impl"
            
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            for item_name in dir(module):
                item = getattr(module, item_name)
                if (inspect.isclass(item) and 
                    issubclass(item, SkillBase) and 
                    item is not SkillBase and 
                    item is not GenericSkill):
                    return item()
        except Exception as e:
            logger.error(f"❌ Class load error in {skill_id}: {e}", exc_info=True)
        
        return None

    
    def _scan_functions(self, skill_id: str, path: Path) -> Dict[str, Callable]:
        """Scan impl.py using package loading."""
        collected_funcs = {}
        
        # 1. Scan scripts/ (Keep legacy file-based loading for scripts if needed)
        scripts_dir = path / "scripts"
        if scripts_dir.exists():
            # ... (保持原有的 scripts 扫描逻辑不变，或者也尝试改为包加载) ...
            pass 

        # 2. Scan impl.py (FIXED)
        impl_path = path / "impl.py"
        if impl_path.exists():
            self._prepare_sys_path(path)
            try:
                module_name = f"{skill_id}.impl"
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    module = importlib.import_module(module_name)
                
                # Filter functions defined in this module only
                for n, f in inspect.getmembers(module, inspect.isfunction):
                    if not n.startswith("_") and f.__module__ == module.__name__:
                        collected_funcs[n] = f
            except Exception as e:
                logger.warning(f"⚠️  Error scanning functions in '{impl_path}': {e}")

        return collected_funcs
    
    def _attach_functions_to_instance(self, instance: SkillBase, functions: Dict[str, Callable]):
        """Inject scripts/*.py functions into a SkillBase instance."""
        for name, func in functions.items():
            if instance.has_tool(name):
                continue # Class method takes precedence

            # Use GenericSkill statics to generate metadata & wrapper
            params = GenericSkill.extract_params(func)
            handler = GenericSkill.make_handler(func)
            doc = func.__doc__ or f"Tool: {name}"

            meta = ToolMetadata(
                name=name,
                description=doc,
                parameters=params,
                handler=handler
            )
            # Manually inject into the instance's tool registry
            instance._tools[name] = meta

    def _filter_allowed_tools(self, skill: SkillBase, allowed: List[str]):
        """Remove tools not in the allowed list."""
        allowed_set = set(allowed)
        # Only keep tools that are in the allowed set
        skill._tools = {k: v for k, v in skill._tools.items() if k in allowed_set}

    def _apply_tools_config(self, skill: SkillBase, tools_config: Dict[str, ToolConfig]):
        """
        应用工具级别配置覆盖。

        Args:
            skill: 技能实例
            tools_config: 工具配置映射 {tool_name: ToolConfig}
        """
        for tool_name, tool_meta in skill._tools.items():
            if tool_name in tools_config:
                config = tools_config[tool_name]
                updated_fields = []

                # 覆盖 label
                if config.label:
                    tool_meta.label = config.label
                    updated_fields.append(f"label={config.label}")

                # 覆盖 description
                if config.description:
                    tool_meta.description = config.description
                    updated_fields.append(f"description")

                # 覆盖 sensitive（注意：这个会在后续的敏感工具合并策略中再次处理）
                if config.sensitive is not None:
                    tool_meta.is_sensitive = config.sensitive
                    updated_fields.append(f"sensitive={config.sensitive}")

                if updated_fields:
                    logger.info(f"🏷️  Tool '{tool_name}' in skill '{skill.name}' updated: {', '.join(updated_fields)}")

    def _register_skill_instance(self, skill: SkillBase):
        """Final registration step."""
        if skill.name in self._skills:
            logger.warning(f"⚠️  Overwriting skill: {skill.name}")

        self._skills[skill.name] = skill

        # Index tools
        tools = skill.get_tools()
        self._skill_tools[skill.name] = {t.name: t for t in tools}

        # If global, add to global index
        if skill.skill_type == SkillType.GLOBAL:
            for tool in tools:
                self._global_tools[tool.name] = tool

        # Log loaded tools (changed from debug to info)
        tool_names = [t.name for t in tools]
        skill_type_emoji = "🌐" if skill.skill_type == SkillType.GLOBAL else "🎯"
        logger.info(f"{skill_type_emoji} Registered '{skill.name}' with {len(tools)} tool(s): {tool_names}")

    # =========================================================================
    # Runtime: Tool Retrieval
    # =========================================================================

    def get_tool_func(self, tool_name: str) -> Optional[Callable]:
        """
        Find the callable for a tool name.
        Order: Built-in -> Global -> Any Skill (Flattened).
        """
        # 1. Built-in
        if tool_name in self._builtin_tools:
            return self._builtin_tools[tool_name]
        
        # 2. Global
        if tool_name in self._global_tools:
            return self._global_tools[tool_name].handler
        
        # 3. Search all skills (Flattened access)
        for tools in self._skill_tools.values():
            if tool_name in tools:
                return tools[tool_name].handler
        
        return None

    def is_sensitive(self, tool_name: str) -> bool:
        """
        Check if tool requires human approval.

        Priority order:
        1. Per-skill sensitive_tools from config
        2. Tool metadata is_sensitive flag
        3. Global sensitive_tools set (fallback)
        """
        # 1. Check per-skill sensitive tools configuration
        for skill_id, sensitive_set in self._skill_sensitive_tools.items():
            if tool_name in sensitive_set:
                return True

        # 2. Check metadata
        tool = None
        if tool_name in self._global_tools:
            tool = self._global_tools[tool_name]
        else:
            for tools in self._skill_tools.values():
                if tool_name in tools:
                    tool = tools[tool_name]
                    break

        if tool and tool.is_sensitive:
            return True

        # 3. Global fallback
        if tool_name in self.global_sensitive_tools:
            return True

        return False

    def get_tool_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """
        获取工具的完整 metadata（包括 label）

        Args:
            tool_name: 工具名称

        Returns:
            ToolMetadata 对象，包含 name, description, label 等信息
        """
        # 1. Global tools
        if tool_name in self._global_tools:
            return self._global_tools[tool_name]

        # 2. Skill tools
        for tools in self._skill_tools.values():
            if tool_name in tools:
                return tools[tool_name]

        return None

    # =========================================================================
    # Runtime: Context & Schema
    # =========================================================================

    def get_all_tools_schema(self, active_skill: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generate OpenAI Tool Schemas based on current context.

        Args:
            active_skill: 当前激活的技能
        """
        schemas = []
        added = set()

        def add(meta: ToolMetadata):
            if meta.name not in added:
                schemas.append(meta.to_schema())
                added.add(meta.name)

        # 1. Routing Tools (Dynamic)
        routable_skills = [
            name for name, sk in self._skills.items()
            if sk.skill_type == SkillType.CONTEXTUAL
        ]

        if routable_skills:
            schemas.append({
                "type": "function",
                "function": {
                    "name": "activate_skill",
                    "description": f"Switch context to a specialized skill. Available: {', '.join(routable_skills)}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {"type": "string", "enum": routable_skills}
                        },
                        "required": ["skill_name"]
                    }
                }
            })

        if active_skill:
            schemas.append({
                "type": "function",
                "function": {
                    "name": "exit_skill",
                    "description": "Exit the current skill and return to main routing mode.",
                    "parameters": {"type": "object", "properties": {}}
                }
            })

        # 2. Global Tools
        logger.debug(f"🔧 Adding {len(self._global_tools)} global tools")
        for tool in self._global_tools.values():
            add(tool)

        # 3. Active Skill Tools
        if active_skill and active_skill in self._skills:
            skill = self._skills[active_skill]
            logger.info(f"🔧 Active skill '{active_skill}' type={skill.skill_type}")
            if skill.skill_type == SkillType.CONTEXTUAL:
                for tool in skill.get_tools():
                    add(tool)

        return schemas

    def get_context_prompt(self, active_skill: Optional[str] = None) -> str:
        """
        Generate the System Prompt based on current context.
        """
        parts = []

        # 1. Global Skills Descriptions
        global_skills = [s for s in self._skills.values() if s.skill_type == SkillType.GLOBAL]
        if global_skills:
            parts.append("### Global Capabilities")
            for sk in global_skills:
                parts.append(sk.get_system_prompt())

        # 2. Active Context or Routing Logic
        if active_skill and active_skill in self._skills:
            # === Active Mode ===
            skill = self._skills[active_skill]
            parts.append(f"\n=== 🛡️ ACTIVE SKILL: {skill.name} ===")
            parts.append(skill.get_system_prompt())
            parts.append("\n(Constraint: Focus ONLY on this skill's domain. Use 'exit_skill' when done.)")
        else:
            # === Routing Mode ===
            routable = [s for s in self._skills.values() if s.skill_type == SkillType.CONTEXTUAL]
            if routable:
                parts.append("\n=== 🧭 ROUTING MODE ===")
                parts.append("Available specialized skills:")
                for sk in routable:
                    parts.append(f"- {sk.name}: {sk.description}")
                parts.append("\nInstruction: If the user request matches a skill, use 'activate_skill'.")

        return "\n".join(parts)

    def get_skill(self, name: str) -> Optional[SkillBase]:
        return self._skills.get(name)

    def get_available_skills_list(self) -> List[str]:
        return list(self._skills.keys())

    def register_builtin_tool(self, name: str, func: Callable):
        self._builtin_tools[name] = func

    def _register_builtin_skill_tools(self):
        """
        Register builtin skill-related tools (activate_skill, exit_skill).

        These tools are dynamically added to the tool schema but need actual
        handler functions registered in _builtin_tools.
        """
        def activate_skill(skill_name: str, _state=None) -> str:
            """Activate a contextual skill by name."""
            if _state is not None:
                _state.active_skill = skill_name
                return f"Activated skill: {skill_name}"
            return f"Error: Cannot activate skill - no state context"

        def exit_skill(_state=None) -> str:
            """Exit the current active skill and return to routing mode."""
            if _state is not None:
                current = _state.active_skill
                _state.active_skill = None
                return f"Exited skill: {current}" if current else "No active skill to exit"
            return "Error: Cannot exit skill - no state context"

        self._builtin_tools["activate_skill"] = activate_skill
        self._builtin_tools["exit_skill"] = exit_skill

        logger.debug("Registered builtin skill tools: activate_skill, exit_skill")

    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------

    async def unload_skill(self, skill_name: str) -> bool:
        """
        Unload a skill dynamically.
        1. Calls on_deactivate (cleanup).
        2. Removes from registries.
        3. Removes from sys.modules (Hot-reload support).
        """
        if skill_name not in self._skills:
            logger.warning(f"Skill '{skill_name}' not found, cannot unload.")
            return False

        skill = self._skills[skill_name]
        logger.info(f"🔻 Unloading skill: {skill_name}")

        # 1. Resource Cleanup (Async hook)
        # 假设 GenericSkill 也有 on_deactivate 即使是空的
        if hasattr(skill, 'on_deactivate'):
            try:
                # 注意：这里需要传入 context，如果没有 ctx，可能需要调整设计
                # 或者让 on_deactivate 接受 Optional[Context]
                if inspect.iscoroutinefunction(skill.on_deactivate):
                    await skill.on_deactivate(None) 
                else:
                    skill.on_deactivate(None)
            except Exception as e:
                logger.error(f"Error executing on_deactivate for {skill_name}: {e}")

        # 2. Remove from Global Tools Registry
        if skill.skill_type == SkillType.GLOBAL:
            for tool_name in skill._tools.keys():
                self._global_tools.pop(tool_name, None)

        # 3. Remove from Skill Tools Registry
        self._skill_tools.pop(skill_name, None)

        # 4. Remove from Main Registry
        self._skills.pop(skill_name, None)

        # 5. Clean sys.modules (Optional but good for Hot Reload)
        # 这能让下次 import 时重新读取文件
        to_remove = [m for m in sys.modules if m.startswith(f"{skill_name}.")]
        if skill_name in sys.modules:
            to_remove.append(skill_name)
        
        for m in to_remove:
            del sys.modules[m]

        logger.info(f"✅ Skill '{skill_name}' unloaded.")
        return True

    async def reload_skill(self, skill_name: str):
        """Hot reload a specific skill."""
        await self.unload_skill(skill_name)
        
        # Re-scan specifically this folder
        # 注意：你需要实现 _find_path_by_name 或者约定 skill_id == folder_name
        skill_path = self.skills_dir / skill_name
        if skill_path.exists():
            self._load_single_skill(skill_name, skill_path)
            return True
        return False