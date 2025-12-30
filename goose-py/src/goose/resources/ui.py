# src/flow_engine/resources/ui.py
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo


class OutputMapItem(BaseModel):
    """
    描述一个输出字段的映射规则
    """

    # 1. 下游看到的变量名 (Target)
    key: str = Field(..., description="输出变量名 (如 task_id)")

    # 2. 原始数据的取值路径 (Source)
    # 支持点号语法: data.items.id
    source_path: str = Field(..., description="原始数据路径")

    # 3. 数据类型
    type: Literal["String", "Number", "Boolean", "Object", "Array"] = "String"

    # 4. 嵌套结构 (用于 Object 或 Array<Object>)
    children: List["OutputMapItem"] = Field(default_factory=list)

    # 5. 数组项类型 (仅当 type=Array 时有效，如 Array<String>)
    item_type: Optional[str] = None


# 允许递归定义
OutputMapItem.model_rebuild()


# 定义泛型 T，用于 DSL 风格的返回值提示
T = TypeVar("T")


class UI:
    """
    UI 组件定义工厂
    支持两种用法：
    1. 封装式 (DSL): x: UI.Input(str, placeholder="...")
    2. 原生式 (Annotated): x: Annotated[str, UI.Input(placeholder="...")]
    """

    @staticmethod
    def _factory(
        component: str,
        dtype: Optional[Type[T]] = None,
        description: str = "",
        group: str = "",
        options: Optional[List[Any]] = None,
        **ui_props,
    ) -> Union[T, FieldInfo]:
        """
        UI 组件核心工厂方法。
        生成包含前端渲染元数据 (x-ui-component) 的 Pydantic FieldInfo。

        ----------------------------------------------------------------
        📖 使用规范指南 (Usage Guide)
        ----------------------------------------------------------------

        本工厂支持两种定义风格，请根据场景选择：

        1. 【DSL 封装风格】(推荐: 简单场景)
           直接在 UI 方法中传入类型。代码最简洁，适合无复杂校验的字段。

           >>> name: UI.Input(str, description="用户名")
           >>> port: UI.Number(int, port=8080)

        2. 【Annotated 标准风格】(推荐: 高级场景)
           结合 Pydantic 的 Annotated 使用。
           ⚠️ 注意：在此风格下，UI 方法 **不需要** 传入 dtype 参数 (即保持 None)。

           场景 A: 需要叠加 Pydantic 原生校验 (Field)
           >>> age: Annotated[int, UI.Number(description="年龄"), Field(ge=18, le=100)]

           场景 B: 需要类型转换 (BeforeValidator)
           >>> # 将输入的字符串 "a,b,c" 自动转为列表 ['a','b','c']
           >>> tags: Annotated[List[str], UI.Input(), BeforeValidator(lambda x: x.split(','))]

           场景 C: 类型比较复杂 (如 Optional, Union)
           >>> config: Annotated[Optional[dict], UI.Json(description="可选配置")]

        ----------------------------------------------------------------
        :param component: 前端组件名称 (如 'Input', 'Select')
        :param dtype: [仅 DSL 风格使用] 字段的数据类型。若使用 Annotated 风格，请留空。
        :param description: 字段描述，显示在表单下方的帮助文本。
        :param group: UI 分组标签，用于前端 Tabs 或折叠面板分类。
        :param options: 选项列表 (仅用于 Select/Radio 等组件)。
        :param ui_props: 透传给前端组件的 Props (如 placeholder, clearable, rows)。
        """

        is_hidden = ui_props.pop("hidden", False)

        # 1. 组装 UI 属性
        final_props = ui_props.copy()

        # 特殊处理 options，确保它进入 x-ui-props
        if options is not None:
            final_props["options"] = options

        # 2. 构建 Pydantic V2 的 FieldInfo
        # json_schema_extra 会被序列化到 JSON Schema 中，供前端解析
        json_extra = {
            "x-ui-component": component,
            "x-ui-props": final_props,
            "x-ui-group": group,
            "x-ui-hidden": is_hidden,
        }

        # 创建 FieldInfo
        # 注意：如果用户在 Annotated 中同时使用了 UI.Input() 和 Field()，
        # Pydantic 会自动合并它们的 metadata。
        field_info = Field(description=description, json_schema_extra=json_extra)

        # 3. 根据是否传入 dtype 决定返回类型
        if dtype is not None:
            # 风格 A: 返回 Annotated 类型 (DSL 封装)
            return Annotated[dtype, field_info]
        else:
            # 风格 B: 返回 FieldInfo (供 Annotated 使用)
            return field_info

    # ==========================================
    # 1. 基础文本类
    # ==========================================

    @overload
    @staticmethod
    def Input(
        dtype: Type[T],
        description: str = "",
        placeholder: str = "",
        group: str = "",
        clearable: bool = True,
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Input(
        description: str = "",
        placeholder: str = "",
        group: str = "",
        clearable: bool = True,
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Input(
        dtype=None,
        description: str = "",
        placeholder: str = "",
        group: str = "",
        clearable: bool = True,
        **ui_props,
    ):
        """单行文本输入框"""
        return UI._factory(
            "Input",
            dtype,
            description,
            group,
            placeholder=placeholder,
            clearable=clearable,
            **ui_props,
        )

    @overload
    @staticmethod
    def TextArea(
        dtype: Type[T],
        rows: int = 3,
        description: str = "",
        placeholder: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def TextArea(
        rows: int = 3,
        description: str = "",
        placeholder: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def TextArea(
        dtype=None,
        rows: int = 3,
        description: str = "",
        placeholder: str = "",
        group: str = "",
        **ui_props,
    ):
        """多行文本域"""
        return UI._factory(
            "TextArea",
            dtype,
            description,
            group,
            rows=rows,
            placeholder=placeholder,
            **ui_props,
        )

    @overload
    @staticmethod
    def Secret(
        dtype: Type[T],
        description: str = "",
        placeholder: str = "********",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Secret(
        description: str = "",
        placeholder: str = "********",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Secret(
        dtype=None,
        description: str = "",
        placeholder: str = "********",
        group: str = "",
        **ui_props,
    ):
        """密码/API Key 输入框 (前端掩码显示)"""
        return UI._factory(
            "Secret", dtype, description, group, placeholder=placeholder, **ui_props
        )

    # ==========================================
    # 2. 数值类
    # ==========================================

    @overload
    @staticmethod
    def Number(
        dtype: Type[T],
        min: float = None,
        max: float = None,
        step: float = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Number(
        min: float = None,
        max: float = None,
        step: float = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Number(
        dtype=None,
        min: float = None,
        max: float = None,
        step: float = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """数字输入框 (支持 int 和 float)"""
        return UI._factory(
            "InputNumber",
            dtype,
            description,
            group,
            min=min,
            max=max,
            step=step,
            **ui_props,
        )

    @overload
    @staticmethod
    def Slider(
        dtype: Type[T],
        min: float = 0,
        max: float = 100,
        step: float = 1,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Slider(
        min: float = 0,
        max: float = 100,
        step: float = 1,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Slider(
        dtype=None,
        min: float = 0,
        max: float = 100,
        step: float = 1,
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """滑动条"""
        return UI._factory(
            "Slider", dtype, description, group, min=min, max=max, step=step, **ui_props
        )

    # ==========================================
    # 3. 选项类
    # ==========================================

    @overload
    @staticmethod
    def Select(
        dtype: Type[T],
        options: List[Any],
        multiple: bool = False,
        description: str = "",
        group: str = "",
        placeholder: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Select(
        options: List[Any],
        multiple: bool = False,
        description: str = "",
        group: str = "",
        placeholder: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Select(
        dtype=None,
        options: List[Any] = [],
        multiple: bool = False,
        description: str = "",
        group: str = "",
        placeholder: str = "",
        **ui_props,
    ):
        """下拉选择器"""
        return UI._factory(
            "Select",
            dtype,
            description,
            group,
            options=options,
            multiple=multiple,
            placeholder=placeholder,
            **ui_props,
        )

    @overload
    @staticmethod
    def Switch(
        dtype: Type[T], description: str = "", group: str = "", **ui_props
    ) -> T: ...
    @overload
    @staticmethod
    def Switch(description: str = "", group: str = "", **ui_props) -> FieldInfo: ...

    @staticmethod
    def Switch(dtype=None, description: str = "", group: str = "", **ui_props):
        """布尔开关"""
        return UI._factory("Switch", dtype, description, group, **ui_props)

    # ==========================================
    # 4. 高级类
    # ==========================================

    @overload
    @staticmethod
    def Json(
        dtype: Type[T],
        description: str = "",
        height: str = "200px",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Json(
        description: str = "", height: str = "200px", group: str = "", **ui_props
    ) -> FieldInfo: ...

    @staticmethod
    def Json(
        dtype=None,
        description: str = "",
        height: str = "200px",
        group: str = "",
        **ui_props,
    ):
        """JSON 编辑器"""
        return UI._factory(
            "JsonEditor", dtype, description, group, height=height, **ui_props
        )

    @overload
    @staticmethod
    def Code(
        dtype: Type[T],
        language: str = "python",
        description: str = "",
        height: str = "200px",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Code(
        language: str = "python",
        description: str = "",
        height: str = "200px",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Code(
        dtype=None,
        language: str = "python",
        description: str = "",
        height: str = "200px",
        group: str = "",
        **ui_props,
    ):
        """代码编辑器"""
        return UI._factory(
            "CodeEditor",
            dtype,
            description,
            group,
            language=language,
            height=height,
            **ui_props,
        )

    # ==========================================
    # 1. 复杂输入类 (Table / Radio / Checkbox)
    # ==========================================

    @overload
    @staticmethod
    def InputTable(
        dtype: Type[T],
        columns: List[Dict],
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def InputTable(
        columns: List[Dict], description: str = "", group: str = "", **ui_props
    ) -> FieldInfo: ...

    @staticmethod
    def InputTable(
        dtype=None,
        columns: List[Dict] = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """
        表格输入组件。
        DSL 用法: variables: UI.InputTable(Dict, columns=[...])
        """
        # 默认列配置 (为了兼容以前的默认行为，如果用户没传 columns 则使用默认)
        default_columns = [
            {"title": "变量名", "dataIndex": "key", "type": "input"},
            {
                "title": "变量类型",
                "dataIndex": "type",
                "type": "select",
                "options": ["String", "Number", "Object"],
            },
            {"title": "变量值", "dataIndex": "value", "type": "input"},
        ]
        cols = columns if columns is not None else default_columns

        return UI._factory(
            "InputTable", dtype, description, group, columns=cols, **ui_props
        )

    @overload
    @staticmethod
    def Radio(
        dtype: Type[T],
        options: List[dict],
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Radio(
        options: List[dict], description: str = "", group: str = "", **ui_props
    ) -> FieldInfo: ...

    @staticmethod
    def Radio(
        dtype=None,
        options: List[dict] = [],
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """单选框组"""
        return UI._factory(
            "Radio", dtype, description, group, options=options, **ui_props
        )

    @overload
    @staticmethod
    def Checkbox(
        dtype: Type[T],
        options: List[dict],
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Checkbox(
        options: List[dict], description: str = "", group: str = "", **ui_props
    ) -> FieldInfo: ...

    @staticmethod
    def Checkbox(
        dtype=None,
        options: List[dict] = [],
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """复选框组 (通常配合 List[Any] 使用)"""
        return UI._factory(
            "Checkbox", dtype, description, group, options=options, **ui_props
        )

    # ==========================================
    # 2. 日期时间类
    # ==========================================

    @overload
    @staticmethod
    def DatePicker(
        dtype: Type[T],
        placeholder: str = "请选择日期",
        format: str = "YYYY-MM-DD",
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def DatePicker(
        placeholder: str = "请选择日期",
        format: str = "YYYY-MM-DD",
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def DatePicker(
        dtype=None,
        placeholder: str = "请选择日期",
        format: str = "YYYY-MM-DD",
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """日期选择器"""
        return UI._factory(
            "DatePicker",
            dtype,
            description,
            group,
            placeholder=placeholder,
            format=format,
            **ui_props,
        )

    @overload
    @staticmethod
    def DateTimePicker(
        dtype: Type[T],
        placeholder: str = "请选择日期时间",
        format: str = "YYYY-MM-DD HH:mm:ss",
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def DateTimePicker(
        placeholder: str = "请选择日期时间",
        format: str = "YYYY-MM-DD HH:mm:ss",
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def DateTimePicker(
        dtype=None,
        placeholder: str = "请选择日期时间",
        format: str = "YYYY-MM-DD HH:mm:ss",
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """日期时间选择器"""
        return UI._factory(
            "DateTimePicker",
            dtype,
            description,
            group,
            placeholder=placeholder,
            format=format,
            **ui_props,
        )

    # ==========================================
    # 3. 特殊功能类 (Upload / Rate)
    # ==========================================

    @overload
    @staticmethod
    def Upload(
        dtype: Type[T],
        accept: str = "image/*",
        multiple: bool = False,
        limit: Optional[int] = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Upload(
        accept: str = "image/*",
        multiple: bool = False,
        limit: Optional[int] = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def Upload(
        dtype=None,
        accept: str = "image/*",
        multiple: bool = False,
        limit: Optional[int] = None,
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """文件上传组件"""
        return UI._factory(
            "Upload",
            dtype,
            description,
            group,
            accept=accept,
            multiple=multiple,
            limit=limit,
            **ui_props,
        )

    @overload
    @staticmethod
    def Rate(
        dtype: Type[T],
        min: int = 1,
        max: int = 5,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def Rate(
        min: int = 1, max: int = 5, description: str = "", group: str = "", **ui_props
    ) -> FieldInfo: ...

    @staticmethod
    def Rate(
        dtype=None,
        min: int = 1,
        max: int = 5,
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """评分组件"""
        return UI._factory(
            "Rate", dtype, description, group, min=min, max=max, **ui_props
        )

    # ==========================================
    # 4. 高级配置类 (ModelConfig / DataSource)
    # ==========================================

    @overload
    @staticmethod
    def ModelConfig(
        dtype: Type[T],
        model_class: Type[BaseModel],
        label: str = "配置",
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def ModelConfig(
        model_class: Type[BaseModel],
        label: str = "配置",
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def ModelConfig(
        dtype=None,
        model_class: Type[BaseModel] = None,
        label: str = "配置",
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """
        【高级】复合配置组件。
        DSL 用法: config: UI.ModelConfig(Dict, MyConfigModel)
        Annotated 用法: config: Annotated[Dict, UI.ModelConfig(MyConfigModel)]
        """
        # 核心逻辑：动态提取 Schema 传给前端
        # 前端会根据这个 schema 递归渲染表单
        sub_schema = model_class.model_json_schema() if model_class else {}

        return UI._factory(
            "ModalConfig",
            dtype,
            description,
            group,
            label=label,
            schema=sub_schema,  # 将子 schema 作为 props 传递
            **ui_props,
        )

    @overload
    @staticmethod
    def DataSource(
        dtype: Type[T],
        source_type: str,
        multiple: bool = False,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> T: ...
    @overload
    @staticmethod
    def DataSource(
        source_type: str,
        multiple: bool = False,
        description: str = "",
        group: str = "",
        **ui_props,
    ) -> FieldInfo: ...

    @staticmethod
    def DataSource(
        dtype=None,
        source_type: str = "",
        multiple: bool = False,
        description: str = "",
        group: str = "",
        **ui_props,
    ):
        """
        【特性】动态数据源选择器
        DSL 用法: model: UI.DataSource(str, "models")
        :param source_type: 'models' | 'tools' | 'knowledge_bases'
        """
        return UI._factory(
            "Select",  # 本质还是下拉框
            dtype,
            description,
            group,
            multiple=multiple,
            placeholder=f"Select {source_type}...",
            dataSource=source_type,  # 特殊标记，前端看到这个会去调用 API 加载数据
            **ui_props,
        )


    @staticmethod
    def OutputMap(raw_model: Type[BaseModel], description: str = "", group: str = ""):
        """
        【通用】输出映射编辑器
        :param raw_model: 节点原始输出的 Pydantic 模型 (用于前端生成 source_path 的候选项)
        """
        # 提取原始 Schema，传给前端作为“数据源”提示
        raw_schema = raw_model.model_json_schema()

        return UI._factory(
            "OutputMapper",  # 前端需实现对应的树状映射组件
            List[OutputMapItem],  # 最终存储的是映射配置列表
            description,
            group,
            raw_schema=raw_schema,  # 关键：把原始结构告诉前端
        )

    
    @staticmethod
    def TypeBuilder(
        description: str = "",
        group: str = "",
        # 可以限制用户能选择的根类型，比如 Start 节点通常只允许 Object 或 String
        allowed_root_types: List[str] = ["string", "number", "boolean", "object", "array"],
        **ui_props
    ):
        """
        【核心特性】动态类型构建器 (Dynamic Schema Builder)
        前端应渲染为一个支持递归嵌套的表格编辑器 (类似 Coze 的参数配置)。
        
        DSL 用法: 
            inputs: List[ParameterDefinition] = Field(
                default_factory=list, 
                json_schema_extra=UI.TypeBuilder()
            )
        """
        return UI._factory(
            "TypeBuilder", # 前端组件名
            None, # Annotated 不需要 dtype
            description,
            group,
            allowed_types=allowed_root_types,
            **ui_props
        )
        
    @staticmethod
    def Combo(
        dtype: Type[T]=None,
        model_class: Type[BaseModel] = None,
        description: str = "",
        group: str = "",
    ):
        """
        【通用】对象列表组件 (Repeater / Array Editor)
        前端渲染为：一个可增删的列表，列表的每一项是一个子表单（根据 model_class 生成）。
        适用于：复杂嵌套对象的数组。
        """
        # 如果传入了 model_class，提取其 Schema 传给前端，方便前端递归渲染
        items_schema = {}
        if model_class:
            items_schema = model_class.model_json_schema()

        # 复用 factory
        return UI._factory(
            "ListEditor",  # 前端需要实现一个通用的 ListEditor 组件
            dtype,
            description,
            group,
            # 告诉前端：列表里的每一项长什么样
            items_schema=items_schema,
        )
