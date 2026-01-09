# pip install jmespath jinja2 pydantic
import pandas as pd
import jmespath
import json
from jinja2 import Template
from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field
from loguru import logger
import numpy as np

# ===========================
# 1. 配置模型定义 (Pydantic V2)
# ===========================

class PandasConfig(BaseModel):
    """Pandas 数据清洗配置"""
    # 重命名列: {"old_name": "new_name"}
    rename: Optional[Dict[str, str]] = None
    
    # 类型转换: {"score": "float", "date": "datetime", "id": "str"}
    dtypes: Optional[Dict[str, Literal['int', 'float', 'str', 'datetime', 'bool']]] = None
    
    # 空值填充: {"score": 0} 或 "N/A" (全局填充)
    fillna: Union[None, Dict[str, Any], Any] = None
    
    # 过滤表达式 (Pandas Query): "score > 60 and role == 'admin'"
    query: Optional[str] = None
    
    # 排序: ["-score", "name"] (-代表降序)
    sort_by: Optional[List[str]] = None
    
    # 字段裁剪: 只保留这些列
    keep_columns: Optional[List[str]] = None
    
    # 最大行数限制 (防止上下文爆炸)
    limit: Optional[int] = None

class TransformConfig(BaseModel):
    """主转换配置"""
    # 1. 提取阶段 (JMESPath)
    # 如果 raw_data 是深层嵌套的 JSON，先用这个提取出列表
    jmespath_expr: Optional[str] = Field(None, description="JMESPath 提取表达式")
    
    # 2. 清洗阶段 (Pandas)
    pandas_config: Optional[PandasConfig] = None
    
    # 3. 渲染阶段 (Jinja2)
    # 最终给 LLM 看的视图模板
    template: Optional[str] = None
    
    # 当结果为空时的提示语
    empty_msg: str = "No relevant data found."

class TransformedResult(BaseModel):
    """标准化输出结果"""
    data: Any       # 清洗后的结构化数据 (存入 Artifact Store)
    view: str       # 渲染后的文本 (给 LLM 看)
    is_empty: bool = False

# ===========================
# 2. 转换器实现
# ===========================

class DictTransformer:
    
    @classmethod
    def transform(cls, raw_data: Any, config: Union[TransformConfig, Dict]) -> TransformedResult:
        """
        主入口：Raw Data -> [JMESPath] -> [Pandas] -> [Jinja2] -> Result
        """
        # 支持传入字典配置，自动转模型
        if isinstance(config, dict):
            config = TransformConfig.model_validate(config)

        current_data = raw_data

        # --- Phase 1: Extraction (JMESPath) ---
        if config.jmespath_expr:
            try:
                current_data = jmespath.search(config.jmespath_expr, raw_data)
                # 如果提取结果是 None，初始化为空列表防止 Pandas 报错
                if current_data is None:
                    current_data = []
            except Exception as e:
                logger.error(f"JMESPath extraction failed: {e}")
                # 降级：保持原数据继续尝试
        
        # --- Phase 2: Transformation (Pandas) ---
        if config.pandas_config:
            try:
                current_data = cls._process_with_pandas(current_data, config.pandas_config)
            except Exception as e:
                logger.error(f"Pandas transformation failed: {e}")
                # 降级：保持 Phase 1 的数据

        # --- Phase 3: Check Empty ---
        is_empty = False
        if current_data is None:
            is_empty = True
        elif isinstance(current_data, (list, dict, str)) and len(current_data) == 0:
            is_empty = True

        # --- Phase 4: Rendering (Jinja2) ---
        if is_empty:
            view_text = config.empty_msg
            # 确保 data 也是空的结构，方便后续处理
            final_data = [] if isinstance(current_data, list) else {}
        else:
            final_data = current_data
            view_text = cls._render_view(final_data, config.template)

        return TransformedResult(
            data=final_data,
            view=view_text,
            is_empty=is_empty
        )

    @staticmethod
    def _process_with_pandas(data: Any, cfg: PandasConfig) -> Any:
        """Pandas 处理引擎"""
        # 1. 数据标准化为 DataFrame
        if not data:
            return []
            
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            # 标量或其他类型，跳过 Pandas 处理
            return data

        if df.empty:
            return []

        # 2. 重命名 (Rename) - 优先执行，方便后续配置引用新列名
        if cfg.rename:
            df = df.rename(columns=cfg.rename)

        # 3. 类型转换 (Type Casting)
        if cfg.dtypes:
            for col, dtype in cfg.dtypes.items():
                if col not in df.columns: continue
                
                try:
                    if dtype == 'datetime':
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                        # 格式化为字符串，否则 JSON 序列化会挂
                        df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
                    elif dtype == 'float':
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    elif dtype == 'int':
                        # 转 numeric -> fillna(0) -> astype(int)
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                    elif dtype == 'str':
                        df[col] = df[col].astype(str)
                    elif dtype == 'bool':
                        df[col] = df[col].astype(bool)
                except Exception as e:
                    logger.warning(f"Type conversion failed for col '{col}': {e}")

        # 4. 空值填充 (Fill NaNs)
        if cfg.fillna is not None:
            if isinstance(cfg.fillna, dict):
                df = df.fillna(cfg.fillna)
            else:
                df = df.fillna(cfg.fillna)

        # 5. 过滤 (Query)
        if cfg.query:
            try:
                df = df.query(cfg.query)
            except Exception as e:
                logger.warning(f"Pandas query failed '{cfg.query}': {e}")

        # 6. 排序 (Sort)
        if cfg.sort_by:
            cols = []
            ascending = []
            for c in cfg.sort_by:
                if c.startswith('-'):
                    cols.append(c[1:])
                    ascending.append(False)
                else:
                    cols.append(c)
                    ascending.append(True)
            
            # 过滤掉不存在的列
            valid_cols = [c for c in cols if c in df.columns]
            if valid_cols:
                df = df.sort_values(by=valid_cols, ascending=ascending)

        # 7. 限制行数 (Limit)
        if cfg.limit and cfg.limit > 0:
            df = df.head(cfg.limit)

        # 8. 列裁剪 (Projection)
        if cfg.keep_columns:
            target_cols = [c for c in cfg.keep_columns if c in df.columns]
            if target_cols:
                df = df[target_cols]

        # 9. 导出 (Export)
        # 将 NaN 替换为 None，符合 JSON 标准
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')

    @staticmethod
    def _render_view(data: Any, template_str: Optional[str]) -> str:
        """Jinja2 渲染引擎"""
        if not template_str:
            # 默认视图：美化的 JSON
            return json.dumps(data, ensure_ascii=False, indent=2)

        try:
            # 自动封装 Context
            context = data if isinstance(data, dict) else {"items": data}
            return Template(template_str).render(context)
        except Exception as e:
            logger.error(f"Template render error: {e}")
            return str(data)



def main():
    import yaml

    config ="""
# 场景：处理 API 返回的脏数据
# 原始数据结构假设：
# {
#   "payload": {
#     "order_list": [
#       {"oid": "A1", "amt": "100.5", "st": 1, "ts": "2023-10-01"},
#       {"oid": "A2", "amt": "invalid", "st": 0},
#       {"oid": "A3", "amt": 5000, "st": 1} 
#     ]
#   }
# }

# 1. 提取阶段
jmespath_expr: "payload.order_list"

# 2. 清洗阶段
pandas_config:
  # 重命名：让列名更有语义
  rename:
    oid: "order_id"
    amt: "amount"
    st: "status"
    ts: "created_at"
  
  # 类型转换：处理脏数据
  dtypes:
    amount: "float"
    status: "int"
    created_at: "datetime"
  
  # 空值填充
  fillna:
    amount: 0.0
    created_at: "1970-01-01"
  
  # 逻辑过滤：只保留状态为1(已支付) 且 金额大于 50 的订单
  query: "status == 1 and amount > 50"
  
  # 排序：按金额倒序
  sort_by: ["-amount"]
  
  # 裁剪：只保留需要的列
  keep_columns: ["order_id", "amount", "created_at"]
  
  # 限制：只取前 5 条
  limit: 5

# 3. 渲染阶段
template: |
  **📊 高价值订单 Top 5**
  
  | ID | 金额 | 时间 |
  |---|---|---|
  {% for item in items %}
  | {{ item.order_id }} | ${{ item.amount }} | {{ item.created_at }} |
  {% endfor %}
"""
    # 1. 模拟一个糟糕的、混乱的 API 返回数据
    raw_api_data = {
        "code": 200,
        "payload": {
            "server_time": 12345678,
            "order_list": [
                {"oid": "ORD-001", "amt": "299.9", "st": 1, "ts": "2024-01-01 10:00"},
                {"oid": "ORD-002", "amt": None,    "st": 0, "ts": None}, # 脏数据
                {"oid": "ORD-003", "amt": "1200",  "st": 1, "ts": "2024-01-02 14:30"},
                {"oid": "ORD-004", "amt": 50,      "st": 1, "ts": "2024-01-03"}, # 金额太小，应被过滤
                {"oid": "ORD-005", "amt": "abc",   "st": 1}, # 金额非法
                {"oid": "ORD-006", "amt": 50000,   "st": 1, "ts": "2024-01-05"} # 大额订单
            ]
        }
    }

    config_dict = yaml.load(config,Loader=yaml.FullLoader)
    # 3. 执行转换
    print(">>> 开始处理数据...")
    result = DictTransformer.transform(raw_api_data, config_dict)

    # 4. 输出结果
    print("\n=== [Artifact Data] (存内存) ===")
    print(result.data) 
    # 预期：只包含 ORD-006, ORD-003, ORD-001 (按金额倒序)
    
    print("\n=== [LLM View] (给 AI 看) ===")
    print(result.view)

if __name__ == "__main__":
    main()