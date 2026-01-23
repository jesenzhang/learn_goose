"""
Recipe Module

可重用任务模板系统，支持：
- YAML/JSON 格式的配方定义
- 参数化模板 (Jinja2) 支持继承
- 配方验证
- 配方执行
- 重试配置
- 安全检查

Reference: goose-rs/crates/goose/src/recipe/mod.rs
"""

import json
import os
import re
import shutil
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone


GOOSE_RECIPE_PATH_ENV_VAR = "GOOSE_RECIPE_PATH"


class RecipeParameterInputType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    FILE = "file"
    SELECT = "select"


class RecipeParameterRequirement(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    USER_PROMPT = "user_prompt"


class RetryStrategy(str, Enum):
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"


class RecipeError(Exception):
    def __init__(self, message: str, code: str = "RECIPE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass
class Author:
    contact: Optional[str] = None
    metadata: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.contact:
            result["contact"] = self.contact
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Author":
        return cls(
            contact=data.get("contact"),
            metadata=data.get("metadata")
        )


@dataclass
class Settings:
    goose_provider: Optional[str] = None
    goose_model: Optional[str] = None
    temperature: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.goose_provider:
            result["goose_provider"] = self.goose_provider
        if self.goose_model:
            result["goose_model"] = self.goose_model
        if self.temperature is not None:
            result["temperature"] = self.temperature
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        return cls(
            goose_provider=data.get("goose_provider"),
            goose_model=data.get("goose_model"),
            temperature=data.get("temperature")
        )


@dataclass
class Response:
    json_schema: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        if self.json_schema:
            return {"json_schema": self.json_schema}
        return {}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Response":
        return cls(json_schema=data.get("json_schema"))


@dataclass
class RecipeParameter:
    key: str
    input_type: RecipeParameterInputType
    requirement: RecipeParameterRequirement
    description: str
    default: Optional[str] = None
    options: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "key": self.key,
            "input_type": self.input_type.value,
            "requirement": self.requirement.value,
            "description": self.description,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.options:
            result["options"] = self.options
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecipeParameter":
        return cls(
            key=data["key"],
            input_type=RecipeParameterInputType(data.get("input_type", "string")),
            requirement=RecipeParameterRequirement(data.get("requirement", "optional")),
            description=data.get("description", ""),
            default=data.get("default"),
            options=data.get("options")
        )


@dataclass
class SubRecipe:
    name: str
    path: str
    values: Dict[str, str] = field(default_factory=dict)
    sequential_when_repeated: bool = False
    description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "path": self.path,
            "values": self.values,
            "sequential_when_repeated": self.sequential_when_repeated,
        }
        if self.description:
            result["description"] = self.description
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubRecipe":
        return cls(
            name=data["name"],
            path=data["path"],
            values=data.get("values", {}),
            sequential_when_repeated=data.get("sequential_when_repeated", False),
            description=data.get("description")
        )


@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_delay_ms: int = 1000
    max_delay_ms: int = 60000
    exponential_base: int = 2
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    
    def validate(self) -> List[str]:
        errors = []
        if self.max_retries < 0:
            errors.append("max_retries must be non-negative")
        if self.initial_delay_ms <= 0:
            errors.append("initial_delay_ms must be positive")
        if self.max_delay_ms <= 0:
            errors.append("max_delay_ms must be positive")
        if self.initial_delay_ms > self.max_delay_ms:
            errors.append("initial_delay_ms cannot be greater than max_delay_ms")
        if self.exponential_base <= 1:
            errors.append("exponential_base must be greater than 1")
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "initial_delay_ms": self.initial_delay_ms,
            "max_delay_ms": self.max_delay_ms,
            "exponential_base": self.exponential_base,
            "strategy": self.strategy.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetryConfig":
        strategy = data.get("strategy", "exponential_backoff")
        if isinstance(strategy, str):
            strategy = RetryStrategy(strategy)
        return cls(
            max_retries=data.get("max_retries", 3),
            initial_delay_ms=data.get("initial_delay_ms", 1000),
            max_delay_ms=data.get("max_delay_ms", 60000),
            exponential_base=data.get("exponential_base", 2),
            strategy=strategy,
        )


@dataclass
class RenderedRecipe:
    title: str
    description: str
    instructions: Optional[str] = None
    prompt: Optional[str] = None
    settings: Optional[Settings] = None
    activities: Optional[List[str]] = None
    parameters: Optional[List[RecipeParameter]] = None
    response: Optional[Response] = None


UNICODE_TAG_PATTERN = re.compile(r'[\uE000-\uF8FF]')


def contains_unicode_tags(text: str) -> bool:
    return bool(UNICODE_TAG_PATTERN.search(text))


@dataclass
class Recipe:
    version: str = "1.0.0"
    title: str = ""
    description: str = ""
    instructions: Optional[str] = None
    prompt: Optional[str] = None
    extensions: Optional[List[Dict[str, Any]]] = None
    settings: Optional[Settings] = None
    activities: Optional[List[str]] = None
    author: Optional[Author] = None
    parameters: Optional[List[RecipeParameter]] = None
    response: Optional[Response] = None
    sub_recipes: Optional[List[SubRecipe]] = None
    retry: Optional[RetryConfig] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def __post_init__(self):
        if self.settings and isinstance(self.settings, dict):
            self.settings = Settings.from_dict(self.settings)
        if self.author and isinstance(self.author, dict):
            self.author = Author.from_dict(self.author)
        if self.retry and isinstance(self.retry, dict):
            self.retry = RetryConfig.from_dict(self.retry)
    
    def check_for_security_warnings(self) -> bool:
        if contains_unicode_tags(self.instructions or ""):
            return True
        if contains_unicode_tags(self.prompt or ""):
            return True
        if self.activities:
            for activity in self.activities:
                if contains_unicode_tags(activity):
                    return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        
        if self.instructions:
            data["instructions"] = self.instructions
        if self.prompt:
            data["prompt"] = self.prompt
        if self.extensions:
            data["extensions"] = self.extensions
        if self.settings:
            data["settings"] = self.settings.to_dict()
        if self.activities:
            data["activities"] = self.activities
        if self.author:
            data["author"] = self.author.to_dict()
        if self.parameters:
            data["parameters"] = [p.to_dict() for p in self.parameters]
        if self.response:
            data["response"] = self.response.to_dict()
        if self.sub_recipes:
            data["sub_recipes"] = [s.to_dict() for s in self.sub_recipes]
        if self.retry:
            data["retry"] = self.retry.to_dict()
        
        return data
    
    def to_yaml(self) -> str:
        import yaml
        yaml.add_representer(str, lambda dumper, s: dumper.represent_scalar('tag:yaml.org,2002:str', s))
        return yaml.dump(self.to_dict(), default_flow_style=False, allow_unicode=True)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recipe":
        parameters = None
        if data.get("parameters"):
            parameters = [RecipeParameter.from_dict(p) for p in data["parameters"]]
        
        sub_recipes = None
        if data.get("sub_recipes"):
            sub_recipes = [SubRecipe.from_dict(s) for s in data["sub_recipes"]]
        
        author = None
        if data.get("author"):
            author = Author.from_dict(data["author"])
        
        settings = None
        if data.get("settings"):
            settings = Settings.from_dict(data["settings"])
        
        response = None
        if data.get("response"):
            response = Response.from_dict(data["response"])
        
        retry = None
        if data.get("retry"):
            retry = RetryConfig.from_dict(data["retry"])
        
        return cls(
            version=data.get("version", "1.0.0"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            instructions=data.get("instructions"),
            prompt=data.get("prompt"),
            extensions=data.get("extensions"),
            settings=settings,
            activities=data.get("activities"),
            author=author,
            parameters=parameters,
            response=response,
            sub_recipes=sub_recipes,
            retry=retry,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat())
        )
    
    @classmethod
    def from_content(cls, content: str) -> "Recipe":
        import yaml
        
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise RecipeError(f"Failed to parse recipe: {e}", "PARSE_ERROR")
        
        if data is None:
            raise RecipeError("Empty recipe content", "PARSE_ERROR")
        
        if "recipe" in data:
            data = data["recipe"]
        
        if "name" in data and "title" not in data:
            data["title"] = data["name"]
        
        recipe = cls.from_dict(data)
        
        if recipe.retry:
            validation_errors = recipe.retry.validate()
            if validation_errors:
                raise RecipeError(
                    f"Invalid retry configuration: {validation_errors}",
                    "INVALID_RETRY_CONFIG"
                )
        
        return recipe
    
    @classmethod
    def from_file(cls, file_path: str) -> "Recipe":
        path = Path(file_path)
        if not path.exists():
            raise RecipeError(f"Recipe file not found: {file_path}", "FILE_NOT_FOUND")
        
        content = path.read_text(encoding="utf-8")
        return cls.from_content(content)
    
    def validate(self) -> List[str]:
        errors = []
        
        if not self.title:
            errors.append("Title is required")
        
        if not self.description:
            errors.append("Description is required")
        
        if not self.instructions and not self.prompt:
            errors.append("At least one of 'prompt' or 'instructions' is required")
        
        if self.parameters:
            param_keys = set()
            for param in self.parameters:
                if param.key in param_keys:
                    errors.append(f"Duplicate parameter key: {param.key}")
                param_keys.add(param.key)
                
                if param.input_type == RecipeParameterInputType.SELECT and not param.options:
                    errors.append(f"Select parameter '{param.key}' must have options")
                
                if param.requirement == RecipeParameterRequirement.REQUIRED:
                    if param.default is not None:
                        errors.append(f"Required parameter '{param.key}' cannot have a default value")
        
        if self.retry:
            errors.extend(self.retry.validate())
        
        return errors
    
    def render(self, params: Dict[str, Any], recipe_dir: Optional[str] = None) -> RenderedRecipe:
        from jinja2 import Environment, StrictUndefined, BaseLoader, FileSystemLoader, DictLoader
        import tempfile
        
        def render_field(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            try:
                template = env.from_string(value)
                return template.render(**params)
            except Exception as e:
                raise RecipeError(f"Template render error: {e}", "TEMPLATE_ERROR")
        
        template_content = self._get_template_content()
        
        loaders = []
        if recipe_dir:
            loaders.append(FileSystemLoader(recipe_dir))
        loaders.append(DictLoader({}))
        
        env = Environment(
            loader=BaseLoader.from_list(loaders),
            undefined=StrictUndefined,
            autoescape=False
        )
        
        if uses_template_inheritance(template_content):
            try:
                template = env.from_string(template_content)
                template.render(**params)
            except Exception as e:
                raise RecipeError(f"Template inheritance error: {e}", "TEMPLATE_ERROR")
        
        rendered = RenderedRecipe(
            title=self.title,
            description=self.description,
            instructions=render_field(self.instructions),
            prompt=render_field(self.prompt),
            settings=self.settings,
            activities=self.activities,
            parameters=self.parameters,
            response=self.response,
        )
        
        return rendered
    
    def _get_template_content(self) -> str:
        parts = []
        if self.title:
            parts.append(f"title: {self.title}")
        if self.description:
            parts.append(f"description: {self.description}")
        if self.instructions:
            parts.append(f"instructions: |\n  {self.instructions}")
        if self.prompt:
            parts.append(f"prompt: |\n  {self.prompt}")
        return "\n".join(parts)
    
    def extract_variables(self) -> List[str]:
        text = self.prompt or self.instructions or ""
        
        variables = set()
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"
        matches = re.findall(pattern, text)
        variables.update(matches)
        
        return sorted(list(variables))


def uses_template_inheritance(content: str) -> bool:
    inheritance_pattern = r'\{%-?\s*(extends|include)'
    return bool(re.search(inheritance_pattern, content))


def preprocess_template_variables(content: str) -> str:
    all_vars = extract_template_variables(content)
    complex_vars = [v for v in all_vars if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', v)]
    
    result = content
    for var in complex_vars:
        pattern = r'\{\{\s*' + re.escape(var) + r'\s*\}\}'
        replacement = r'{% raw %}{{' + var + '}}{% endraw %}'
        result = re.sub(pattern, replacement, result)
    
    return result


def extract_template_variables(content: str) -> List[str]:
    pattern = r"\{\{\s*(.*?)\s*\}\}"
    matches = re.findall(pattern, content)
    return matches


class RecipeLoader:
    BUILT_IN_RECIPE_DIR_PARAM = "recipe_dir"
    RECIPE_FILE_EXTENSIONS = [".yaml", ".json"]
    
    def __init__(
        self,
        recipe_dirs: Optional[List[str]] = None,
        built_in_dir: Optional[str] = None,
        use_env_path: bool = True
    ):
        self.recipe_dirs = recipe_dirs or []
        self.built_in_dir = built_in_dir
        self._cache: Dict[str, Recipe] = {}
        
        if use_env_path:
            self._init_from_env_path()
    
    def _init_from_env_path(self):
        recipe_path = os.environ.get(GOOSE_RECIPE_PATH_ENV_VAR)
        if recipe_path:
            path_separator = ';' if os.name == 'nt' else ':'
            for path in recipe_path.split(path_separator):
                path = path.strip()
                if path and path not in self.recipe_dirs:
                    self.recipe_dirs.append(path)
    
    def get_recipe_library_dir(self, is_global: bool = True) -> Path:
        if is_global:
            config_dir = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
            return Path(config_dir) / "goose" / "recipes"
        else:
            return Path.cwd() / ".goose" / "recipes"
    
    def add_recipe_dir(self, path: str) -> None:
        if path not in self.recipe_dirs:
            self.recipe_dirs.append(path)
    
    def load(self, name_or_path: str) -> Optional[Recipe]:
        if name_or_path in self._cache:
            return self._cache[name_or_path]
        
        recipe = self._load_from_path(name_or_path)
        if recipe:
            self._cache[name_or_path] = recipe
        
        return recipe
    
    def _is_file_path(self, path: str) -> bool:
        return any(char in path for char in ['/', '\\', '~', '.'])
    
    def _is_file_name(self, path: str) -> bool:
        return Path(path).suffix in self.RECIPE_FILE_EXTENSIONS
    
    def _load_from_path(self, path: str) -> Optional[Recipe]:
        if self._is_file_path(path) or self._is_file_name(path):
            p = Path(path)
            if p.exists():
                try:
                    return Recipe.from_file(str(p))
                except RecipeError:
                    pass
        
        search_dirs = self.recipe_dirs.copy()
        
        global_dir = self.get_recipe_library_dir(True)
        local_dir = self.get_recipe_library_dir(False)
        if global_dir not in search_dirs:
            search_dirs.insert(0, str(global_dir))
        if local_dir not in search_dirs:
            search_dirs.insert(0, str(local_dir))
        
        for dir_path in search_dirs:
            recipe = self._load_from_dir(Path(dir_path), path)
            if recipe:
                return recipe
        
        return None
    
    def _load_from_dir(self, dir_path: Path, recipe_name: str) -> Optional[Recipe]:
        for ext in self.RECIPE_FILE_EXTENSIONS:
            recipe_path = dir_path / f"{recipe_name}{ext}"
            if recipe_path.exists():
                try:
                    return Recipe.from_file(str(recipe_path))
                except RecipeError:
                    pass
        return None
    
    def load_recipe_file(self, recipe_name: str) -> Optional[Recipe]:
        return self.load(recipe_name)
    
    def list_recipes(self) -> List[Dict[str, Any]]:
        recipes = []
        seen = set()
        
        search_dirs = self.recipe_dirs.copy()
        global_dir = self.get_recipe_library_dir(True)
        local_dir = self.get_recipe_library_dir(False)
        if global_dir not in search_dirs:
            search_dirs.insert(0, str(global_dir))
        if local_dir not in search_dirs:
            search_dirs.insert(0, str(local_dir))
        
        for recipe_dir in search_dirs:
            dir_path = Path(recipe_dir)
            if not dir_path.exists() or not dir_path.is_dir():
                continue
            
            for p in dir_path.glob("*.yaml"):
                if p.stem not in seen:
                    seen.add(p.stem)
                    recipe = self.load(p.stem)
                    if recipe:
                        recipes.append({
                            "name": p.stem,
                            "title": recipe.title,
                            "description": recipe.description
                        })
            
            for p in dir_path.glob("*.json"):
                if p.stem not in seen:
                    seen.add(p.stem)
                    recipe = self.load(p.stem)
                    if recipe:
                        recipes.append({
                            "name": p.stem,
                            "title": recipe.title,
                            "description": recipe.description
                        })
        
        return recipes
    
    def scan_directory_for_recipes(self, dir_path: Path) -> List[tuple]:
        recipes = []
        if not dir_path.exists() or not dir_path.is_dir():
            return recipes
        
        for entry in dir_path.iterdir():
            if entry.is_file():
                if entry.suffix in self.RECIPE_FILE_EXTENSIONS:
                    try:
                        recipe = Recipe.from_file(str(entry))
                        recipes.append((entry, recipe))
                    except RecipeError as e:
                        import logging
                        logging.error(f"Failed to load recipe from {entry}: {e}")
        
        return recipes
    
    def search(self, query: str) -> List[Recipe]:
        results = []
        for recipe_dir in self.recipe_dirs:
            for p in Path(recipe_dir).glob("*.yaml"):
                recipe = self.load(p.stem)
                if recipe:
                    if (query.lower() in recipe.title.lower() or 
                        query.lower() in recipe.description.lower()):
                        results.append(recipe)
        return results
    
    def clear_cache(self) -> None:
        self._cache.clear()


def generate_recipe_filename(title: str, recipe_library_dir: Path) -> Path:
    base_name = "".join(
        c for c in title.lower()
        if c.isalnum() or c.isspace() or c == '-'
    ).split()[0]
    
    if not base_name:
        base_name = "untitled-recipe"
    
    candidate = recipe_library_dir / f"{base_name}.yaml"
    if not candidate.exists():
        return candidate
    
    counter = 1
    while True:
        candidate = recipe_library_dir / f"{base_name}-{counter}.yaml"
        if not candidate.exists():
            return candidate
        counter += 1


def save_recipe_to_file(recipe: Recipe, file_path: Optional[str] = None, is_global: bool = True) -> Path:
    loader = RecipeLoader()
    recipe_library_dir = loader.get_recipe_library_dir(is_global)
    
    if file_path:
        path = Path(file_path)
    else:
        path = generate_recipe_filename(recipe.title, recipe_library_dir)
    
    path = path.with_suffix(".yaml")
    
    path.parent.mkdir(parents=True, exist_ok=True)
    
    yaml_content = recipe.to_yaml()
    path.write_text(yaml_content, encoding="utf-8")
    
    return path


class RecipeExecutor:
    def __init__(
        self,
        agent_factory: Callable,
        recipe_loader: Optional[RecipeLoader] = None
    ):
        self.agent_factory = agent_factory
        self.recipe_loader = recipe_loader or RecipeLoader()
    
    async def execute(
        self,
        recipe: Recipe,
        params: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        params = params or {}
        
        from goose.recipe import RecipeLoader
        loader = RecipeLoader()
        recipe_dir = str(loader.get_recipe_library_dir(True))
        
        rendered = recipe.render(params, recipe_dir=recipe_dir)
        
        agent = self.agent_factory()
        
        if system_prompt is None:
            system_prompt = rendered.instructions or rendered.prompt or ""
        
        state = await agent.reply(system_prompt)
        
        return {
            "recipe": recipe.title,
            "params": params,
            "messages": state.messages,
            "turn_count": len(state.messages)
        }
    
    async def execute_by_name(
        self,
        recipe_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        recipe = self.recipe_loader.load(recipe_name)
        if not recipe:
            raise RecipeError(f"Recipe not found: {recipe_name}", "NOT_FOUND")
        
        return await self.execute(recipe, params)


def create_recipe_loader(recipe_dirs: Optional[List[str]] = None) -> RecipeLoader:
    return RecipeLoader(recipe_dirs=recipe_dirs)


def create_recipe_executor(
    agent_factory: Callable,
    recipe_dirs: Optional[List[str]] = None
) -> RecipeExecutor:
    loader = create_recipe_loader(recipe_dirs)
    return RecipeExecutor(agent_factory=agent_factory, recipe_loader=loader)


def render_recipe_content_with_params(
    content: str,
    params: Dict[str, str],
    recipe_dir: Optional[str] = None
) -> str:
    from jinja2 import Environment, StrictUndefined
    
    processed_content = preprocess_template_variables(content)
    
    env = Environment(undefined=StrictUndefined)
    
    if recipe_dir:
        try:
            env.loader = env.file_system_loader.__class__(recipe_dir)
        except:
            pass
    
    try:
        template = env.from_string(processed_content)
        return template.render(**params)
    except Exception as e:
        raise RecipeError(f"Failed to render recipe: {e}", "RENDER_ERROR")


def parse_recipe_content(
    content: str,
    recipe_dir: Optional[str] = None
) -> tuple:
    preprocessed = preprocess_template_variables(content)
    recipe = Recipe.from_content(preprocessed)
    variables = recipe.extract_variables()
    return recipe, variables
