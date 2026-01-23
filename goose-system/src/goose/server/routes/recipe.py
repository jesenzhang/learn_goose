"""
Server Routes - Recipe Management

API endpoints for recipe management:
- List recipes
- Get recipe by ID
- Save recipe
- Validate recipe

Reference: goose-rs/crates/goose-server/src/routes/recipe.rs
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from .router import ServerRouter
from ...recipe import Recipe, RecipeLoader, save_recipe_to_file

router = APIRouter()


class RecipeListResponse(BaseModel):
    """Response for listing recipes"""
    recipes: List[Dict[str, Any]]


class RecipeResponse(BaseModel):
    """Response for a single recipe"""
    recipe: Dict[str, Any]


class SaveRecipeRequest(BaseModel):
    """Request to save a recipe"""
    recipe: Dict[str, Any]
    file_path: Optional[str] = Field(default=None, description="Optional file path")
    is_global: bool = Field(default=True, description="Save to global recipes directory")


class ValidateRecipeResponse(BaseModel):
    """Response for recipe validation"""
    valid: bool
    errors: List[str] = []


class RecipeParameter(BaseModel):
    """Recipe parameter definition"""
    key: str
    input_type: str = "string"
    requirement: str = "optional"
    description: str = ""
    default: Optional[str] = None
    options: Optional[List[str]] = None


class RecipeModel(BaseModel):
    """Recipe model for API"""
    version: str = "1.0.0"
    title: str = ""
    description: str = ""
    instructions: Optional[str] = None
    prompt: Optional[str] = None
    activities: Optional[List[str]] = None
    parameters: Optional[List[RecipeParameter]] = None


@router.get("/recipes", response_model=RecipeListResponse)
async def list_recipes() -> RecipeListResponse:
    """
    List all available recipes
    
    Returns recipes from all configured recipe directories.
    """
    loader = RecipeLoader()
    recipes = loader.list_recipes()
    
    return RecipeListResponse(recipes=recipes)


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: str) -> RecipeResponse:
    """
    Get a recipe by ID or path
    """
    loader = RecipeLoader()
    recipe = loader.load(recipe_id)
    
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe {recipe_id} not found"
        )
    
    return RecipeResponse(
        recipe=recipe.to_dict()
    )


@router.post("/recipes", response_model=Dict[str, Any])
async def save_recipe(request: SaveRecipeRequest) -> Dict[str, Any]:
    """
    Save a recipe to file
    
    Creates or updates a recipe file.
    """
    recipe = Recipe.from_dict(request.recipe)
    
    path = save_recipe_to_file(
        recipe=recipe,
        file_path=request.file_path,
        is_global=request.is_global,
    )
    
    return {
        "status": "ok",
        "path": str(path),
        "recipe": recipe.to_dict()
    }


@router.post("/recipes/validate", response_model=ValidateRecipeResponse)
async def validate_recipe(recipe: RecipeModel) -> ValidateRecipeResponse:
    """
    Validate a recipe
    
    Checks if the recipe has all required fields and valid configuration.
    """
    recipe_dict = recipe.model_dump(exclude_none=True)
    full_recipe = Recipe.from_dict(recipe_dict)
    
    errors = full_recipe.validate()
    
    return ValidateRecipeResponse(
        valid=len(errors) == 0,
        errors=errors,
    )


@router.get("/recipes/search")
async def search_recipes(
    query: str = Query(..., description="Search query")
) -> RecipeListResponse:
    """
    Search recipes by title or description
    """
    loader = RecipeLoader()
    results = loader.search(query)
    
    return RecipeListResponse(
        recipes=[r.to_dict() for r in results]
    )


def routes() -> ServerRouter:
    """Create router with all recipe routes"""
    return ServerRouter(router)
