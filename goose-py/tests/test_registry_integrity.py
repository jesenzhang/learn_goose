import sys
import os
import logging
from typing import Dict, Any

# 将项目根目录加入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 配置日志以便观察注册过程
logging.basicConfig(level=logging.INFO, format="%(name)s - %(message)s")

# --- 1. 模拟组件定义 (为了测试隔离性，我们在脚本里定义一个临时的) ---
from goose.registry import sys_registry, SystemRegistry
from goose.components import Component, register_component
from pydantic import BaseModel

class MockConfig(BaseModel):
    test_val: str = "demo"

@register_component(
    name="mock_comp",
    group="Test",
    label="Mock Component",
    description="A component for testing registry"
)
class MockComponent(Component):
    config_model = MockConfig
    async def execute(self, ctx, config, inputs):
        pass

# --- 2. 模拟工具定义 ---
from goose.toolkit import register_tool

@register_tool(name="mock_func_tool", description="Test Func")
def mock_func(x: int):
    return x * 2

# --- 测试主逻辑 ---
def test_registry_system():
    print("\n🚀 Starting Registry Integrity Test...\n")

    # TEST 1: 单例模式验证
    print("1️⃣  Testing Singleton Pattern...")
    reg1 = SystemRegistry()
    reg2 = sys_registry # import 进来的实例
    
    assert reg1 is reg2, "❌ SystemRegistry is NOT a singleton!"
    print("   ✅ Singleton check passed (id matches).")

    # TEST 2: 初始化加载验证 (Components)
    # 必须手动触发 import src.goose.components 才能运行 __init__.py 里的逻辑
    print("\n2️⃣  Testing Domain Registration (Components)...")
    import goose.components # 触发 components/__init__.py
    
    # 验证 registry.components 是否存在且是 ComponentRegistry 类型
    assert hasattr(reg1, "components"), "❌ registry.components attribute missing"
    
    # 验证是否包含我们刚才定义的 MockComponent
    # 注意：MockComponent 在本文件定义，装饰器运行时会写入 registry
    entry = reg1.components.get_entry("mock_comp")
    assert entry is not None, "❌ MockComponent not found in registry"
    assert entry.meta.definition.ui.label == "Mock Component", "❌ Metadata definition mismatch"
    print("   ✅ Component registration passed.")
    
    # 验证 export_definitions (这是 ComponentRegistry 特有的方法)
    defs = reg1.components.list_meta()
    assert isinstance(defs, list), "❌ export_definitions did not return a list"
    assert len(defs) >= 1, "❌ Definitions list is empty"
    print(f"   ✅ Export definitions working. Found {len(defs)} components.")

    # TEST 3: 初始化加载验证 (Tools)
    print("\n3️⃣  Testing Domain Registration (Tools)...")
    import goose.toolkit # 触发 toolkit/__init__.py
    
    # 验证 func tool
    tool_entry = reg1.tools.get_entry("mock_func_tool")
    assert tool_entry is not None, "❌ Function Tool not found"
    assert tool_entry.meta.source_type == "builtin"
    
    # 验证特有方法 to_openai_tools
    openai_tools = reg1.tools.to_openai_tools()
    assert len(openai_tools) >= 1
    assert openai_tools[-1]["function"]["name"] == "mock_func_tool"
    print("   ✅ Tool registration and OpenAI export passed.")

    # TEST 4: 自动注册 (Proxy) 验证
    print("\n4️⃣  Testing Auto-Registration (Proxy)...")
    # 访问一个不存在的属性，应该自动创建 BaseRegistry
    try:
        # 假设我们要注册 Prompt
        reg1.prompts.register(None) # 故意报错或者随便调个方法测试它存在
    except AttributeError:
        # 如果没有 register 方法说明不是 BaseRegistry
        assert False, "❌ registry.prompts did not auto-create BaseRegistry"
    except Exception:
        # 忽略 register(None) 的参数错误，只要没报 AttributeError 就行
        pass
        
    assert "prompts" in reg1._domains, "❌ 'prompts' not found in internal _domains"
    print("   ✅ Auto-registration (registry.prompts) passed.")

    print("\n✨ All Registry Tests Passed!")

if __name__ == "__main__":
    test_registry_system()