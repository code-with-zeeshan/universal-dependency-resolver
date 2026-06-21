# packagist_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from backend.core.utils import normalize_package_name, parse_version
import re
from backend.core.cache import cache_manager, cached, CacheKeys
from enum import Enum
import hashlib
from dataclasses import dataclass
from collections import defaultdict
from backend.settings import (
    PACKAGIST_URL,
    PACKAGIST_API_URL,
    CACHE_TTL,
    CACHE_TTL_SHORT,
    RATE_LIMIT_DELAY,
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

class DependencyType(Enum):
    REQUIRE = "require"
    REQUIRE_DEV = "require-dev"
    CONFLICT = "conflict"
    REPLACE = "replace"
    PROVIDE = "provide"
    SUGGEST = "suggest"

@dataclass
class ComposerVersionRequirement:
    """Represents a Composer version requirement with ^ and ~ operators"""
    raw: str
    operator: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None
    
class PackagistClient:
    def __init__(self, 
                 api_url: str = None,
                 cache_ttl: int = None,
                 max_retries: int = None,
                 rate_limit_delay: float = None,
                 timeout: int = None):
        # Get Packagist-specific configuration
        packagist_config = get_ecosystem_config('packagist')
        
        # Use settings with ability to override
        self.api_url = (api_url or packagist_config.get('api_url', PACKAGIST_API_URL)).rstrip('/')
        self.base_url = PACKAGIST_URL
        self.search_url = f"{PACKAGIST_URL}/search.json"
        
        # Cache configuration
        self.cache_ttl = cache_ttl or packagist_config.get('cache_ttl', CACHE_TTL)
        self.cache_enabled = ENABLE_CACHE
        
        # Rate limiting configuration
        self.max_retries = max_retries or MAX_RETRIES
        self.rate_limit_delay = rate_limit_delay or RATE_LIMIT_DELAY
        self.rate_limit = packagist_config.get('rate_limit', RATE_LIMITS.get('packagist', 600))
        self.retry_backoff_factor = RETRY_BACKOFF_FACTOR
        self.retry_max_delay = RETRY_MAX_DELAY
        
        # Timeout configuration
        self.timeout = timeout or REQUEST_TIMEOUT
        self.connect_timeout = CONNECT_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('packagist', USER_AGENTS['default'])
        
        # Session and cache
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Tuple[Any, datetime]] = {} if self.cache_enabled else None
        self._version_cache: Dict[str, ComposerVersionRequirement] = {}
        
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
                          headers: Optional[Dict] = None) -> Optional[Dict]:
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
    
    def package_exists(self, package_name: str) -> bool:
        """Quick check if package exists on Packagist"""
        package_name = normalize_package_name(package_name)
        try:
            import requests
            response = requests.head(f"{self.api_url}/packages/{package_name}.json", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    async def search_packages(self, query: str, limit: int = 20,
                            package_type: Optional[str] = None,
                            tags: Optional[List[str]] = None) -> List[Dict]:
        """Search for PHP packages on Packagist"""
        query = normalize_package_name(query)
        
        params = {
            'q': query,
            'per_page': min(limit, 100)  # API max per page
        }
        
        if package_type:
            params['type'] = package_type
        
        if tags:
            params['tags'] = ','.join(tags)
        
        data = await self._make_request(self.search_url, params=params)
        if not data or 'results' not in data:
            return []
        
        results = []
        for package in data['results']:
            result = {
                'name': package.get('name'),
                'description': package.get('description'),
                'url': package.get('url'),
                'repository': package.get('repository'),
                'downloads': package.get('downloads'),
                'favers': package.get('favers'),
                'abandoned': package.get('abandoned', False),
                'replacement': package.get('replacement')
            }
            results.append(result)
        
        return results
    
    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str, 
                                   include_versions: bool = True) -> Optional[Dict]:
        """Get comprehensive package information"""
        package_name = normalize_package_name(package_name)
        
        # Get package data from Packagist
        url = f"{self.api_url}/packages/{package_name}.json"
        data = await self._make_request(url)
        if not data or 'package' not in data:
            return None
        
        package_data = data['package']
        
        # Process versions
        versions_info = []
        latest_version = None
        latest_data = None
        
        for version, version_data in package_data.get('versions', {}).items():
            if self._is_valid_version(version):
                version_info = self._process_version_data(version_data)
                if version_info:
                    versions_info.append(version_info)
                    if not latest_version or self._is_newer_version(version, latest_version):
                        latest_version = version
                        latest_data = version_data
        
        # Sort versions
        versions_info.sort(
            key=lambda x: parse_version(x['version']) or parse_version('0.0.0'),
            reverse=True
        )
        
        # Get download statistics
        downloads = await self._get_download_stats(package_name)
        
        # Build comprehensive info
        info = {
            'name': package_data.get('name'),
            'description': package_data.get('description'),
            'type': package_data.get('type', 'library'),
            'repository': package_data.get('repository'),
            'homepage': package_data.get('homepage'),
            'language': package_data.get('language'),
            'abandoned': package_data.get('abandoned', False),
            'replacement': package_data.get('replacement'),
            'downloads': downloads,
            'dependents': package_data.get('dependents', 0),
            'suggesters': package_data.get('suggesters', 0),
            'github_stars': package_data.get('github_stars'),
            'github_watchers': package_data.get('github_watchers'),
            'github_forks': package_data.get('github_forks'),
            'github_open_issues': package_data.get('github_open_issues'),
            'versions': versions_info if include_versions else []
        }
        
        # Add latest version info
        if latest_data:
            info.update({
                'version': latest_version,
                'time': latest_data.get('time'),
                'authors': latest_data.get('authors', []),
                'keywords': latest_data.get('keywords', []),
                'license': latest_data.get('license', []),
                'support': latest_data.get('support', {}),
                'funding': latest_data.get('funding', []),
                'dependencies': self._extract_dependencies(latest_data),
                'system_requirements': self._extract_system_requirements(latest_data),
                'autoload': latest_data.get('autoload', {}),
                'bin': latest_data.get('bin', []),
                'scripts': latest_data.get('scripts', {}),
                'extra': latest_data.get('extra', {})
            })
        
        return info
    
    def get_package_info(self, package_name: str) -> Dict:
        """Synchronous wrapper for get_package_info_async"""
        package_name = normalize_package_name(package_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_package_info_async(package_name))
        finally:
            loop.close()
    
    async def get_package_version(self, package_name: str, version: str) -> Optional[Dict]:
        """Get specific version information"""
        package_name = normalize_package_name(package_name)
        
        info = await self.get_package_info_async(package_name, include_versions=True)
        if not info or not info.get('versions'):
            return None
        
        for v in info['versions']:
            if v.get('version') == version:
                return v
        
        return None
    
    async def get_versions(self, package_name: str, 
                         include_dev: bool = True,
                         include_abandoned: bool = False) -> List[Dict]:
        """Get all versions with filtering options"""
        package_name = normalize_package_name(package_name)
        
        info = await self.get_package_info_async(package_name, include_versions=True)
        if not info or not info.get('versions'):
            return []
        
        versions = []
        for v in info['versions']:
            # Filter dev versions
            if not include_dev and self._is_dev_version(v.get('version', '')):
                continue
            
            versions.append(v)
        
        return versions
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None,
                             include_dev: bool = True) -> Dict[str, Any]:
        """Get package dependencies"""
        package_name = normalize_package_name(package_name)
        
        if version:
            pkg_data = await self.get_package_version(package_name, version)
        else:
            pkg_data = await self.get_package_info_async(package_name, include_versions=False)
        
        if not pkg_data:
            return {}
        
        dependencies = pkg_data.get('dependencies', {})
        
        if not include_dev and 'require-dev' in dependencies:
            del dependencies['require-dev']
        
        return dependencies
    
    async def _get_download_stats(self, package_name: str) -> Dict[str, int]:
        """Get download statistics"""
        package_name = normalize_package_name(package_name)
        try:
            url = f"{self.api_url}/downloads/{package_name}.json"
            data = await self._make_request(url)
            if data and 'package' in data:
                return data['package']
        except:
            pass
        return {'daily': 0, 'monthly': 0, 'total': 0}
    
    def _process_version_data(self, version_data: Dict) -> Optional[Dict]:
        """Process version data into standardized format"""
        version = version_data.get('version')
        if not version or not self._is_valid_version(version):
            return None
        
        return {
            'version': version,
            'version_normalized': version_data.get('version_normalized'),
            'stability': version_data.get('stability'),
            'time': version_data.get('time'),
            'description': version_data.get('description'),
            'keywords': version_data.get('keywords', []),
            'license': version_data.get('license', []),
            'authors': version_data.get('authors', []),
            'support': version_data.get('support', {}),
            'funding': version_data.get('funding', []),
            'dependencies': self._extract_dependencies(version_data),
            'system_requirements': self._extract_system_requirements(version_data),
            'autoload': version_data.get('autoload', {}),
            'bin': version_data.get('bin', []),
            'notification_url': version_data.get('notification-url'),
            'source': version_data.get('source', {}),
            'dist': version_data.get('dist', {})
        }
    
    def _extract_dependencies(self, version_data: Dict) -> Dict[str, Dict]:
        """Extract dependencies from version data"""
        dependencies = {}
        
        # Standard dependency types in Composer
        dep_types = ['require', 'require-dev', 'conflict', 'replace', 'provide', 'suggest']
        
        for dep_type in dep_types:
            if dep_type in version_data:
                dependencies[dep_type] = version_data[dep_type]
        
        return dependencies
    
    def _extract_system_requirements(self, version_data: Dict) -> Dict[str, Any]:
        """Extract system requirements"""
        requirements = {
            'php': None,
            'extensions': [],
            'platform': {},
            'composer': None
        }
        
        # Extract PHP version requirement
        require = version_data.get('require', {})
        if 'php' in require:
            requirements['php'] = require['php']
        
        # Extract PHP extensions
        for req_name, req_version in require.items():
            if req_name.startswith('ext-'):
                ext_name = req_name[4:]  # Remove 'ext-' prefix
                requirements['extensions'].append({
                    'name': ext_name,
                    'version': req_version
                })
        
        # Extract platform requirements
        platform_requires = {}
        for req_name, req_version in require.items():
            if req_name in ['lib-openssl', 'lib-pcre', 'lib-iconv', 'lib-icu', 'lib-libxml']:
                platform_requires[req_name] = req_version
        
        requirements['platform'] = platform_requires
        
        # Extract Composer version requirement
        if 'composer' in require:
            requirements['composer'] = require['composer']
        
        return requirements
    
    def _is_valid_version(self, version: str) -> bool:
        """Check if version string is valid"""
        if not version:
            return False
        
        # Skip dev branches
        if version.startswith('dev-'):
            return False
        
        # Check if parseable
        return parse_version(version) is not None
    
    def _is_dev_version(self, version: str) -> bool:
        """Check if version is a development version"""
        return version.startswith('dev-') or '-dev' in version
    
    def _is_newer_version(self, version1: str, version2: str) -> bool:
        """Check if version1 is newer than version2"""
        v1 = parse_version(version1)
        v2 = parse_version(version2)
        
        if v1 and v2:
            return v1 > v2
        
        return False
    
    def _parse_composer_version_requirement(self, spec: str) -> ComposerVersionRequirement:
        """Parse Composer version requirement with ^ and ~ operators"""
        if spec in self._version_cache:
            return self._version_cache[spec]
        
        req = ComposerVersionRequirement(raw=spec)
        
        # Handle Composer-specific patterns
        patterns = {
            r'^\^(\d+)\.(\d+)\.(\d+)': lambda m: {
                'operator': '^',
                'major': int(m[1]),
                'minor': int(m[2]),
                'patch': int(m[3])
            },
            r'^~(\d+)\.(\d+)\.(\d+)': lambda m: {
                'operator': '~',
                'major': int(m[1]),
                'minor': int(m[2]),
                'patch': int(m[3])
            },
            r'^>=(\d+)\.(\d+)\.(\d+)': lambda m: {
                'operator': '>=',
                'major': int(m[1]),
                'minor': int(m[2]),
                'patch': int(m[3])
            },
            r'^(\d+)\.(\d+)\.(\d+)$': lambda m: {
                'major': int(m[1]),
                'minor': int(m[2]),
                'patch': int(m[3])
            }
        }
        
        for pattern, handler in patterns.items():
            match = re.match(pattern, spec.strip())
            if match:
                for key, value in handler(match).items():
                    setattr(req, key, value)
                break
        
        self._version_cache[spec] = req
        return req
    
    async def check_compatibility(self, package_name: str, version: str,
                                system_info: Dict[str, Any]) -> Dict[str, Any]:
        """Check if package is compatible with system"""
        package_name = normalize_package_name(package_name)
        
        pkg_data = await self.get_package_version(package_name, version)
        if not pkg_data:
            return {
                'compatible': False,
                'errors': ['Package version not found'],
                'warnings': []
            }
        
        errors = []
        warnings = []
        
        # Check PHP version
        php_requirement = pkg_data.get('system_requirements', {}).get('php')
        if php_requirement and 'php_version' in system_info:
            if not self._check_php_compatibility(system_info['php_version'], php_requirement):
                errors.append(f"Requires PHP {php_requirement}, but system has {system_info['php_version']}")
        
        # Check PHP extensions
        required_extensions = pkg_data.get('system_requirements', {}).get('extensions', [])
        system_extensions = system_info.get('php_extensions', [])
        
        for ext in required_extensions:
            ext_name = ext['name']
            if ext_name not in system_extensions:
                errors.append(f"Required PHP extension missing: {ext_name}")
        
        # Check Composer version
        composer_requirement = pkg_data.get('system_requirements', {}).get('composer')
        if composer_requirement and 'composer_version' in system_info:
            if not self._check_composer_compatibility(system_info['composer_version'], composer_requirement):
                warnings.append(f"Recommends Composer {composer_requirement}")
        
        # Check if package is abandoned
        if pkg_data.get('abandoned', False):
            replacement = pkg_data.get('replacement')
            if replacement:
                warnings.append(f"Package is abandoned. Consider using {replacement} instead.")
            else:
                warnings.append("Package is abandoned and has no recommended replacement.")
        
        return {
            'compatible': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'requirements': pkg_data.get('system_requirements', {})
        }
    
    def _check_php_compatibility(self, system_version: str, required: str) -> bool:
        """Check PHP version compatibility with Composer operators"""
        req = self._parse_composer_version_requirement(required)
        system_v = parse_version(system_version)
        
        if not system_v or not req.major:
            return True
        
        if req.operator == '^':
            # Caret: compatible within major version
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            max_v = parse_version(f"{req.major + 1}.0.0")
            return min_v <= system_v < max_v
        elif req.operator == '~':
            # Tilde: compatible within minor version
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            max_v = parse_version(f"{req.major}.{req.minor + 1}.0")
            return min_v <= system_v < max_v
        elif req.operator == '>=':
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            return system_v >= min_v
        else:
            # Exact match
            exact_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            return system_v == exact_v
    
    def _check_composer_compatibility(self, system_version: str, required: str) -> bool:
        """Check Composer version compatibility"""
        return self._check_php_compatibility(system_version, required)

# Example usage
async def example_usage():
    async with PackagistClient() as client:
        # Search for packages
        results = await client.search_packages("symfony", limit=5)
        
        # Get comprehensive package info
        info = await client.get_package_info_async("symfony/console", include_versions=True)
        
        # Get specific version
        version_info = await client.get_package_version("symfony/console", "v6.0.0")
        
        # Check compatibility
        compat = await client.check_compatibility(
            "symfony/console",
            "v6.0.0",
            {
                'php_version': '8.1.0',
                'php_extensions': ['json', 'mbstring', 'ctype'],
                'composer_version': '2.4.0'
            }
        )
        
        print(f"Package: {info['name']}")
        print(f"Latest version: {info['version']}")
        print(f"Compatible: {compat['compatible']}")

if __name__ == "__main__":
    asyncio.run(example_usage())