from .accounts import router as accounts_router
from .eaters import router as eaters_router
from .ingredients import router as ingredients_router
from .instance import router as instance_router
from .pantry import router as pantry_router
from .plans import router as plans_router
from .preferences import router as preferences_router
from .recipes import router as recipes_router
from .setup import router as setup_router
from .status import router as status_router

__all__ = [
    "accounts_router",
    "eaters_router",
    "ingredients_router",
    "instance_router",
    "pantry_router",
    "plans_router",
    "preferences_router",
    "recipes_router",
    "setup_router",
    "status_router",
]
