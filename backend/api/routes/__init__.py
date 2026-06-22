#routes/__init__.py
"""
API Routes Package

This package contains all API route definitions organized by domain.
"""

from . import packages
from . import system

# Import specific route functions if needed for testing
from .packages import (
    get_package_info,
    resolve_dependencies,
    export_configuration,
    search_packages,
    get_package_versions,
    get_package_dependencies,
    compare_packages
)

from .system import get_system_info

__all__ = [
    # Route modules
    "packages",
    "system",
    
    # Package routes
    "get_package_info",
    "resolve_dependencies",
    "export_configuration",
    "search_packages",
    "get_package_versions",
    "get_package_dependencies",
    "compare_packages",
    
    # System routes
    "get_system_info",
    "check_system_compatibility",
]