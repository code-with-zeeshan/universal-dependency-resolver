from . import auth as auth_routes
from . import check as check_routes
from . import completion as completion_routes
from . import index as index_routes
from . import lock as lock_routes
from . import packages, scan, system
from . import sbom as sbom_routes

__all__ = [
    "auth_routes",
    "check_routes",
    "completion_routes",
    "index_routes",
    "lock_routes",
    "packages",
    "sbom_routes",
    "scan",
    "system",
]
