"""
Tests for recipe module
"""

import pytest
import tempfile
import os
from pathlib import Path
from goose.recipe import (
    Recipe,
    RecipeParameter,
    RecipeParameterInputType,
    RecipeParameterRequirement,
    Author,
    Settings,
    Response,
    SubRecipe,
    RetryConfig,
    RetryStrategy,
    RecipeLoader,
    RecipeError,
    contains_unicode_tags,
    save_recipe_to_file,
    generate_recipe_filename,
    preprocess_template_variables,
    uses_template_inheritance,
    render_recipe_content_with_params,
    parse_recipe_content,
    GOOSE_RECIPE_PATH_ENV_VAR,
)


class TestRecipeParameter:
    """Test RecipeParameter dataclass"""

    def test_parameter_creation(self):
        param = RecipeParameter(
            key="name",
            input_type=RecipeParameterInputType.STRING,
            requirement=RecipeParameterRequirement.REQUIRED,
            description="Your name",
            default="Guest"
        )
        assert param.key == "name"
        assert param.input_type == RecipeParameterInputType.STRING
        assert param.requirement == RecipeParameterRequirement.REQUIRED

    def test_parameter_to_dict(self):
        param = RecipeParameter(
            key="count",
            input_type=RecipeParameterInputType.NUMBER,
            requirement=RecipeParameterRequirement.OPTIONAL,
            description="Count items"
        )
        result = param.to_dict()
        assert result["key"] == "count"
        assert result["input_type"] == "number"
        assert result["requirement"] == "optional"

    def test_parameter_from_dict(self):
        data = {
            "key": "age",
            "input_type": "number",
            "requirement": "required",
            "description": "Your age",
            "default": "18"
        }
        param = RecipeParameter.from_dict(data)
        assert param.key == "age"
        assert param.input_type == RecipeParameterInputType.NUMBER


class TestRetryConfig:
    """Test RetryConfig dataclass"""

    def test_retry_config_creation(self):
        retry = RetryConfig(
            max_retries=3,
            initial_delay_ms=1000,
            max_delay_ms=60000,
            exponential_base=2,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF
        )
        assert retry.max_retries == 3
        assert retry.strategy == RetryStrategy.EXPONENTIAL_BACKOFF

    def test_retry_config_validation(self):
        retry = RetryConfig(max_retries=-1)
        errors = retry.validate()
        assert "max_retries must be non-negative" in errors

    def test_retry_config_validation_delay(self):
        retry = RetryConfig(initial_delay_ms=-1)
        errors = retry.validate()
        assert "initial_delay_ms must be positive" in errors

    def test_retry_config_validation_base(self):
        retry = RetryConfig(exponential_base=1)
        errors = retry.validate()
        assert "exponential_base must be greater than 1" in errors

    def test_retry_config_to_dict(self):
        retry = RetryConfig(max_retries=5)
        result = retry.to_dict()
        assert result["max_retries"] == 5
        assert result["strategy"] == "exponential_backoff"

    def test_retry_config_from_dict(self):
        data = {
            "max_retries": 2,
            "strategy": "linear_backoff"
        }
        retry = RetryConfig.from_dict(data)
        assert retry.max_retries == 2
        assert retry.strategy == RetryStrategy.LINEAR_BACKOFF


class TestAuthor:
    """Test Author dataclass"""

    def test_author_creation(self):
        author = Author(contact="test@example.com", metadata="Test author")
        assert author.contact == "test@example.com"

    def test_author_to_dict(self):
        author = Author(contact="test@example.com")
        result = author.to_dict()
        assert result["contact"] == "test@example.com"


class TestRecipe:
    """Test Recipe dataclass"""

    def test_recipe_creation(self):
        recipe = Recipe(
            title="Test Recipe",
            description="A test recipe",
            instructions="Do something"
        )
        assert recipe.title == "Test Recipe"
        assert recipe.version == "1.0.0"

    def test_recipe_with_all_fields(self):
        recipe = Recipe(
            title="Full Recipe",
            description="A complete recipe",
            instructions="Instructions here",
            prompt="Prompt here",
            settings=Settings(goose_model="gpt-4"),
            activities=["activity1", "activity2"],
            author=Author(contact="test@example.com"),
            parameters=[
                RecipeParameter(
                    key="name",
                    input_type=RecipeParameterInputType.STRING,
                    requirement=RecipeParameterRequirement.REQUIRED,
                    description="Name parameter"
                )
            ],
            response=Response(json_schema={"type": "object"}),
            sub_recipes=[
                SubRecipe(name="sub1", path="sub1.yaml")
            ],
            retry=RetryConfig(max_retries=3)
        )
        assert recipe.settings.goose_model == "gpt-4"
        assert len(recipe.parameters) == 1
        assert recipe.retry.max_retries == 3

    def test_recipe_to_dict(self):
        recipe = Recipe(
            title="Test Recipe",
            description="A test recipe",
            instructions="Do something"
        )
        result = recipe.to_dict()
        assert result["title"] == "Test Recipe"
        assert result["version"] == "1.0.0"

    def test_recipe_from_yaml_content(self):
        content = """
version: 1.0.0
title: YAML Recipe
description: A recipe from YAML
instructions: Do something useful
"""
        recipe = Recipe.from_content(content)
        assert recipe.title == "YAML Recipe"
        assert recipe.instructions == "Do something useful"

    def test_recipe_from_json_content(self):
        content = """
{
    "version": "1.0.0",
    "title": "JSON Recipe",
    "description": "A recipe from JSON",
    "instructions": "Process JSON data"
}
"""
        recipe = Recipe.from_content(content)
        assert recipe.title == "JSON Recipe"

    def test_recipe_from_nested_yaml(self):
        content = """
name: nested_recipe
recipe:
    title: Nested Recipe
    description: A nested recipe structure
    instructions: Handle nested content
"""
        recipe = Recipe.from_content(content)
        assert recipe.title == "Nested Recipe"

    def test_recipe_from_file(self, tmp_path):
        content = """
version: 1.0.0
title: File Recipe
description: A recipe from file
instructions: Read from file
"""
        recipe_file = tmp_path / "test_recipe.yaml"
        recipe_file.write_text(content)
        
        recipe = Recipe.from_file(str(recipe_file))
        assert recipe.title == "File Recipe"

    def test_recipe_validation_required_fields(self):
        recipe = Recipe(title="", description="")
        errors = recipe.validate()
        assert "Title is required" in errors
        assert "Description is required" in errors

    def test_recipe_validation_missing_prompt_instructions(self):
        recipe = Recipe(title="Test", description="Test")
        errors = recipe.validate()
        assert "At least one of 'prompt' or 'instructions' is required" in errors

    def test_recipe_validation_duplicate_params(self):
        recipe = Recipe(
            title="Test",
            description="Test",
            instructions="Do it",
            parameters=[
                RecipeParameter(
                    key="name",
                    input_type=RecipeParameterInputType.STRING,
                    requirement=RecipeParameterRequirement.OPTIONAL,
                    description="Name"
                ),
                RecipeParameter(
                    key="name",
                    input_type=RecipeParameterInputType.STRING,
                    requirement=RecipeParameterRequirement.OPTIONAL,
                    description="Name again"
                )
            ]
        )
        errors = recipe.validate()
        assert "Duplicate parameter key: name" in errors

    def test_recipe_validation_select_options(self):
        recipe = Recipe(
            title="Test",
            description="Test",
            instructions="Do it",
            parameters=[
                RecipeParameter(
                    key="choice",
                    input_type=RecipeParameterInputType.SELECT,
                    requirement=RecipeParameterRequirement.OPTIONAL,
                    description="Select an option"
                )
            ]
        )
        errors = recipe.validate()
        assert "Select parameter 'choice' must have options" in errors

    def test_recipe_validation_required_with_default(self):
        recipe = Recipe(
            title="Test",
            description="Test",
            instructions="Do it",
            parameters=[
                RecipeParameter(
                    key="required_param",
                    input_type=RecipeParameterInputType.STRING,
                    requirement=RecipeParameterRequirement.REQUIRED,
                    description="Required param",
                    default="default_value"
                )
            ]
        )
        errors = recipe.validate()
        assert "Required parameter 'required_param' cannot have a default value" in errors

    def test_recipe_validation_retry(self):
        recipe = Recipe(
            title="Test",
            description="Test",
            instructions="Do it",
            retry=RetryConfig(max_retries=-1)
        )
        errors = recipe.validate()
        assert any("max_retries must be non-negative" in e for e in errors)

    def test_recipe_render_basic(self):
        recipe = Recipe(
            title="Render Test",
            description="Testing render",
            instructions="Say hello to {{ name }}"
        )
        rendered = recipe.render({"name": "World"})
        assert "World" in rendered.instructions

    def test_recipe_extract_variables(self):
        recipe = Recipe(
            title="Variables",
            description="Testing variables",
            instructions="Hello {{ name }}, your age is {{ age }}"
        )
        variables = recipe.extract_variables()
        assert "name" in variables
        assert "age" in variables


class TestSecurityWarnings:
    """Test security warning detection"""

    def test_contains_unicode_tags_clean(self):
        assert not contains_unicode_tags("clean text")
        assert not contains_unicode_tags("instructions here")

    def test_contains_unicode_tags_malicious(self):
        malicious_text = "instructions" + chr(0xE0041)
        assert contains_unicode_tags(malicious_text)

    def test_recipe_security_warning_clean(self):
        recipe = Recipe(
            title="Clean",
            description="Clean recipe",
            instructions="Do something clean"
        )
        assert not recipe.check_for_security_warnings()

    def test_recipe_security_warning_malicious_instructions(self):
        recipe = Recipe(
            title="Malicious",
            description="Malicious recipe",
            instructions="instructions" + chr(0xE0041)
        )
        assert recipe.check_for_security_warnings()

    def test_recipe_security_warning_malicious_prompt(self):
        recipe = Recipe(
            title="Malicious",
            description="Malicious recipe",
            prompt="prompt" + chr(0xE0042)
        )
        assert recipe.check_for_security_warnings()

    def test_recipe_security_warning_malicious_activity(self):
        recipe = Recipe(
            title="Malicious",
            description="Malicious recipe",
            instructions="Do something",
            activities=["clean", "malicious" + chr(0xE0041)]
        )
        assert recipe.check_for_security_warnings()


class TestRecipeLoader:
    """Test RecipeLoader class"""

    def test_loader_basic(self, tmp_path):
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        assert len(loader.recipe_dirs) == 1

    def test_loader_add_dir(self, tmp_path):
        loader = RecipeLoader()
        loader.add_recipe_dir(str(tmp_path))
        assert str(tmp_path) in loader.recipe_dirs

    def test_loader_load_from_file(self, tmp_path):
        content = """
version: 1.0.0
title: Load Test
description: Testing load
instructions: Load this recipe
"""
        recipe_file = tmp_path / "load_test.yaml"
        recipe_file.write_text(content)
        
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        recipe = loader.load("load_test")
        
        assert recipe is not None
        assert recipe.title == "Load Test"

    def test_loader_load_json(self, tmp_path):
        content = """
{
    "version": "1.0.0",
    "title": "JSON Load Test",
    "description": "Testing JSON load",
    "instructions": "Load JSON recipe"
}
"""
        recipe_file = tmp_path / "json_load.json"
        recipe_file.write_text(content)
        
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        recipe = loader.load("json_load")
        
        assert recipe is not None
        assert recipe.title == "JSON Load Test"

    def test_loader_cache(self, tmp_path):
        content = """
version: 1.0.0
title: Cache Test
description: Testing cache
instructions: Cache this
"""
        recipe_file = tmp_path / "cache_test.yaml"
        recipe_file.write_text(content)
        
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        recipe1 = loader.load("cache_test")
        recipe2 = loader.load("cache_test")
        
        assert recipe1 is recipe2

    def test_loader_search_recipes(self, tmp_path):
        (tmp_path / "recipe1.yaml").write_text("""
version: 1.0.0
title: Recipe One
description: First recipe
instructions: Do one
""")
        (tmp_path / "recipe2.yaml").write_text("""
version: 1.0.0
title: Recipe Two
description: Second recipe
instructions: Do two
""")
        
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        recipes = loader.list_recipes()
        
        assert len(recipes) == 2

    def test_loader_search_query(self, tmp_path):
        (tmp_path / "search_test.yaml").write_text("""
version: 1.0.0
title: Search Target
description: Find this recipe
instructions: Search for it
""")
        
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        results = loader.search("target")
        
        assert len(results) == 1
        assert results[0].title == "Search Target"

    def test_loader_clear_cache(self, tmp_path):
        content = """
version: 1.0.0
title: Cache Clear Test
description: Testing cache clear
instructions: Clear cache
"""
        recipe_file = tmp_path / "cache_clear.yaml"
        recipe_file.write_text(content)
        
        loader = RecipeLoader(recipe_dirs=[str(tmp_path)])
        loader.load("cache_clear")
        assert "cache_clear" in loader._cache
        
        loader.clear_cache()
        assert "cache_clear" not in loader._cache

    def test_loader_env_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv(GOOSE_RECIPE_PATH_ENV_VAR, str(tmp_path))
        
        content = """
version: 1.0.0
title: Env Path Test
description: Testing env path
instructions: Load from env
"""
        (tmp_path / "env_test.yaml").write_text(content)
        
        loader = RecipeLoader(use_env_path=True)
        assert str(tmp_path) in loader.recipe_dirs


class TestTemplateFunctions:
    """Test template-related functions"""

    def test_preprocess_template_variables(self):
        content = "Hello {{ name }} and {{ invalid var }}"
        result = preprocess_template_variables(content)
        assert "{{ name }}" in result
        assert "{% raw %}" in result

    def test_uses_template_inheritance_false(self):
        content = "Hello {{ name }}"
        assert not uses_template_inheritance(content)

    def test_uses_template_inheritance_true(self):
        content = """
{% extends "base.html" %}
Hello {{ name }}
"""
        assert uses_template_inheritance(content)

    def test_uses_template_inheritance_include(self):
        content = """
{% include "header.html" %}
Content here
"""
        assert uses_template_inheritance(content)


class TestRecipeSave:
    """Test recipe save functionality"""

    def test_generate_recipe_filename(self, tmp_path):
        filename = generate_recipe_filename("My Recipe", tmp_path)
        assert filename.name == "my-recipe.yaml"

    def test_generate_recipe_filename_duplicate(self, tmp_path):
        (tmp_path / "my-recipe.yaml").write_text("test")
        
        filename = generate_recipe_filename("My Recipe", tmp_path)
        assert filename.name == "my-recipe-1.yaml"

    def test_save_recipe_to_file(self, tmp_path):
        recipe = Recipe(
            title="Save Test",
            description="Testing save",
            instructions="Save this recipe"
        )
        
        path = save_recipe_to_file(recipe, str(tmp_path / "saved.yaml"))
        
        assert path.exists()
        
        loaded = Recipe.from_file(str(path))
        assert loaded.title == "Save Test"

    def test_save_recipe_auto_filename(self, tmp_path):
        recipe = Recipe(
            title="Auto Name Recipe",
            description="Testing auto naming",
            instructions="Auto name this"
        )
        
        path = save_recipe_to_file(recipe, file_path=None, is_global=False)
        
        assert path.name == "auto-name-recipe.yaml"


class TestRecipeFromFile:
    """Test Recipe.from_file with various scenarios"""

    def test_file_not_found(self):
        with pytest.raises(RecipeError) as exc_info:
            Recipe.from_file("/nonexistent/path/recipe.yaml")
        assert exc_info.value.code == "FILE_NOT_FOUND"

    def test_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()
            
            try:
                with pytest.raises(RecipeError) as exc_info:
                    Recipe.from_file(f.name)
                assert exc_info.value.code == "PARSE_ERROR"
            finally:
                os.unlink(f.name)

    def test_empty_content(self):
        with pytest.raises(RecipeError) as exc_info:
            Recipe.from_content("")
        assert "Empty recipe content" in exc_info.value.message


class TestRecipeRetryValidation:
    """Test retry configuration validation in Recipe"""

    def test_retry_validation_on_parse(self):
        content = """
version: 1.0.0
title: Invalid Retry
description: Testing invalid retry
instructions: Do something
retry:
    max_retries: -1
"""
        with pytest.raises(RecipeError) as exc_info:
            Recipe.from_content(content)
        assert "INVALID_RETRY_CONFIG" in exc_info.value.code


class TestRecipeRenderWithTemplateInheritance:
    """Test recipe rendering with template inheritance"""

    def test_render_with_inheritance_detection(self):
        content = """
{% extends "base.html" %}
Hello {{ name }}
"""
        assert uses_template_inheritance(content)

    def test_render_complex_template(self):
        recipe = Recipe(
            title="Complex Template",
            description="Testing complex templates",
            instructions="Process {{ data.value }} and {{ complex.var.name }}"
        )
        rendered = recipe.render({"data": {"value": "test"}, "complex": {"var": {"name": "nested"}}})
        assert "test" in rendered.instructions
        assert "nested" in rendered.instructions


class TestRecipeAuthorFromDict:
    """Test Author.from_dict"""

    def test_author_from_dict_with_contact(self):
        data = {"contact": "test@example.com"}
        author = Author.from_dict(data)
        assert author.contact == "test@example.com"

    def test_author_from_dict_with_metadata(self):
        data = {"metadata": "Some metadata"}
        author = Author.from_dict(data)
        assert author.metadata == "Some metadata"

    def test_author_from_dict_empty(self):
        author = Author.from_dict({})
        assert author.contact is None
        assert author.metadata is None


class TestRecipeSubRecipe:
    """Test SubRecipe functionality"""

    def test_subrecipe_creation(self):
        sub = SubRecipe(
            name="install_deps",
            path="install.yaml",
            values={"package": "requests"},
            sequential_when_repeated=True,
            description="Install dependencies"
        )
        assert sub.name == "install_deps"
        assert sub.sequential_when_repeated is True

    def test_subrecipe_to_dict(self):
        sub = SubRecipe(name="test", path="test.yaml")
        result = sub.to_dict()
        assert result["name"] == "test"
        assert result["path"] == "test.yaml"
        assert result["sequential_when_repeated"] is False

    def test_subrecipe_from_dict(self):
        data = {
            "name": "build",
            "path": "build.yaml",
            "values": {"target": "release"},
            "sequential_when_repeated": True
        }
        sub = SubRecipe.from_dict(data)
        assert sub.name == "build"
        assert sub.values["target"] == "release"


class TestRecipeSettingsFromDict:
    """Test Settings.from_dict"""

    def test_settings_from_dict(self):
        data = {
            "goose_provider": "openai",
            "goose_model": "gpt-4",
            "temperature": 0.7
        }
        settings = Settings.from_dict(data)
        assert settings.goose_provider == "openai"
        assert settings.goose_model == "gpt-4"
        assert settings.temperature == 0.7

    def test_settings_from_dict_partial(self):
        data = {"goose_model": "claude-3"}
        settings = Settings.from_dict(data)
        assert settings.goose_model == "claude-3"
        assert settings.goose_provider is None


class TestRecipeResponseFromDict:
    """Test Response.from_dict"""

    def test_response_from_dict(self):
        data = {"json_schema": {"type": "object", "properties": {"name": {"type": "string"}}}}
        response = Response.from_dict(data)
        assert response.json_schema is not None
        assert response.json_schema["type"] == "object"


class TestRecipeWithRetryFromDict:
    """Test Recipe.from_dict with retry configuration"""

    def test_recipe_with_retry_from_dict(self):
        data = {
            "title": "Retry Test",
            "description": "Testing retry",
            "instructions": "Retry on failure",
            "retry": {
                "max_retries": 5,
                "strategy": "linear_backoff",
                "initial_delay_ms": 2000
            }
        }
        recipe = Recipe.from_dict(data)
        assert recipe.retry is not None
        assert recipe.retry.max_retries == 5
        assert recipe.retry.strategy == RetryStrategy.LINEAR_BACKOFF
