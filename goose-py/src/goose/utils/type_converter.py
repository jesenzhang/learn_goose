import inspect
import re
import functools
from typing import Any, Dict, List, Optional, Type, Union, Callable, get_origin, get_args
from pydantic import BaseModel, Field, create_model, ValidationError, ConfigDict
import jsonschema

# 引用核心类型定义 (确保 core/types.py 存在)
from goose.types import DataType, TypeInfo

# --- 全局配置 ---
TIME_FORMAT_REGEX = {
    "yyyy-mm-dd": r'^\d{4}-\d{2}-\d{2}$',
    "yyyy-mm-dd hh:mm:ss": r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',
    "yyyy/mm/dd": r'^\d{4}/\d{2}/\d{2}$',
    "yyyy/mm/dd hh:mm:ss": r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$',
    "default": r'^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$',
}

FILE_SUFFIX_REGEX = {
    "png": r'(?i)\.png$',
    "jpg": r'(?i)\.(jpg|jpeg)$',
    "pdf": r'(?i)\.pdf$',
    "txt": r'(?i)\.txt$',
    "svg": r'(?i)\.svg$',
    "*": r'(?i)\.\w+$',
}

class TypeConverter:
    """
    [Core] 统一类型转换工具
    负责在 Pydantic Model <-> TypeInfo <-> JSON Schema <-> Python Function 之间流转
    """

    # ==========================================
    # 1. TypeInfo <-> JSON Schema
    # ==========================================
    @staticmethod
    def to_json_schema(typeinfo: TypeInfo) -> Dict[str, Any]:
        """TypeInfo -> JSON Schema"""
        schema = {
            "title": typeinfo.title or None,
            "description": typeinfo.description or None,
        }
        if typeinfo.default is not None:
            schema["default"] = typeinfo.default

        dt = typeinfo.type
        
        if dt == DataType.OBJECT:
            schema["type"] = "object"
            if typeinfo.properties:
                schema["properties"] = {
                    k: TypeConverter.to_json_schema(v) 
                    for k, v in typeinfo.properties.items()
                }
                reqs = [k for k, v in typeinfo.properties.items() if v.required]
                if reqs: schema["required"] = reqs
            else:
                schema["additionalProperties"] = True
        
        elif dt == DataType.ARRAY:
            schema["type"] = "array"
            if typeinfo.elem_type_info:
                schema["items"] = TypeConverter.to_json_schema(typeinfo.elem_type_info)
            else:
                schema["items"] = {}
        
        elif dt == DataType.TIME:
            schema["type"] = "string"
            pattern = TIME_FORMAT_REGEX.get(typeinfo.time_format or "default")
            if pattern: schema["pattern"] = pattern
            
        elif dt == DataType.FILE:
            schema["type"] = "string"
            pattern = FILE_SUFFIX_REGEX.get(typeinfo.file_type or "*")
            if pattern: schema["pattern"] = pattern
            
        else:
            # 基础类型映射
            mapping = {
                DataType.STRING: "string", DataType.INTEGER: "integer",
                DataType.NUMBER: "number", DataType.BOOLEAN: "boolean"
            }
            schema["type"] = mapping.get(dt, "string")

        return {k: v for k, v in schema.items() if v is not None}

    @staticmethod
    def from_json_schema(schema: Dict[str, Any], prop_name: str = "") -> TypeInfo:
        """JSON Schema -> TypeInfo"""
        schema_type = schema.get("type", "string")
        data_type = DataType.STRING
        
        if schema_type == "array": data_type = DataType.ARRAY
        elif schema_type == "object": data_type = DataType.OBJECT
        elif schema_type == "integer": data_type = DataType.INTEGER
        elif schema_type == "number": data_type = DataType.NUMBER
        elif schema_type == "boolean": data_type = DataType.BOOLEAN
        elif schema_type == "string":
            pattern = schema.get("pattern", "")
            if any(pattern == r for r in TIME_FORMAT_REGEX.values()):
                data_type = DataType.TIME
            elif any(pattern == r for r in FILE_SUFFIX_REGEX.values()):
                data_type = DataType.FILE
        
        typeinfo = TypeInfo(
            type=data_type,
            title=schema.get("title") or prop_name,
            description=schema.get("description"),
            required=False, # 上层逻辑处理
            default=schema.get("default"),
        )

        if data_type == DataType.TIME:
            pattern = schema.get("pattern", "")
            for k, v in TIME_FORMAT_REGEX.items():
                if v == pattern:
                    typeinfo.time_format = k
                    break
        
        elif data_type == DataType.FILE:
            pattern = schema.get("pattern", "")
            for k, v in FILE_SUFFIX_REGEX.items():
                if v == pattern:
                    typeinfo.file_type = k
                    break

        elif data_type == DataType.OBJECT:
            props = schema.get("properties", {})
            reqs = schema.get("required", [])
            typeinfo.properties = {}
            for k, v in props.items():
                child = TypeConverter.from_json_schema(v, k)
                child.required = k in reqs
                typeinfo.properties[k] = child

        elif data_type == DataType.ARRAY:
            items = schema.get("items", {})
            if items:
                typeinfo.elem_type_info = TypeConverter.from_json_schema(items, f"{prop_name}_item")

        return typeinfo

    # ==========================================
    # 2. TypeInfo <-> Pydantic
    # ==========================================
    
    @staticmethod
    def to_pydantic(typeinfo: TypeInfo, model_name: str = "DynamicModel") -> Type[BaseModel]:
        """
        TypeInfo -> Pydantic Model Class
        使用 LRU 缓存避免重复创建 Class (Key 为 typeinfo 的 JSON 字符串)
        """
        # 为了使用 lru_cache，我们需要传入不可变对象。这里简单地序列化为 JSON 字符串作为 Key。
        return TypeConverter._cached_to_pydantic(typeinfo.model_dump_json(), model_name)

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def _cached_to_pydantic(typeinfo_json: str, model_name: str) -> Type[BaseModel]:
        """内部缓存实现"""
        typeinfo = TypeInfo.model_validate_json(typeinfo_json)
        
        # 1. 对象类型且有属性：创建标准 Pydantic Model
        if typeinfo.type == DataType.OBJECT and typeinfo.properties:
            fields = {}
            for k, v in typeinfo.properties.items():
                py_type = TypeConverter._get_py_type(v)
                # 处理默认值：如果是必填，默认值为 ... (Ellipsis)
                default = ... if v.required else (v.default if v.default is not None else None)
                fields[k] = (py_type, Field(default, title=v.title, description=v.description))
            
            return create_model(model_name, **fields)
        
        # 2. 对象类型但无属性：创建允许任意字段的 Model (Dict)
        elif typeinfo.type == DataType.OBJECT:
            return create_model(
                model_name, 
                __config__=ConfigDict(extra='allow')
            )
            
        # 3. 基础类型或数组：创建包装模型 (Wrapper Model)
        # 因为 create_model 必须创建类，不能直接返回 int 或 List[int]
        else:
            py_type = TypeConverter._get_py_type(typeinfo)
            
            # 注入校验 Pattern
            extra = {}
            if typeinfo.type == DataType.TIME: 
                extra["pattern"] = TIME_FORMAT_REGEX.get(typeinfo.time_format or "default")
            if typeinfo.type == DataType.FILE:
                extra["pattern"] = FILE_SUFFIX_REGEX.get(typeinfo.file_type or "*")
                
            default = ... if typeinfo.required else (typeinfo.default if typeinfo.default is not None else None)
            
            # 定义一个名为 'value' 的字段来承载数据
            fields = {
                "value": (py_type, Field(default, title=typeinfo.title, description=typeinfo.description, **extra))
            }
            return create_model(model_name, **fields)

    @classmethod
    def from_pydantic(cls, model: Type[BaseModel]) -> TypeInfo:
        """Pydantic Model Class -> TypeInfo"""
        schema = model.model_json_schema(mode='validation')
        return cls.from_json_schema(schema)
    
    @classmethod
    def pydantic_to_json_schema(cls, model: Type[BaseModel]) -> Dict[str, Any]:
        """[Shortcut] Pydantic Model -> JSON Schema"""
        return model.model_json_schema(mode='validation')

    @classmethod
    def json_schema_to_pydantic(cls, schema: Dict[str, Any], model_name: str = "DynamicModel") -> Type[BaseModel]:
        """[Shortcut] JSON Schema -> Pydantic Model"""
        type_info = cls.from_json_schema(schema)
        return cls.to_pydantic(type_info, model_name)
    
    # ==========================================
    # 3. Python Function <-> TypeInfo
    # ==========================================
    @classmethod
    def infer_input_schema(cls, func: Callable) -> TypeInfo:
        """推断函数输入 Schema"""
        explicit_model = cls._get_input_model(func)
        if explicit_model:
            return cls.from_pydantic(explicit_model)
        return cls._from_function(func)
    
    @classmethod
    def infer_output_schema(cls, func: Callable) -> Optional[TypeInfo]:
        """推断函数返回值 Schema"""
        try:
            sig = inspect.signature(func)
            ret_type = sig.return_annotation
        except (ValueError, TypeError):
            return None

        if ret_type is inspect.Signature.empty or ret_type is None:
            return None

        return cls._py_type_to_typeinfo(ret_type)

    # ==========================================
    # Helpers
    # ==========================================
    @classmethod
    def _from_function(cls, func: Callable) -> TypeInfo:
        """从普通函数签名动态生成 Schema"""
        try:
            sig = inspect.signature(func)
        except ValueError:
            return TypeInfo(type=DataType.OBJECT)

        fields = {}
        for name, param in sig.parameters.items():
            if name in ('self', 'cls', 'ctx', 'config'): 
                continue
            
            annotation = param.annotation
            if annotation == inspect.Parameter.empty:
                annotation = str
            
            default = param.default
            if default == inspect.Parameter.empty:
                default = ... 
            
            fields[name] = (annotation, default)

        DynamicModel = create_model(
            f"{func.__name__}Args", 
            __config__=ConfigDict(extra='allow'), 
            **fields
        )
        return cls.from_pydantic(DynamicModel)

    @classmethod
    def _get_input_model(cls, func: Any) -> Type[BaseModel] | None:
        """查找显式的 Pydantic Input Model"""
        try:
            annotations = inspect.get_annotations(func)
        except (ValueError, AttributeError):
            return None

        # 优先查找名为 'inputs' 的参数
        if "inputs" in annotations:
            arg_type = annotations["inputs"]
            if isinstance(arg_type, type) and issubclass(arg_type, BaseModel):
                return arg_type

        # 扫描参数类型
        try:
            sig = inspect.signature(func)
            for name, param in sig.parameters.items():
                if name in ('self', 'cls', 'ctx', 'config'): continue
                if isinstance(param.annotation, type) and issubclass(param.annotation, BaseModel):
                    return param.annotation
        except ValueError:
            pass
        return None

    @staticmethod
    def _get_py_type(info: TypeInfo) -> Any:
        """Internal: TypeInfo -> Python Type"""
        dt = info.type
        if dt == DataType.STRING: return str
        if dt == DataType.INTEGER: return int
        if dt == DataType.NUMBER: return float
        if dt == DataType.BOOLEAN: return bool
        if dt == DataType.TIME: return str
        if dt == DataType.FILE: return str
        
        if dt == DataType.OBJECT: 
            if not info.properties:
                return dict
            # 递归创建嵌套模型
            # 注意：这里直接递归调用，如果层级很深可能会慢，但对于配置对象通常没问题
            return TypeConverter.to_pydantic(info, f"Nested_{info.title or 'Obj'}")
            
        if dt == DataType.ARRAY:
            elem_info = info.elem_type_info
            # [Fix] 递归获取元素类型，并返回 typing.List
            elem_type = TypeConverter._get_py_type(elem_info) if elem_info else Any
            return List[elem_type]
            
        return Any
    
    @classmethod
    def _py_type_to_typeinfo(cls, py_type: Any) -> TypeInfo:
        """Python Type Hint -> TypeInfo"""
        if isinstance(py_type, type) and issubclass(py_type, BaseModel):
            return cls.from_pydantic(py_type)

        origin = get_origin(py_type)
        args = get_args(py_type)

        # List[T]
        if origin is list or origin is List:
            elem_type = args[0] if args else str
            elem_info = cls._py_type_to_typeinfo(elem_type)
            return TypeInfo(type=DataType.ARRAY, elem_type=elem_info)
        
        # Dict
        if origin is dict or origin is Dict:
            return TypeInfo(type=DataType.OBJECT)

        # Primitives
        if py_type is str: return TypeInfo(type=DataType.STRING)
        if py_type is int: return TypeInfo(type=DataType.INTEGER)
        if py_type is float: return TypeInfo(type=DataType.NUMBER)
        if py_type is bool: return TypeInfo(type=DataType.BOOLEAN)
        
        # TypedDict
        if isinstance(py_type, type) and issubclass(py_type, dict) and hasattr(py_type, '__annotations__'):
            props = {}
            for name, type_hint in py_type.__annotations__.items():
                child_info = cls._py_type_to_typeinfo(type_hint)
                child_info.required = getattr(py_type, '__total__', True)
                props[name] = child_info
            return TypeInfo(type=DataType.OBJECT, properties=props)

        return TypeInfo(type=DataType.OBJECT)

class DataValidator:
    """基于 TypeInfo/Pydantic 的数据验证工具"""

    @staticmethod
    def validate_with_typeinfo(data: Any, typeinfo: TypeInfo) -> tuple[bool, Union[Any, List[str]]]:
        """
        验证数据是否符合 TypeInfo 定义。
        返回: (is_valid, validated_data_or_errors)
        """
        try:
            model = TypeConverter.to_pydantic(typeinfo)
            
            if typeinfo.type == DataType.OBJECT:
                if not isinstance(data, dict):
                    return False, ["Input data must be a dictionary for Object type"]
                # 允许 extra fields，防止因前端多传了无用字段而报错
                validated_obj = model.model_validate(data)
                return True, validated_obj.model_dump()
            else:
                # 基础类型/数组：包装验证
                # data=123 -> model(value=123)
                validated_obj = model.model_validate({"value": data})
                return True, validated_obj.model_dump()["value"]
                
        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = ".".join([str(x) for x in err['loc']])
                msg = err['msg']
                errors.append(f"{loc}: {msg}")
            return False, errors
        except Exception as e:
            return False, [str(e)]

    @staticmethod
    def validate_with_json_schema(data: Any, schema: Dict[str, Any]) -> tuple[bool, Union[Any, str]]:
        try:
            jsonschema.validate(instance=data, schema=schema)
            return True, data
        except jsonschema.ValidationError as e:
            return False, e.message