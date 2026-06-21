# homebrew_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from backend.core.cache import cache_manager, cached, CacheKeys
from backend.core.utils import normalize_package_name, parse_version
import re
from enum import Enum
import hashlib
from dataclasses import dataclass
from collections import defaultdict
from backend.settings import (
    HOMEBREW_URL,
    HOMEBREW_API_URL,
    CACHE_TTL,
    CACHE_TTL_SHORT,
    RATE_LIMIT_delay,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    CONNECT_TIMEOUT,
    USER_AGENTS,
    RATE_LIMITS,
    RETRY_BACKOFF_FACTOR,
    RETRY_MAX_DELAY,
    ENABLE_CACHE,
    get_ecosystem_config
)

logger = logging.getLogger(__name__)

class PackageType(Enum):
    FORMULA = "formula"
    CASK = "cask"

class DependencyType(Enum):
    BUILD = "build"
    RUNTIME = "runtime"
    OPTIONAL = "optional"
    RECOMMENDED = "recommended"

@dataclass
class BrewDependency:
    """Represents a Homebrew dependency"""
    name: str
    dependency_type: DependencyType
    optional: bool = False
    
class HomebrewClient:
    def __init__(self, 
                 api_url: str = None,
                 cache_ttl: int = None,
                 max_retries: int = None,
                 rate_limit_delay: float = None,
                 timeout: int = None):
        # Get Homebrew-specific configuration
        homebrew_config = get_ecosystem_config('homebrew')
        
        # Use settings with ability to override
        self.api_url = (api_url or homebrew_config.get('api_url', HOMEBREW_API_URL)).rstrip('/')
        self.base_url = HOMEBREW_URL
        self.formula_api = f"{self.api_url}/formula"
        self.cask_api = f"{self.api_url}/cask"
        
        # Cache configuration
        self.cache_ttl = cache_ttl or homebrew_config.get('cache_ttl', CACHE_TTL)
        self.cache_enabled = ENABLE_CACHE
        
        # Rate limiting configuration
        self.max_retries = max_retries or MAX_RETRIES
        self.rate_limit_delay = rate_limit_delay or RATE_LIMIT_DELAY
        self.rate_limit = homebrew_config.get('rate_limit', RATE_LIMITS.get('homebrew', 600))
        self.retry_backoff_factor = RETRY_BACKOFF_FACTOR
        self.retry_max_delay = RETRY_MAX_DELAY
        
        # Timeout configuration
        self.timeout = timeout or REQUEST_TIMEOUT
        self.connect_timeout = CONNECT_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('homebrew', USER_AGENTS['default'])
        
        # Session and cache
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Tuple[Any, datetime]] = {} if self.cache_enabled else None
        
    async def __aenter__(self):
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if self._session is None or self._session.closed:
            timeout_config = aiohttp.ClientTimeout(
                total=self.timeout,
                connect=self.connect_timeout
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout_config,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json"
                }
            )
    
    async def close(self):
        """Close the HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached data if not expired"""
        if not self.cache_enabled or self._cache is None:
            return None
            
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return data
            else:
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: Any):
        """Set cache data"""
        if self.cache_enabled and self._cache is not None:
            self._cache[cache_key] = (data, datetime.now())
    
    async def _make_request(self, url: str, params: Optional[Dict] = None, 
                          headers: Optional[Dict] = None) -> Optional[Union[Dict, List]]:
        """Make HTTP request with retry logic"""
        await self._ensure_session()
        
        # Check cache
        cache_key = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        cached_data = await self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Rate limiting
        await asyncio.sleep(self.rate_limit_delay)
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with self._session.get(url, params=params, headers=headers) as response:
                    if response.status == 429:  # Rate limited
                        retry_after = int(response.headers.get('Retry-After', 60))
                        logger.warning(f"Rate limited, waiting {retry_after}s")
                        await asyncio.sleep(min(retry_after, self.retry_max_delay))
                        continue
                    
                    if response.status == 404:
                        return None
                    
                    if response.status != 200:
                        logger.error(f"HTTP {response.status} from {url}")
                        if attempt < self.max_retries - 1:
                            delay = min(self.retry_backoff_factor ** attempt, self.retry_max_delay)
                            await asyncio.sleep(delay)
                            continue
                        last_error = f"HTTP {response.status}"
                        break
                    
                    data = await response.json()
                    self._set_cache(cache_key, data)
                    return data
                    
            except asyncio.TimeoutError:
                logger.error(f"Timeout for {url}")
                last_error = "Timeout"
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                last_error = str(e)
            
            if attempt < self.max_retries - 1:
                delay = min(self.retry_backoff_factor ** attempt, self.retry_max_delay)
                await asyncio.sleep(delay)
        
        logger.error(f"All attempts failed. Last error: {last_error}")
        return None
    
    def package_exists(self, package_name: str, package_type: PackageType = PackageType.FORMULA) -> bool:
        """Quick check if package exists in Homebrew"""
        package_name = normalize_package_name(package_name)
        try:
            import requests
            if package_type == PackageType.FORMULA:
                url = f"{self.formula_api}/{package_name}.json"
            else:
                url = f"{self.cask_api}/{package_name}.json"
            response = requests.head(url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    async def search_packages(self, query: str, limit: int = 20,
                            package_type: Optional[PackageType] = None) -> List[Dict]:
        """Search for Homebrew packages (formulas and casks)"""
        query = normalize_package_name(query)
        results = []
        
        # Search both formulas and casks unless type is specified
        search_types = [package_type] if package_type else [PackageType.FORMULA, PackageType.CASK]
        
        for search_type in search_types:
            if search_type == PackageType.FORMULA:
                formulas = await self._search_formulas(query, limit // len(search_types))
                results.extend(formulas)
            else:
                casks = await self._search_casks(query, limit // len(search_types))
                results.extend(casks)
        
        # Sort by relevance (simple name matching for now)
        results.sort(key=lambda x: self._calculate_relevance_score(x['name'], query), reverse=True)
        
        return results[:limit]
    
    async def _search_formulas(self, query: str, limit: int) -> List[Dict]:
        """Search formulas"""
        # Get all formulas (Homebrew API provides full list)
        data = await self._make_request(f"{self.formula_api}.json")
        if not data:
            return []
        
        matches = []
        query_lower = query.lower()
        
        for formula in data:
            name = formula.get('name', '')
            desc = formula.get('desc', '')
            
            # Simple relevance matching
            if (query_lower in name.lower() or 
                query_lower in desc.lower()):
                
                matches.append({
                    'name': name,
                    'type': 'formula',
                    'description': desc,
                    'homepage': formula.get('homepage'),
                    'license': formula.get('license'),
                    'versions': formula.get('versions', {}),
                    'dependencies': formula.get('dependencies', []),
                    'build_dependencies': formula.get('build_dependencies', []),
                    'optional_dependencies': formula.get('optional_dependencies', []),
                    'recommended_dependencies': formula.get('recommended_dependencies', []),
                    'conflicts_with': formula.get('conflicts_with', []),
                    'caveats': formula.get('caveats'),
                    'installed': formula.get('installed', []),
                    'linked_keg': formula.get('linked_keg'),
                    'pinned': formula.get('pinned', False),
                    'outdated': formula.get('outdated', False)
                })
        
        return matches[:limit]
    
    async def _search_casks(self, query: str, limit: int) -> List[Dict]:
        """Search casks"""
        # Get all casks
        data = await self._make_request(f"{self.cask_api}.json")
        if not data:
            return []
        
        matches = []
        query_lower = query.lower()
        
        for cask in data:
            token = cask.get('token', '')
            name = cask.get('name', [''])[0] if cask.get('name') else ''
            desc = cask.get('desc', '')
            
            # Simple relevance matching
            if (query_lower in token.lower() or 
                query_lower in name.lower() or 
                query_lower in desc.lower()):
                
                matches.append({
                    'name': token,
                    'type': 'cask',
                    'full_name': name,
                    'description': desc,
                    'homepage': cask.get('homepage'),
                    'version': cask.get('version'),
                    'installed': cask.get('installed'),
                    'outdated': cask.get('outdated', False),
                    'sha256': cask.get('sha256'),
                    'artifacts': cask.get('artifacts', []),
                    'caveats': cask.get('caveats'),
                    'depends_on': cask.get('depends_on', {}),
                    'conflicts_with': cask.get('conflicts_with', [])
                })
        
        return matches[:limit]
    
    def _calculate_relevance_score(self, name: str, query: str) -> float:
        """Calculate relevance score for search results"""
        name_lower = name.lower()
        query_lower = query.lower()
        
        # Exact match gets highest score
        if name_lower == query_lower:
            return 1.0
        
        # Starts with query gets high score
        if name_lower.startswith(query_lower):
            return 0.8
        
        # Contains query gets medium score
        if query_lower in name_lower:
            return 0.6
        
        # No match gets low score
        return 0.1
    
    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str, 
                                   package_type: PackageType = PackageType.FORMULA) -> Optional[Dict]:
        """Get comprehensive package information"""
        package_name = normalize_package_name(package_name)
        
        if package_type == PackageType.FORMULA:
            return await self._get_formula_info(package_name)
        else:
            return await self._get_cask_info(package_name)
    
    def get_package_info(self, package_name: str, package_type: PackageType = PackageType.FORMULA) -> Dict:
        """Synchronous wrapper for get_package_info_async"""
        package_name = normalize_package_name(package_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_package_info_async(package_name, package_type))
        finally:
            loop.close()
    
    async def _get_formula_info(self, formula_name: str) -> Optional[Dict]:
        """Get formula information"""
        url = f"{self.formula_api}/{formula_name}.json"
        data = await self._make_request(url)
        
        if not data:
            return None
        
        return {
            'name': data.get('name'),
            'type': 'formula',
            'full_name': data.get('full_name'),
            'tap': data.get('tap'),
            'oldname': data.get('oldname'),
            'aliases': data.get('aliases', []),
            'versioned_formulae': data.get('versioned_formulae', []),
            'description': data.get('desc'),
            'license': data.get('license'),
            'homepage': data.get('homepage'),
            'versions': data.get('versions', {}),
            'urls': data.get('urls', {}),
            'revision': data.get('revision', 0),
            'version_scheme': data.get('version_scheme', 0),
            'bottle': data.get('bottle', {}),
            'keg_only': data.get('keg_only', False),
            'keg_only_reason': data.get('keg_only_reason'),
            'options': data.get('options', []),
            'build_dependencies': data.get('build_dependencies', []),
            'dependencies': data.get('dependencies', []),
            'optional_dependencies': data.get('optional_dependencies', []),
            'recommended_dependencies': data.get('recommended_dependencies', []),
            'test_dependencies': data.get('test_dependencies', []),
            'requirements': data.get('requirements', []),
            'conflicts_with': data.get('conflicts_with', []),
            'caveats': data.get('caveats'),
            'installed': data.get('installed', []),
            'linked_keg': data.get('linked_keg'),
            'pinned': data.get('pinned', False),
            'outdated': data.get('outdated', False),
            'deprecated': data.get('deprecated', False),
            'deprecation_date': data.get('deprecation_date'),
            'deprecation_reason': data.get('deprecation_reason'),
            'disabled': data.get('disabled', False),
            'disable_date': data.get('disable_date'),
            'disable_reason': data.get('disable_reason'),
            'uses_from_macos': data.get('uses_from_macos', []),
            'head': data.get('head'),
            'pour_bottle_only_if': data.get('pour_bottle_only_if'),
            'link_overwrite': data.get('link_overwrite', []),
            'system_requirements': self._extract_formula_system_requirements(data)
        }
    
    async def _get_cask_info(self, cask_name: str) -> Optional[Dict]:
        """Get cask information"""
        url = f"{self.cask_api}/{cask_name}.json"
        data = await self._make_request(url)
        
        if not data:
            return None
        
        return {
            'name': data.get('token'),
            'type': 'cask',
            'full_name': data.get('name', []),
            'tap': data.get('tap'),
            'description': data.get('desc'),
            'homepage': data.get('homepage'),
            'version': data.get('version'),
            'sha256': data.get('sha256'),
            'url': data.get('url'),
            'appcast': data.get('appcast'),
            'auto_updates': data.get('auto_updates', False),
            'artifacts': data.get('artifacts', []),
            'caveats': data.get('caveats'),
            'depends_on': data.get('depends_on', {}),
            'conflicts_with': data.get('conflicts_with', []),
            'container': data.get('container'),
            'installed': data.get('installed'),
            'outdated': data.get('outdated', False),
            'deprecated': data.get('deprecated', False),
            'deprecation_date': data.get('deprecation_date'),
            'deprecation_reason': data.get('deprecation_reason'),
            'disabled': data.get('disabled', False),
            'disable_date': data.get('disable_date'),
            'disable_reason': data.get('disable_reason'),
            'languages': data.get('languages', []),
            'system_requirements': self._extract_cask_system_requirements(data)
        }
    
    async def get_dependencies(self, package_name: str, 
                             package_type: PackageType = PackageType.FORMULA,
                             include_optional: bool = True,
                             include_build: bool = True) -> Dict[str, List[str]]:
        """Get package dependencies"""
        package_name = normalize_package_name(package_name)
        
        info = await self.get_package_info_async(package_name, package_type)
        if not info:
            return {}
        
        dependencies = {
            'runtime': info.get('dependencies', []),
            'build': info.get('build_dependencies', []) if include_build else [],
            'optional': info.get('optional_dependencies', []) if include_optional else [],
            'recommended': info.get('recommended_dependencies', []),
            'test': info.get('test_dependencies', [])
        }
        
        # For casks, dependencies are in 'depends_on'
        if package_type == PackageType.CASK:
            depends_on = info.get('depends_on', {})
            dependencies.update({
                'formula': depends_on.get('formula', []),
                'cask': depends_on.get('cask', []),
                'macos': depends_on.get('macos', {})
            })
        
        return dependencies
    
    def _extract_formula_system_requirements(self, data: Dict) -> Dict[str, Any]:
        """Extract system requirements for formulas"""
        requirements = {
            'macos_version': None,
            'arch': [],
            'xcode': None,
            'java': None,
            'uses_from_macos': data.get('uses_from_macos', []),
            'keg_only': data.get('keg_only', False),
            'pour_bottle_only_if': data.get('pour_bottle_only_if')
        }
        
        # Extract from requirements array
        for req in data.get('requirements', []):
            if isinstance(req, dict):
                if 'name' in req:
                    name = req['name']
                    if name == 'xcode':
                        requirements['xcode'] = req.get('version')
                    elif name == 'java':
                        requirements['java'] = req.get('version')
                    elif name == 'arch':
                        requirements['arch'] = req.get('specs', [])
        
        # Extract macOS version from bottle
        bottle = data.get('bottle', {})
        if bottle and 'stable' in bottle:
            stable = bottle['stable']
            if 'files' in stable:
                # Get supported macOS versions from bottle files
                macos_versions = []
                for file_key in stable['files'].keys():
                    if file_key.startswith('monterey') or file_key.startswith('big_sur') or file_key.startswith('catalina'):
                        macos_versions.append(file_key)
                
                if macos_versions:
                    requirements['macos_version'] = macos_versions
        
        return requirements
    
    def _extract_cask_system_requirements(self, data: Dict) -> Dict[str, Any]:
        """Extract system requirements for casks"""
        requirements = {
            'macos_version': None,
            'arch': None
        }
        
        depends_on = data.get('depends_on', {})
        
        # Extract macOS version requirement
        if 'macos' in depends_on:
            macos_req = depends_on['macos']
            if isinstance(macos_req, dict):
                requirements['macos_version'] = macos_req
            else:
                requirements['macos_version'] = {'min': macos_req}
        
        # Extract architecture requirement
        if 'arch' in depends_on:
            requirements['arch'] = depends_on['arch']
        
        return requirements
    
    async def check_compatibility(self, package_name: str, 
                                package_type: PackageType = PackageType.FORMULA,
                                system_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Check if package is compatible with system"""
        package_name = normalize_package_name(package_name)
        
        pkg_data = await self.get_package_info_async(package_name, package_type)
        if not pkg_data:
            return {
                'compatible': False,
                'errors': ['Package not found'],
                'warnings': []
            }
        
        errors = []
        warnings = []
        
        if system_info:
            # Check macOS version
            sys_reqs = pkg_data.get('system_requirements', {})
            required_macos = sys_reqs.get('macos_version')
            system_macos = system_info.get('macos_version')
            
            if required_macos and system_macos:
                if not self._check_macos_compatibility(system_macos, required_macos):
                    errors.append(f"Requires macOS {required_macos}, but system has {system_macos}")
            
            # Check architecture
            required_arch = sys_reqs.get('arch')
            system_arch = system_info.get('arch')
            
            if required_arch and system_arch:
                if system_arch not in required_arch:
                    errors.append(f"Requires architecture {required_arch}, but system has {system_arch}")
        
        # Check if deprecated
        if pkg_data.get('deprecated'):
            reason = pkg_data.get('deprecation_reason', 'No reason provided')
            warnings.append(f"Package is deprecated: {reason}")
        
        # Check if disabled
        if pkg_data.get('disabled'):
            reason = pkg_data.get('disable_reason', 'No reason provided')
            errors.append(f"Package is disabled: {reason}")
        
        # Check for conflicts
        conflicts = pkg_data.get('conflicts_with', [])
        if conflicts:
            warnings.append(f"May conflict with: {', '.join(conflicts)}")
        
        # Check if keg-only (for formulas)
        if package_type == PackageType.FORMULA and pkg_data.get('keg_only'):
            reason = pkg_data.get('keg_only_reason', {})
            if reason:
                warnings.append(f"Keg-only: {reason.get('reason', 'Unknown reason')}")
        
        return {
            'compatible': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'requirements': pkg_data.get('system_requirements', {}),
            'caveats': pkg_data.get('caveats')
        }
    
    def _check_macos_compatibility(self, system_version: str, required: Union[str, Dict, List]) -> bool:
        """Check macOS version compatibility"""
        if isinstance(required, str):
            # Simple version comparison
            return system_version >= required
        elif isinstance(required, dict):
            # Version range
            min_version = required.get('min')
            max_version = required.get('max')
            
            if min_version and system_version < min_version:
                return False
            if max_version and system_version > max_version:
                return False
            
            return True
        elif isinstance(required, list):
            # List of supported versions
            return system_version in required
        
        return True

# Example usage
async def example_usage():
    async with HomebrewClient() as client:
        # Search for packages
        results = await client.search_packages("python", limit=5)
        
        # Get formula info
        formula_info = await client.get_package_info_async("python@3.11", PackageType.FORMULA)
        
        # Get cask info
        cask_info = await client.get_package_info_async("visual-studio-code", PackageType.CASK)
        
        # Check compatibility
        compat = await client.check_compatibility(
            "python@3.11",
            PackageType.FORMULA,
            {
                'macos_version': '13.0',
                'arch': 'arm64'
            }
        )
        
        print(f"Formula: {formula_info['name'] if formula_info else 'Not found'}")
        print(f"Cask: {cask_info['name'] if cask_info else 'Not found'}")
        print(f"Compatible: {compat['compatible']}")

if __name__ == "__main__":
    asyncio.run(example_usage())