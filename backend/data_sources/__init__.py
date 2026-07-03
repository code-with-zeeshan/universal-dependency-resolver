"""Module docstring."""

# In data_sources/__init__.py
from .apk_client import APKClient
from .apt_client import APTClient
from .cocoapods_client import CocoaPodsClient
from .conda_client import CondaClient
from .crates_client import CratesClient
from .documentation_scraper import DocumentationScraper
from .gomodules_client import GoModulesClient
from .homebrew_client import HomebrewClient
from .maven_client import MavenClient
from .npm_client import NPMClient
from .nuget_client import NuGetClient
from .packagist_client import PackagistClient
from .pypi_client import PyPIClient
from .rubygems_client import RubyGemsClient
from .utils import safe_data_source_call

__all__ = [
    "APKClient",
    "APTClient",
    "CocoaPodsClient",
    "CondaClient",
    "CratesClient",
    "DocumentationScraper",
    "GoModulesClient",
    "HomebrewClient",
    "MavenClient",
    "NPMClient",
    "NuGetClient",
    "PackagistClient",
    "PyPIClient",
    "RubyGemsClient",
    "safe_data_source_call",
]
