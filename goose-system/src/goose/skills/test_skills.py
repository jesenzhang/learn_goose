"""
Test Suite for Goose System Skills Implementation

基于 Agent Skills 运行时验收测试手册设计

Reference: Agent Skills 运行时验收测试手册
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

# 添加 goose-system 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from goose.skills import (
    SkillLoader,
    SkillRegistry,
    ProgressiveDisclosureStateMachine,
    SkillState,
    ToolInterceptor,
    ToolPermission,
    ResourceLoader,
    ResourceValidator,
    SandboxIntegrator,
    ExecutionResult,
    StandardPathDiscovery,
    ConfigurablePathDiscovery,
    Skill,
    SkillMetadata,
    parse_skill_metadata,
)


class MockSkillGenerator:
    """
    测试用技能生成器
    
    Reference: 验收测试手册 - 测试环境准备
    """
    
    def __init__(self):
        self.test_dir = tempfile.mkdtemp()
        self.skills_root = Path(self.test_dir) / ".claude" / "skills"
        self.skills_root.mkdir(parents=True)
    
    def create_skill(
        self,
        folder_name: str,
        yaml_content: Dict[str, Any],
        readme_body: str,
        script_files: Optional[Dict[str, str]] = None
    ) -> Path:
        """创建测试技能"""
        skill_path = self.skills_root / folder_name
        skill_path.mkdir()
        
        # 创建 SKILL.md
        skill_file = skill_path / "SKILL.md"
        content = "---\n"
        for key, value in yaml_content.items():
            content += f"{key}: {value}\n"
        content += f"---\n{readme_body}"
        skill_file.write_text(content, encoding="utf-8")
        
        # 创建脚本
        if script_files:
            scripts_dir = skill_path / "scripts"
            scripts_dir.mkdir()
            for fname, fcontent in script_files.items():
                (scripts_dir / fname).write_text(fcontent, encoding="utf-8")
        
        return skill_path
    
    def cleanup(self):
        """清理测试目录"""
        shutil.rmtree(self.test_dir)


# ============================================================================
# 测试组 1：物理层解析验证 (Discovery & Parsing)
# ============================================================================

class TestDiscovery:
    """测试技能发现"""
    
    def __init__(self):
        self.mock_gen = MockSkillGenerator()
        self.registry = SkillRegistry()
    
    def cleanup(self):
        self.mock_gen.cleanup()
    
    def test_valid_skill_loading(self):
        """TC-01: 验证标准技能的加载"""
        self.mock_gen.create_skill(
            folder_name="data-cruncher",
            yaml_content={
                "name": "data-cruncher",
                "description": "Process CSV files",
                "allowed-tools": ["Read", "Grep"]
            },
            readme_body="# Instructions\nRun script."
        )
        
        loader = SkillLoader()
        skills = loader.load_skills_from_directory(str(self.mock_gen.skills_root))
        
        assert len(skills) == 1
        assert skills[0].name == "data-cruncher"
        assert "Read" in skills[0].metadata.allowed_tools
        print("[PASS] TC-01: Valid skill loading passed")
    
    def test_invalid_yaml_rejection(self):
        """TC-02: 验证系统是否拒绝无效 YAML"""
        skill_path = self.mock_gen.skills_root / "broken-skill"
        skill_path.mkdir()
        
        # YAML 禁止 Tab，使用无效语法
        with open(skill_path / "SKILL.md", "w") as f:
            f.write("---\nname: broken\n  tab_error: true\n---\n")
        
        loader = SkillLoader()
        skills = loader.load_skills_from_directory(str(self.mock_gen.skills_root))
        
        # 应该跳过无效技能
        skill_names = [s.name for s in skills]
        assert "broken-skill" not in skill_names
        print("[PASS] TC-02: Invalid YAML rejection passed")
    
    def test_naming_convention(self):
        """TC-03: 验证命名规范"""
        # kebab-case 验证
        name = "valid-skill-name"
        result = parse_skill_metadata(
            f"""---
name: {name}
description: Test
---
""",
            "test.md"
        )
        assert result is not None
        print("[PASS] TC-03: Naming convention passed")


# ============================================================================
# 测试组 2：渐进式披露逻辑 (Progressive Disclosure Logic)
# ============================================================================

class TestProgressiveDisclosure:
    """测试渐进式披露"""
    
    def __init__(self):
        self.mock_gen = MockSkillGenerator()
    
    def cleanup(self):
        self.mock_gen.cleanup()
    
    def test_l1_metadata_only(self):
        """TC-04: 验证初始状态仅加载元数据"""
        # 创建技能
        self.mock_gen.create_skill(
            folder_name="heavy-skill",
            yaml_content={"name": "heavy-skill", "description": "Complex logic"},
            readme_body="VERY LONG INSTRUCTIONS " * 100
        )
        
        loader = SkillLoader()
        skills = loader.load_skills_from_directory(str(self.mock_gen.skills_root))
        
        state_machine = ProgressiveDisclosureStateMachine()
        
        # 获取 L1 提示
        metadata_list = [s.to_metadata_dict() for s in skills]
        l1_prompt = state_machine.get_awareness_prompt(metadata_list)
        
        # 包含描述
        assert "Complex logic" in l1_prompt
        # 不包含完整指令
        assert "VERY LONG INSTRUCTIONS" not in l1_prompt
        print("[PASS] TC-04: L1 metadata only passed")
    
    def test_l2_activation(self):
        """TC-05: 验证激活后加载完整指令"""
        self.mock_gen.create_skill(
            folder_name="test-skill",
            yaml_content={"name": "test-skill", "description": "Test"},
            readme_body="FULL INSTRUCTIONS HERE"
        )
        
        loader = SkillLoader()
        skills = loader.load_skills_from_directory(str(self.mock_gen.skills_root))
        
        state_machine = ProgressiveDisclosureStateMachine()
        
        # 激活技能
        skill = next(s for s in skills if s.name == "test-skill")
        state_machine.activate_skill(skill.name, skill.content)
        
        # 检查激活状态
        assert skill.name in state_machine.active_skills
        assert state_machine.current_state == SkillState.ACTIVATION
        
        # 获取 L2 内容
        l2_content = state_machine.get_activation_content(skill.name)
        assert "FULL INSTRUCTIONS HERE" in l2_content
        print("[PASS] TC-05: L2 activation passed")


# ============================================================================
# 测试组 3：工具拦截 (Tool Interceptor)
# ============================================================================

class TestToolInterceptor:
    """测试工具拦截"""
    
    def __init__(self):
        self.interceptor = ToolInterceptor()
    
    def cleanup(self):
        pass
    
    def test_tool_blocking(self):
        """TC-07: 验证非白名单工具被拦截"""
        # 注册技能允许的工具
        self.interceptor.register_skill_tools("test-skill", ["Read", "Grep"])
        
        # 检查允许的工具
        permission = self.interceptor.check_permission("Read", ["test-skill"])
        assert permission.allowed is True
        
        # 检查未允许的工具
        permission = self.interceptor.check_permission("Write", ["test-skill"])
        assert permission.allowed is False
        assert "not in allowed-tools" in permission.reason
        print("[PASS] TC-07: Tool blocking passed")
    
    def test_global_blocking(self):
        """验证全局禁止的工具"""
        # 检查全局禁止的工具
        permission = self.interceptor.check_permission("Bash", [])
        assert permission.allowed is False
        assert "globally blocked" in permission.reason
        print("[PASS] Global tool blocking passed")


# ============================================================================
# 测试组 4：资源加载 (Resource Loader)
# ============================================================================

class TestResourceLoader:
    """测试资源加载"""
    
    def __init__(self):
        self.mock_gen = MockSkillGenerator()
    
    def cleanup(self):
        self.mock_gen.cleanup()
    
    def test_requirements_parsing(self):
        """测试 requirements.txt 解析"""
        skill_path = self.mock_gen.create_skill(
            folder_name="test-req",
            yaml_content={"name": "test-req", "description": "Test"},
            readme_body="# Test"
        )
        
        # 创建 requirements.txt
        req_file = skill_path / "requirements.txt"
        req_file.write_text("requests==2.28.0\nnumpy>=1.21\n# comment\npandas")
        
        loader = ResourceLoader(skill_path)
        requirements = loader.parse_requirements()
        
        assert "requests" in requirements
        assert "numpy" in requirements
        assert "pandas" in requirements
        print("[PASS] Requirements parsing passed")
    
    def test_scripts_discovery(self):
        """测试脚本发现"""
        skill_path = self.mock_gen.create_skill(
            folder_name="test-scripts",
            yaml_content={"name": "test-scripts", "description": "Test"},
            readme_body="# Test",
            script_files={"helper.py": "print('hello')", "util.py": "print('world')"}
        )
        
        loader = ResourceLoader(skill_path)
        scripts = loader.get_scripts()
        
        assert "helper.py" in scripts
        assert "util.py" in scripts
        print("[PASS] Scripts discovery passed")


# ============================================================================
# 测试组 5：沙箱执行 (Sandbox)
# ============================================================================

class TestSandbox:
    """测试沙箱执行"""
    
    def __init__(self):
        self.sandbox = SandboxIntegrator()
    
    def cleanup(self):
        pass
    
    def test_script_execution(self):
        """测试脚本执行"""
        # 创建临时脚本
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('print("Hello from sandbox!")')
            script_path = Path(f.name)
        
        try:
            result = self.sandbox.execute_script(script_path)
            
            assert result.success is True
            assert "Hello from sandbox!" in result.stdout
            print("[PASS] Script execution passed")
        finally:
            script_path.unlink()
    
    def test_output_collection(self):
        """测试输出收集"""
        # 创建生成文件的脚本
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
import json
with open("output.json", "w") as f:
    json.dump({"test": "data"}, f)
print("Output created")
''')
            script_path = Path(f.name)
        
        try:
            result = self.sandbox.execute_script(script_path)
            
            assert result.success is True
            assert "output.json" in result.output_files
            print("[PASS] Output collection passed")
        finally:
            script_path.unlink()


# ============================================================================
# 测试组 6：路径发现 (Path Discovery)
# ============================================================================

class TestPathDiscovery:
    """测试路径发现"""
    
    def cleanup(self):
        pass
    
    def test_standard_paths(self):
        """测试标准路径发现"""
        discovery = StandardPathDiscovery()
        result = discovery.discover()
        
        # 应该有用户级路径
        user_path = result.get_path("user")
        # 可能存在也可能不存在，取决于测试环境
        
        print(f"[PASS] Standard paths discovery: user={user_path}")
    
    def test_priority_order(self):
        """测试优先级顺序"""
        discovery = StandardPathDiscovery()
        result = discovery.discover()
        
        # 优先级列表应该按优先级从低到高排序
        assert result.priority_order == ["user"] or "user" in result.priority_order
        print("[PASS] Priority order passed")


# ============================================================================
# 运行所有测试
# ============================================================================

def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Goose System Skills - Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        ("Discovery & Parsing", TestDiscovery),
        ("Progressive Disclosure", TestProgressiveDisclosure),
        ("Tool Interceptor", TestToolInterceptor),
        ("Resource Loader", TestResourceLoader),
        ("Sandbox", TestSandbox),
        ("Path Discovery", TestPathDiscovery),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_class in tests:
        print(f"\n--- {name} ---")
        try:
            instance = test_class()
            for method_name in dir(instance):
                if method_name.startswith("test_"):
                    try:
                        getattr(instance, method_name)()
                        passed += 1
                    except AssertionError as e:
                        print(f"[FAIL] {method_name}: {e}")
                        failed += 1
                    except Exception as e:
                        print(f"[FAIL] {method_name}: {e}")
                        failed += 1
            instance.cleanup()
        except Exception as e:
            print(f"[FAIL] {name}: Setup failed - {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
