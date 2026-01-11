"""
Type converter for Pho framework.

Handles conversion between Pydantic models, TypeInfo, and JSON Schema.
"""

import inspect
import functools
from typing import Any, Dict, List, Optional, Type, Union, Callable
from pydantic import BaseModel, Field, create_model, ValidationError, ConfigDict

from pho.types import DataType, TypeInfo


# --- Global Configuration ---
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
    Type conversion utility.

    Handles conversion between:
    - Pydantic models
    - TypeInfo
    - JSON Schema
    - Python function signatures
    """

    # ==========================================
    # 1. TypeInfo <-> JSON Schema
    # ==========================================
    @staticmethod
    def to_json_schema(typeinfo: TypeInfo) -> Dict[str, Any]:
        """Convert TypeInfo to JSON Schema."""
        if typeinfo is None:
            return {}

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
                if reqs:
                    schema["required"] = reqs
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
            if pattern:
                schema["pattern"] = pattern

        elif dt == DataType.FILE:
            schema["type"] = "string"
            pattern = FILE_SUFFIX_REGEX.get(typeinfo.file_type or "*")
            if pattern:
                schema["pattern"] = pattern

        else:
            # Basic type mapping
            mapping = {
                DataType.STRING: "string",
                DataType.INTEGER: "integer",
                DataType.NUMBER: "number",
                DataType.BOOLEAN: "boolean"
            }
            schema["type"] = mapping.get(dt, "string")

        return {k: v for k, v in schema.items() if v is not None}

    @staticmethod
    def from_json_schema(schema: Dict[str, Any], prop_name: str = "") -> TypeInfo:
        """Convert JSON Schema to TypeInfo."""
        schema_type = schema.get("type", "string")
        data_type = DataType.STRING

        if schema_type == "array":
            data_type = DataType.ARRAY
        elif schema_type == "object":
            data_type = DataType.OBJECT
        elif schema_type == "integer":
            data_type = DataType.INTEGER
        elif schema_type == "number":
            data_type = DataType.NUMBER
        elif schema_type == "boolean":
            data_type = DataType.BOOLEAN
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
            required=False,  # Handled by upper level logic
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
        Convert TypeInfo to Pydantic Model Class.
        Uses LRU cache to avoid recreating classes.
        """
        return TypeConverter._cached_to_pydantic(typeinfo.model_dump_json(), model_name)

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def _cached_to_pydantic(typeinfo_json: str, model_name: str) -> Type[BaseModel]:
        """Internal cached implementation."""
        typeinfo = TypeInfo.model_validate_json(typeinfo_json)

        # Object type with properties: create standard Pydantic Model
        if typeinfo.type == DataType.OBJECT and typeinfo.properties:
            fields = {}
            for k, v in typeinfo.properties.items():
                py_type = TypeConverter._get_py_type(v)
                default = ... if v.required else (v.default if v.default is not None else None)
                fields[k] = (py_type, Field(default, title=v.title, description=v.description))

            return create_model(model_name, **fields)

        # Object type without properties: allow arbitrary fields
        elif typeinfo.type == DataType.OBJECT:
            return create_model(
                model_name,
                __config__=ConfigDict(extra='allow')
            )

        # Basic types or array: create wrapper model
        else:
            py_type = TypeConverter._get_py_type(typeinfo)

            extra = {}
            if typeinfo.type == DataType.TIME:
                extra["pattern"] = r'^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$'
            if typeinfo.type == DataType.FILE:
                extra["pattern"] = r'(?i)\.\w+$'

            default = ... if typeinfo.required else (typeinfo.default if typeinfo.default is not None else None)

            fields = {
                "value": (py_type, Field(default, title=typeinfo.title, description=typeinfo.description, **extra))
            }
            return create_model(model_name, **fields)

    @classmethod
    def from_pydantic(cls, model: Type[BaseModel]) -> TypeInfo:
        """Convert Pydantic Model Class to TypeInfo."""
        schema = model.model_json_schema(mode='validation')
        return cls.from_json_schema(schema)

    @classmethod
    def pydantic_to_json_schema(cls, model: Type[BaseModel]) -> Dict[str, Any]:
        """Convert Pydantic Model to JSON Schema."""
        return model.model_json_schema(mode='validation')

    @classmethod
    def json_schema_to_pydantic(cls, schema: Dict[str, Any], model_name: str = "DynamicModel") -> Type[BaseModel]:
        """Convert JSON Schema to Pydantic Model."""
        type_info = cls.from_json_schema(schema)
        return cls.to_pydantic(type_info, model_name)

    @classmethod
    def infer_input_schema(cls, func: Callable) -> TypeInfo:
        """Infer input schema from function signature."""
        explicit_model = cls._get_input_model(func)
        if explicit_model:
            return cls.from_pydantic(explicit_model)
        return cls._infer_inputs_from_function(func)

    @classmethod
    def infer_config_schema(cls, func: Callable) -> TypeInfo:
        """Infer config schema from function signature."""
        explicit_model = cls._get_config_model(func)
        if explicit_model:
            return cls.from_pydantic(explicit_model)
        return cls._infer_config_from_function(func)

    @classmethod
    def infer_output_schema(cls, func: Callable) -> Optional[TypeInfo]:
        """Infer output schema from function signature."""
        try:
            sig = inspect.signature(func)
            ret_type = sig.return_annotation
        except (ValueError, TypeError):
            return None

        if ret_type is inspect.Signature.empty or ret_type is None:
            return None

        return cls._py_type_to_typeinfo(ret_type)

    @classmethod
    def _infer_inputs_from_function(cls, func: Callable) -> TypeInfo:
        """Infer schema from function parameters."""
        try:
            sig = inspect.signature(func)
        except ValueError:
            return TypeInfo(type=DataType.OBJECT)

        fields = {}
        has_inputs_dict_arg = False

        for name, param in sig.parameters.items():
            if name in ('self', 'cls', 'ctx', 'config', 'context'):
                continue

            # Filter out keyword-only parameters (they're config, not inputs)
            if param.kind == inspect.Parameter.KEYWORD_ONLY:
                continue

            annotation = param.annotation
            origin_type = getattr(annotation, "__origin__", annotation)

            if name == "inputs" and origin_type in (dict, Dict, Any, inspect.Parameter.empty):
                has_inputs_dict_arg = True
                continue

            if annotation == inspect.Parameter.empty:
                annotation = str

            default = param.default
            if default == inspect.Parameter.empty:
                default = ...

            fields[name] = (annotation, default)

        # Function has inputs: Dict parameter
        if has_inputs_dict_arg and not fields:
            DynamicModel = create_model(
                f"{func.__name__}Args",
                __config__=ConfigDict(extra='allow')
            )
            return cls.from_pydantic(DynamicModel)

        # Normal parameters
        if fields:
            DynamicModel = create_model(
                f"{func.__name__}Args",
                __config__=ConfigDict(extra='ignore'),
                **fields
            )
            return cls.from_pydantic(DynamicModel)

        # No valid parameters
        return None

    @classmethod
    def _infer_config_from_function(cls, func: Callable) -> TypeInfo:
        """Infer config schema from function signature."""
        try:
            sig = inspect.signature(func)
        except ValueError:
            return TypeInfo(type=DataType.OBJECT)

        fields = {}
        has_config_dict_arg = False

        for name, param in sig.parameters.items():
            if name in ('self', 'cls', 'ctx', 'inputs', 'context'):
                continue

            annotation = param.annotation
            origin_type = getattr(annotation, "__origin__", annotation)

            # Check for config: Dict parameter
            if name == "config" and origin_type in (dict, Dict, Any, inspect.Parameter.empty):
                has_config_dict_arg = True
                continue

            # Only capture keyword-only parameters as config
            if param.kind != inspect.Parameter.KEYWORD_ONLY:
                continue

            if annotation == inspect.Parameter.empty:
                annotation = str

            default = param.default
            if default == inspect.Parameter.empty:
                default = ...

            fields[name] = (annotation, default)

        # Function has config: Dict parameter
        if has_config_dict_arg and not fields:
            DynamicModel = create_model(
                f"{func.__name__}Config",
                __config__=ConfigDict(extra='allow')
            )
            return cls.from_pydantic(DynamicModel)

        # Specific config parameters
        if fields:
            DynamicModel = create_model(
                f"{func.__name__}Config",
                __config__=ConfigDict(extra='ignore'),
                **fields
            )
            return cls.from_pydantic(DynamicModel)

        # No config parameters
        return TypeInfo(type=DataType.OBJECT)

    @classmethod
    def _get_input_model(cls, func: Any) -> Optional[Type[BaseModel]]:
        """Find explicit Pydantic Input Model."""
        try:
            annotations = inspect.get_annotations(func)
        except (ValueError, AttributeError):
            return None

        if "inputs" in annotations:
            arg_type = annotations["inputs"]
            if isinstance(arg_type, type) and issubclass(arg_type, BaseModel):
                return arg_type

        return None

    @classmethod
    def _get_config_model(cls, func: Any) -> Optional[Type[BaseModel]]:
        """Find explicit Pydantic Config Model."""
        try:
            annotations = inspect.get_annotations(func)
        except (ValueError, AttributeError):
            return None

        if "config" in annotations:
            arg_type = annotations["config"]
            if isinstance(arg_type, type) and issubclass(arg_type, BaseModel):
                return arg_type

        return None

    @staticmethod
    def _get_py_type(info: TypeInfo) -> Any:
        """Convert TypeInfo to Python Type."""
        dt = info.type
        if dt == DataType.STRING:
            return str
        if dt == DataType.INTEGER:
            return int
        if dt == DataType.NUMBER:
            return float
        if dt == DataType.BOOLEAN:
            return bool
        if dt == DataType.TIME:
            return str
        if dt == DataType.FILE:
            return str

        if dt == DataType.OBJECT:
            if not info.properties:
                return dict
            return TypeConverter.to_pydantic(info, f"Nested_{info.title or 'Obj'}")

        if dt == DataType.ARRAY:
            elem_info = info.elem_type_info
            elem_type = TypeConverter._get_py_type(elem_info) if elem_info else Any
            return List[elem_type]

        return Any

    @classmethod
    def _py_type_to_typeinfo(cls, py_type: Any) -> TypeInfo:
        """Convert Python Type Hint to TypeInfo."""
        if isinstance(py_type, type) and issubclass(py_type, BaseModel):
            return cls.from_pydantic(py_type)

        origin = getattr(py_type, "__origin__", None)
        args = getattr(py_type, "__args__", None)

        # List[T]
        if origin is list:
            elem_type = args[0] if args else str
            elem_info = cls._py_type_to_typeinfo(elem_type)
            return TypeInfo(type=DataType.ARRAY, elem_type_info=elem_info)

        # Dict
        if origin is dict:
            return TypeInfo(type=DataType.OBJECT)

        # Primitives
        if py_type is str:
            return TypeInfo(type=DataType.STRING)
        if py_type is int:
            return TypeInfo(type=DataType.INTEGER)
        if py_type is float:
            return TypeInfo(type=DataType.NUMBER)
        if py_type is bool:
            return TypeInfo(type=DataType.BOOLEAN)

        return TypeInfo(type=DataType.OBJECT)


class DataValidator:
    """Data validation utility based on TypeInfo/Pydantic models."""

    @staticmethod
    def validate_with_typeinfo(data: Any, typeinfo: TypeInfo) -> tuple[bool, Union[Any, List[str]]]:
        """
        Validate data against TypeInfo definition.

        Args:
            data: The data to validate
            typeinfo: The TypeInfo defining the expected structure

        Returns:
            Tuple of (is_valid, validated_data_or_errors)
        """
        try:
            model = TypeConverter.to_pydantic(typeinfo)

            if typeinfo.type == DataType.OBJECT:
                if not isinstance(data, dict):
                    return False, ["Input data must be a dictionary for Object type"]
                # Allow extra fields to prevent errors from unused frontend fields
                validated_obj = model.model_validate(data)
                return True, validated_obj.model_dump()
            else:
                # Basic types/arrays: wrapped validation
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


__all__ = ["TypeConverter", "DataValidator"]
