# rubygems_client.py
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
    RUBYGEMS_URL,
    RUBYGEMS_API_URL, 
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
    RUNTIME = "runtime"
    DEVELOPMENT = "development"

@dataclass
class RubyVersionRequirement:
    """Represents a Ruby version requirement (pessimistic ~>, >=, etc.)"""
    raw: str
    operator: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None
    
class RubyGemsClient:
    def __init__(self, 
                 api_url: str = None,
                 cache_ttl: int = None,
                 max_retries: int = None,
                 rate_limit_delay: float = None,
                 timeout: int = None):
        # Get RubyGems-specific configuration
        rubygems_config = get_ecosystem_config('rubygems')
        
        # Use settings with ability to override
        self.api_url = (api_url or rubygems_config.get('api_url', RUBYGEMS_API_URL)).rstrip('/')
        self.base_url = RUBYGEMS_URL
        
        # Cache configuration
        self.cache_ttl = cache_ttl or rubygems_config.get('cache_ttl', CACHE_TTL)
        self.cache_enabled = ENABLE_CACHE
        
        # Rate limiting configuration
        self.max_retries = max_retries or MAX_RETRIES
        self.rate_limit_delay = rate_limit_delay or RATE_LIMIT_DELAY
        self.rate_limit = rubygems_config.get('rate_limit', RATE_LIMITS.get('rubygems', 600))
        self.retry_backoff_factor = RETRY_BACKOFF_FACTOR
        self.retry_max_delay = RETRY_MAX_DELAY
        
        # Timeout configuration
        self.timeout = timeout or REQUEST_TIMEOUT
        self.connect_timeout = CONNECT_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('rubygems', USER_AGENTS['default'])
        
        # Session and cache
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Tuple[Any, datetime]] = {} if self.cache_enabled else None
        self._version_cache: Dict[str, RubyVersionRequirement] = {}
        
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
        """Quick check if gem exists on RubyGems"""
        package_name = normalize_package_name(package_name)
        try:
            import requests
            response = requests.head(f"{self.api_url}/gems/{package_name}.json", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for Ruby gems"""
        query = normalize_package_name(query)
        
        # RubyGems search API
        url = f"{self.api_url}/search.json"
        params = {
            'query': query
        }
        
        data = await self._make_request(url, params=params)
        if not data:
            return []
        
        results = []
        for gem in data[:limit]:
            result = {
                'name': gem.get('name'),
                'version': gem.get('version'),
                'description': gem.get('info'),
                'authors': gem.get('authors'),
                'downloads': gem.get('downloads'),
                'version_downloads': gem.get('version_downloads'),
                'platform': gem.get('platform'),
                'licenses': gem.get('licenses', []),
                'homepage_uri': gem.get('homepage_uri'),
                'documentation_uri': gem.get('documentation_uri'),
                'source_code_uri': gem.get('source_code_uri'),
                'gem_uri': gem.get('gem_uri'),
                'project_uri': gem.get('project_uri')
            }
            results.append(result)
        
        return results
    
    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str, 
                                   include_versions: bool = True) -> Optional[Dict]:
        """Get comprehensive gem information"""
        package_name = normalize_package_name(package_name)
        
        # Get gem info
        url = f"{self.api_url}/gems/{package_name}.json"
        data = await self._make_request(url)
        if not data:
            return None
        
        # Get versions if requested
        versions_info = []
        if include_versions:
            versions_data = await self._get_all_versions(package_name)
            versions_info = self._process_versions(versions_data)
        
        # Get reverse dependencies
        reverse_deps = await self._get_reverse_dependencies(package_name)
        
        # Get download stats
        downloads = await self._get_download_stats(package_name)
        
        # Extract comprehensive metadata
        info = {
            'name': data.get('name'),
            'version': data.get('version'),
            'platform': data.get('platform'),
            'authors': data.get('authors'),
            'info': data.get('info'),
            'licenses': data.get('licenses', []),
            'metadata': data.get('metadata', {}),
            'sha': data.get('sha'),
            'project_uri': data.get('project_uri'),
            'gem_uri': data.get('gem_uri'),
            'homepage_uri': data.get('homepage_uri'),
            'wiki_uri': data.get('wiki_uri'),
            'documentation_uri': data.get('documentation_uri'),
            'mailing_list_uri': data.get('mailing_list_uri'),
            'source_code_uri': data.get('source_code_uri'),
            'bug_tracker_uri': data.get('bug_tracker_uri'),
            'changelog_uri': data.get('changelog_uri'),
            'funding_uri': data.get('funding_uri'),
            'downloads': downloads,
            'version_downloads': data.get('version_downloads'),
            'versions': versions_info,
            'reverse_dependencies': reverse_deps,
            'dependencies': await self._get_dependencies(package_name, data.get('version')),
            'system_requirements': self._extract_system_requirements(data),
            'created_at': data.get('created_at'),
            'updated_at': data.get('updated_at')
        }
        
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
        
        # Get all versions and find the specific one
        versions_data = await self._get_all_versions(package_name)
        if not versions_data:
            return None
        
        for v in versions_data:
            if v.get('number') == version:
                return {
                    'name': package_name,
                    'version': v.get('number'),
                    'platform': v.get('platform'),
                    'prerelease': v.get('prerelease', False),
                    'licenses': v.get('licenses', []),
                    'requirements': v.get('requirements', []),
                    'sha': v.get('sha'),
                    'created_at': v.get('created_at'),
                    'description': v.get('description'),
                    'downloads_count': v.get('downloads_count'),
                    'metadata': v.get('metadata', {}),
                    'dependencies': await self._parse_dependencies(v.get('dependencies', {})),
                    'ruby_version': v.get('ruby_version'),
                    'required_ruby_version': v.get('required_ruby_version'),
                    'required_rubygems_version': v.get('required_rubygems_version')
                }
        
        return None
    
    async def get_versions(self, package_name: str, 
                         include_prereleases: bool = True,
                         include_yanked: bool = False) -> List[Dict]:
        """Get all versions with filtering options"""
        package_name = normalize_package_name(package_name)
        
        versions_data = await self._get_all_versions(package_name)
        if not versions_data:
            return []
        
        versions = []
        for v in versions_data:
            # Filter prereleases
            if not include_prereleases and v.get('prerelease', False):
                continue
            
            # Filter yanked versions
            if not include_yanked and v.get('yanked', False):
                continue
            
            versions.append({
                'version': v.get('number'),
                'platform': v.get('platform'),
                'prerelease': v.get('prerelease', False),
                'yanked': v.get('yanked', False),
                'created_at': v.get('created_at'),
                'sha': v.get('sha'),
                'metadata': v.get('metadata', {}),
                'downloads_count': v.get('downloads_count', 0)
            })
        
        # Sort by version (newest first)
        versions.sort(
            key=lambda x: parse_version(x['version']) or parse_version('0.0.0'), 
            reverse=True
        )
        
        return versions
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None,
                             include_development: bool = True) -> Dict[str, Any]:
        """Get package dependencies"""
        package_name = normalize_package_name(package_name)
        
        if version:
            pkg_data = await self.get_package_version(package_name, version)
        else:
            pkg_data = await self.get_package_info_async(package_name, include_versions=False)
        
        if not pkg_data:
            return {}
        
        return pkg_data.get('dependencies', {})
    
    async def _get_all_versions(self, package_name: str) -> List[Dict]:
        """Get all versions of a gem"""
        package_name = normalize_package_name(package_name)
        url = f"{self.api_url}/gems/{package_name}/versions.json"
        return await self._make_request(url) or []
    
    async def _get_reverse_dependencies(self, package_name: str) -> List[str]:
        """Get reverse dependencies (gems that depend on this one)"""
        package_name = normalize_package_name(package_name)
        url = f"{self.api_url}/gems/{package_name}/reverse_dependencies.json"
        data = await self._make_request(url)
        return data if isinstance(data, list) else []
    
    async def _get_download_stats(self, package_name: str) -> Dict[str, int]:
        """Get download statistics"""
        package_name = normalize_package_name(package_name)
        try:
            url = f"{self.api_url}/downloads/{package_name}.json"
            data = await self._make_request(url)
            if data:
                return {
                    'total': data.get('total_downloads', 0),
                    'version': data.get('version_downloads', 0)
                }
        except:
            pass
        return {'total': 0, 'version': 0}
    
    async def _get_dependencies(self, package_name: str, version: str) -> Dict:
        """Get dependencies for a specific version"""
        package_name = normalize_package_name(package_name)
        versions_data = await self._get_all_versions(package_name)
        
        for v in versions_data:
            if v.get('number') == version:
                return await self._parse_dependencies(v.get('dependencies', {}))
        
        return {}
    
    async def _parse_dependencies(self, dependencies: Dict) -> Dict:
        """Parse Ruby gem dependencies"""
        parsed = {
            'runtime': {},
            'development': {}
        }
        
        if 'dependencies' in dependencies:
            deps = dependencies['dependencies']
            for dep in deps:
                name = dep.get('name')
                requirements = dep.get('requirements', '')
                dep_type = 'development' if dep.get('type') == 'development' else 'runtime'
                
                if name:
                    parsed[dep_type][name] = requirements
        
        return parsed
    
    def _process_versions(self, versions_data: List[Dict]) -> List[Dict]:
        """Process version data"""
        versions = []
        
        for v in versions_data:
            version_str = v.get('number')
            if not version_str or parse_version(version_str) is None:
                continue
                
            versions.append({
                'version': version_str,
                'platform': v.get('platform'),
                'prerelease': v.get('prerelease', False),
                'yanked': v.get('yanked', False),
                'created_at': v.get('created_at'),
                'sha': v.get('sha'),
                'downloads_count': v.get('downloads_count', 0)
            })
        
        # Sort by version (newest first)
        versions.sort(
            key=lambda x: parse_version(x['version']) or parse_version('0.0.0'), 
            reverse=True
        )
        
        return versions
    
    def _extract_system_requirements(self, data: Dict) -> Dict[str, Any]:
        """Extract system requirements"""
        requirements = {
            'ruby': None,
            'rubygems': None,
            'platform': data.get('platform'),
            'licenses': data.get('licenses', [])
        }
        
        # Extract from metadata if available
        metadata = data.get('metadata', {})
        if 'required_ruby_version' in metadata:
            requirements['ruby'] = metadata['required_ruby_version']
        if 'required_rubygems_version' in metadata:
            requirements['rubygems'] = metadata['required_rubygems_version']
        
        return requirements
    
    def _parse_ruby_version_requirement(self, spec: str) -> RubyVersionRequirement:
        """Parse Ruby version requirement with pessimistic operator support"""
        if spec in self._version_cache:
            return self._version_cache[spec]
        
        req = RubyVersionRequirement(raw=spec)
        
        # Handle Ruby-specific patterns
        patterns = {
            r'^~>\s*(\d+)\.(\d+)\.(\d+)': lambda m: {
                'operator': '~>', 
                'major': int(m[1]), 
                'minor': int(m[2]), 
                'patch': int(m[3])
            },
            r'^>=\s*(\d+)\.(\d+)\.(\d+)': lambda m: {
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
        """Check if gem is compatible with system"""
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
        
        # Check Ruby version
        required_ruby = pkg_data.get('required_ruby_version')
        if required_ruby and 'ruby_version' in system_info:
            if not self._check_ruby_compatibility(system_info['ruby_version'], required_ruby):
                errors.append(f"Requires Ruby {required_ruby}, but system has {system_info['ruby_version']}")
        
        # Check RubyGems version
        required_rubygems = pkg_data.get('required_rubygems_version')
        if required_rubygems and 'rubygems_version' in system_info:
            if not self._check_rubygems_compatibility(system_info['rubygems_version'], required_rubygems):
                warnings.append(f"Recommends RubyGems {required_rubygems}, but system has {system_info['rubygems_version']}")
        
        # Check platform compatibility
        platform = pkg_data.get('platform')
        if platform and platform != 'ruby' and 'platform' in system_info:
            if not self._check_platform_compatibility(system_info['platform'], platform):
                errors.append(f"Not compatible with platform: {system_info['platform']}")
        
        return {
            'compatible': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'requirements': pkg_data.get('system_requirements', {})
        }
    
    def _check_ruby_compatibility(self, system_version: str, required: str) -> bool:
        """Check Ruby version compatibility with pessimistic operator support"""
        req = self._parse_ruby_version_requirement(required)
        system_v = parse_version(system_version)
        
        if not system_v or not req.major:
            return True
        
        if req.operator == '~>':
            # Pessimistic operator: compatible within minor version
            if req.patch is not None:
                min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
                max_v = parse_version(f"{req.major}.{req.minor + 1}.0")
            else:
                min_v = parse_version(f"{req.major}.{req.minor}.0")
                max_v = parse_version(f"{req.major + 1}.0.0")
            
            return min_v <= system_v < max_v
        elif req.operator == '>=':
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            return system_v >= min_v
        else:
            # Exact match
            exact_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            return system_v == exact_v
    
    def _check_rubygems_compatibility(self, system_version: str, required: str) -> bool:
        """Check RubyGems version compatibility"""
        return self._check_ruby_compatibility(system_version, required)
    
    def _check_platform_compatibility(self, system_platform: str, required_platform: str) -> bool:
        """Check platform compatibility"""
        if required_platform == 'ruby':
            return True  # Pure Ruby, platform independent
        
        # Platform-specific gems
        platform_mappings = {
            'x86_64-linux': ['linux', 'x86_64'],
            'x86_64-darwin': ['darwin', 'macos', 'x86_64'],
            'arm64-darwin': ['darwin', 'macos', 'arm64'],
            'x64-mingw32': ['windows', 'x64'],
            'x86-mingw32': ['windows', 'x86']
        }
        
        if required_platform in platform_mappings:
            required_parts = platform_mappings[required_platform]
            return any(part in system_platform.lower() for part in required_parts)
        
        return required_platform.lower() in system_platform.lower()

# Example usage
async def example_usage():
    async with RubyGemsClient() as client:
        # Search for gems
        results = await client.search_packages("rails", limit=5)
        
        # Get comprehensive gem info
        info = await client.get_package_info_async("rails", include_versions=True)
        
        # Get specific version
        version_info = await client.get_package_version("rails", "7.0.0")
        
        # Check compatibility
        compat = await client.check_compatibility(
            "rails", 
            "7.0.0",
            {
                'ruby_version': '3.0.0',
                'rubygems_version': '3.2.0',
                'platform': 'x86_64-linux'
            }
        )
        
        print(f"Gem: {info['name']}")
        print(f"Latest version: {info['version']}")
        print(f"Compatible: {compat['compatible']}")

if __name__ == "__main__":
    asyncio.run(example_usage())