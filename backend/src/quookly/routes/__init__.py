from .accounts import router as accounts_router
from .eaters import router as eaters_router
from .ingredients import router as ingredients_router
from .recipes import router as recipes_router
from .status import router as status_router

__all__ = [
    "accounts_router",
    "eaters_router",
    "ingredients_router",
    "recipes_router",
    "status_router",
]
