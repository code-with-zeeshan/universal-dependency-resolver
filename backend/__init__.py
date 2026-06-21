#backend/__init__.py
"""
Universal Dependency Resolver Backend Package

This package contains all backend components including API, core logic,
data sources, and database operations.
"""

# Version information
__version__ = "1.0.0"
__author__ = "Universal Dependency Resolver Team"
__email__ = "team@udr.example.com"

# Import key components for easier access
from .settings import settings, get_ecosystem_config
from .core import (
    DataAggregator,
    ConflictResolver,
    SystemScanner,
    ExportGenerator
)
from .database import (
    CompatibilityDB,
    init_db,
    get_db
)

# API components
from .api import app

# Package metadata
__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__email__",
    
    # Settings
    "settings",
    "get_ecosystem_config",
    
    # Core components
    "DataAggregator",
    "ConflictResolver", 
    "SystemScanner",
    "ExportGenerator",
    
    # Database
    "CompatibilityDB",
    "init_db",
    "get_db",
    
    # API
    "app"
]

# Initialize logging
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())