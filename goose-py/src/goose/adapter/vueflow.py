import uuid
import json
import logging
from typing import Dict, Any, List, Optional, Union
from goose.types import NodeTypes, DataType, TypeInfo
from goose.workflow.protocol import WorkflowDefinition, NodeConfig, EdgeConfig
from goose.adapter.base import BaseWorkflowAdapter
from goose.registry import sys_registry
from goose.utils.type_converter import TypeConverter

logger = logging.getLogger("goose.adapter.vueflow")

# --- 1. 类型映射表 (Frontend Type -> Backend NodeType) ---
NODE_TYPE_MAP = {
    "customInput": NodeTypes.ENTRY,
    "customOutput": NodeTypes.EXIT,
    "llm": NodeTypes.LLM,
    "text-process": "text_processor",
    "knowledge": "knowledge_retriever",
    "code": NodeTypes.CODE_RUNNER,
    "plugin": NodeTypes.PLUGIN,
    "httpRequest": NodeTypes.HTTP_REQUESTER,
    "condition": "switch",  # Selector
    "loop": "loop",
    "batch": "batch",
    "variable": "variable_assigner",
}

BASE_TYPE_MAPPING = {
    "string": DataType.STRING,
    "integer": DataType.INTEGER,
    "int": DataType.INTEGER,
    "number": DataType.NUMBER,
    "float": DataType.NUMBER,
    "boolean": DataType.BOOLEAN,
    "bool": DataType.BOOLEAN,
    "object": DataType.OBJECT,
    "time": DataType.TIME,
    "datetime": DataType.TIME,
    "file": DataType.FILE,
    "array": DataType.ARRAY,
}

# 2. 复合类型前缀：用于识别数组类型（如 arrayString → 前缀array + 元素类型String）
COMPLEX_TYPE_PREFIX = "array"
# 3. 时间格式正则（用于识别字符串中的时间类型）
TIME_PATTERNS = [
    r'^\d{4}-\d{2}-\d{2}$',  # 日期：2025-01-01
    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # 日期时间：2025-01-01 12:00:00
    r'^\d{4}/\d{2}/\d{2}$',  # 日期：2025/01/01
    r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$',  # 日期时间：2025/01/01 12:00:00
]
# 4. 文件后缀映射（用于识别文件类型）
FILE_SUFFIX_MAPPING = {
    "image": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"],
    "document": [".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx"],
    "video": [".mp4", ".avi", ".mov"],
    "audio": [".mp3", ".wav"],
}

# --------------------------
# 辅助工具函数
# --------------------------
# 基础类型映射
def is_time_string(value: str) -> bool:
    """判断字符串是否为时间类型"""
    return any(re.match(pattern, value) for pattern in TIME_PATTERNS)

def is_file_string(value: str) -> str | None:
    """判断字符串是否为文件类型，返回文件后缀（如.png），否则返回None"""
    for suffix_list in FILE_SUFFIX_MAPPING.values():
        for suffix in suffix_list:
            if value.lower().endswith(suffix):
                return suffix
    return None

def map_front_to_node_type(raw_type: str) -> str:
    """获取后端节点类型"""
    return NODE_TYPE_MAP.get(raw_type, raw_type)

def map_type_str_to_datatype(type_str: str) -> DataType:
    """映射前端类型字符串到后端 DataType 枚举"""
    type_str = type_str.lower()
    # 简单处理 arrayString 这种复合类型，这里只取基础映射
    if type_str.startswith("array"):
        return DataType.ARRAY
    return BASE_TYPE_MAPPING.get(type_str, DataType.STRING)

def convert_literal_value(content: Any) -> Any:
    """
    将前端传来的字符串值转换为 Python 原生类型
    """
    if content is None:
        return None
        
    if isinstance(content, str):
        # 布尔值处理
        if content.lower() == "true": return True
        if content.lower() == "false": return False
            
        # 数字处理
        if content.isdigit():
            return int(content)
        if content.replace(".", "", 1).isdigit() and content.count(".") == 1:
            try:
                return float(content)
            except ValueError:
                pass
                
    return content

def parse_source_to_value(source: Dict[str, Any]) -> Any:
    """
    [核心变更] 替代 InputSource。
    
    解析规则：
    1. 引用 (Reference): sourceName 存在 -> 返回 "{{ ref }}" 模板字符串
    2. 值 (Value): content 存在 -> 返回转换后的字面量
    """
    source_name = source.get("sourceName") # e.g. "node_1.result"
    content = source.get("content")        # e.g. "Hello", "123"
    
    # 1. 处理引用 -> Jinja2 模板
    if source_name and isinstance(source_name, str) and source_name.strip():
        clean_ref = source_name.strip()
        # 防止重复包裹
        if clean_ref.startswith("{{") and clean_ref.endswith("}}"):
            return clean_ref
        return f"{{{{ {clean_ref} }}}}"
    
    # 2. 处理字面量
    return convert_literal_value(content)

def parse_property_to_typeinfo_dict(prop: Dict[str, Any]) -> Dict[str, Any]:
    """
    [核心辅助] 将前端属性定义转换为 TypeInfo 的字典结构
    供 ParameterDefinition 使用
    """
    name = prop.get("name", "unknown")
    raw_type = prop.get("type", "string")
    default_val = prop.get("defaultValue")
    
    # 1. 确定 DataType
    data_type = map_type_str_to_datatype(raw_type)
    
    # 2. 构建基础 TypeInfo
    type_info = {
        "type": data_type,
        "title": name,
        "description": prop.get("description", ""),
        "required": prop.get("required", False),
        "default": default_val
    }

    # 3. 处理复杂类型 (Array/Object) 的递归
    # 如果是 Array，尝试提取元素类型
    if data_type == DataType.ARRAY:
        # 简单推断：arrayString -> string
        elem_type_str = "string"
        if raw_type.lower().startswith("array") and len(raw_type) > 5:
            elem_type_str = raw_type[5:].lower()
        
        # 构造 elem_type_info
        type_info["elem_type_info"] = {
            "type": map_type_str_to_datatype(elem_type_str),
            "title": f"{name}_item"
        }

    # 如果是 Object，处理 children
    if data_type == DataType.OBJECT:
        children = prop.get("children", [])
        properties = {}
        for child in children:
            child_name = child.get("name")
            if child_name:
                properties[child_name] = parse_property_to_typeinfo_dict(child)
        type_info["properties"] = properties

    return type_info

# --------------------------
# 节点转换逻辑
# --------------------------

def parse_vueflow_node_to_node(vueflow_node: Dict[str, Any]) -> NodeConfig:
    """将单个 Vue Flow 节点转换为 Goose NodeConfig"""
    
    # 1. 基础信息
    node_id = vueflow_node.get("id")
    node_type = map_front_to_node_type(vueflow_node.get("type", "unknown"))
    node_data = vueflow_node.get("data", {})
    node_meta = node_data.get("nodeMeta", {})
    node_title = node_meta.get("title", node_data.get("label", "Untitled"))

    # 2. 构建 inputs 字典 (扁平化)
    inputs_dict = {}
    
    # 2.1 处理 inputs 数组 (标准前端输入)
    raw_inputs = node_data.get("inputs", [])
    for raw_input in raw_inputs:
        name = raw_input.get("name")
        if not name: continue
        
        # 解析 source
        source_data = raw_input.get("source", {})
        val_or_template = parse_source_to_value(source_data)
        inputs_dict[name] = val_or_template

    # 2.2 处理散落在 data 根目录下的带 source 的属性
    # (有些前端实现不把所有参数放 inputs 数组，而是直接放 data 下)
    for key, value in node_data.items():
        if isinstance(value, dict) and "source" in value and "name" in value:
            p_name = value.get("name", key)
            val = parse_source_to_value(value["source"])
            inputs_dict[p_name] = val

    # 3. 构建 config 字典
    # 排除掉特殊字段
    excluded_fields = ["inputs", "outputs", "nodeMeta", "errorConfig", "batch", "batchInputs"]
    config_dict = {
        k: v for k, v in node_data.items() 
        if k not in excluded_fields
    }

    # 4. 特定节点类型适配
    if node_type == NodeTypes.ENTRY:
        # Entry 节点的 outputs 定义了工作流的输入参数
        # 我们将其提取到 config['input_definitions'] 中，方便后续生成 Schema
        raw_outputs = node_data.get("outputs", [])
        variables_list = []
        for out in raw_outputs:
            # 构造 ParameterDefinition 结构
            param_def = {
                "key": out.get("name"),
                # 将前端属性转换为 TypeInfo 结构
                "type_info": parse_property_to_typeinfo_dict(out)
            }
            variables_list.append(param_def)
        
        # 注入到 config.variables
        config_dict["variables"] = variables_list
    # --- LLM ---
    elif node_type == NodeTypes.LLM:
        raw_model = config_dict.pop("model", {})
        if isinstance(raw_model, dict):
            config_dict.setdefault("model", raw_model.get("modelName") or raw_model.get("name"))
            config_dict.setdefault("temperature", raw_model.get("temperature", 0.7))
            config_dict.setdefault("max_tokens", raw_model.get("maxTokens", 4096))
        
        # 字段映射
        if "userPrompt" in config_dict: config_dict["prompt"] = config_dict.pop("userPrompt")
        if "systemPrompt" in config_dict: config_dict["system_prompt"] = config_dict.pop("systemPrompt")
        
        # 工具列表
        if "pluginList" in config_dict:
            tool_list = config_dict.pop("pluginList")
            config_dict["tools"] = [t['id'] for t in tool_list if 'id' in t]

        # 输出定义 (Output Definitions)
        raw_outputs = node_data.get("outputs", [])
        if raw_outputs:
            config_dict["output_definitions"] = raw_outputs

    # --- Code Runner ---
    elif node_type == NodeTypes.CODE_RUNNER:
        # CodeRunner 需要 inputParameters 列表配置
        # 我们根据 inputs_dict 反向生成它，或者从 node_data 直接拿
        if "inputParameters" not in config_dict:
            param_list = []
            for k, v in inputs_dict.items():
                param_list.append({"name": k, "value": v}) 
            config_dict["inputParameters"] = param_list

    # --- Exit / End ---
    elif node_type == NodeTypes.EXIT:
        # Exit 节点通常定义了工作流的最终输出
        # 将 raw_inputs 转换为 output_map
        # config_dict["outputs"] = inputs_dict # 简单策略：所有输入即输出
        pass

    # 5. 生成 NodeConfig
    new_node = NodeConfig(
        id=node_id,
        type=node_type,
        title=node_title,
        inputs=inputs_dict,   
        config=config_dict, 
    )
    
    # 错误策略
    new_node.error_policy = node_data.get("errorConfig", {})
    
    return new_node

def parse_vueflow_edge_to_edge(vueflow_edge: Dict[str, Any]) -> EdgeConfig:
    """转换连线"""
    return EdgeConfig(
        id=vueflow_edge.get("id", f"edge_{uuid.uuid4().hex[:8]}"),
        source=vueflow_edge.get("source"),
        target=vueflow_edge.get("target"),
        source_handle=vueflow_edge.get("sourceHandle"),
        target_handle=vueflow_edge.get("targetHandle"),
    )

def vueflow_json_to_workflow_def(
    vueflow_json: Dict[str, Any],
    workflow_id: str,
    workflow_name: str = "Untitled",
    workflow_desc: str = ""
) -> WorkflowDefinition:
    """主转换入口"""
    
    nodes = []
    for v_node in vueflow_json.get("nodes", []):
        try:
            nodes.append(parse_vueflow_node_to_node(v_node))
        except Exception as e:
            logger.error(f"Failed to parse node {v_node.get('id')}: {e}")

    edges = []
    for v_edge in vueflow_json.get("edges", []):
        edges.append(parse_vueflow_edge_to_edge(v_edge))

    return WorkflowDefinition(
        id=workflow_id,
        name=workflow_name,
        description=workflow_desc,
        nodes=nodes,
        edges=edges,
        meta={"raw_vueflow": vueflow_json}
    )

# --------------------------
# Adapter 类
# --------------------------

class VueFlowAdapter(BaseWorkflowAdapter):
    @property
    def format_name(self) -> str:
        return "vueflow"

    def transform_workflow(self, data: Dict[str, Any], **kwargs) -> WorkflowDefinition:
        wf_id = kwargs.get("workflow_id") or data.get("id") or f"wf_{uuid.uuid4().hex[:8]}"
        wf_name = kwargs.get("workflow_name") or data.get("name") or "Imported Flow"
        wf_desc = kwargs.get("workflow_desc") or data.get("description") or ""
        
        return vueflow_json_to_workflow_def(data, wf_id, wf_name, wf_desc)

    def export_components(self) -> Dict[str, Any]:
        """
        [Export] 导出组件列表给前端
        直接从 SystemRegistry 获取数据
        """
        # 从注册中心获取所有组件定义
        # export_definitions 已经按 Group 排序并包含了 JSON Schema
        definitions = sys_registry.components.list_meta()
        
        return {"components": definitions}

# --------------------------
# 测试入口
# --------------------------
if __name__ == "__main__":
    import sys
    import os
    # 模拟环境设置
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    
    # 假设有个测试文件
    test_file = r"goose-py\tests\test.json"
    if os.path.exists(test_file):
        with open(test_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        adapter = VueFlowAdapter()
        wf_def = adapter.transform_workflow(data)
        
        print("=== Converted WorkflowDefinition ===")
        print(wf_def.model_dump_json(indent=2, exclude_none=True))
        
        if wf_def.nodes:
            print(f"\nExample Node Inputs: {wf_def.nodes[0].inputs}")
    else:
        print("Test file not found.")