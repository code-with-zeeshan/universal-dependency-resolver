# data_sources/gomodules_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Set
import json
import logging
from datetime import datetime
from urllib.parse import quote
import re
from backend.core.cache import cache_manager, cached, CacheKeys
from backend.core.utils import normalize_package_name, parse_version, compare_versions
from backend.settings import (
    CACHE_TTL, USER_AGENTS, RATE_LIMITS,
    REQUEST_TIMEOUT, MAX_RETRIES, RATE_LIMIT_DELAY,
    RETRY_BACKOFF_FACTOR, RETRY_MAX_DELAY,
    get_ecosystem_config
)

logger = logging.getLogger(__name__)

class GoModulesClient:
    def __init__(self):
        # Get Go-specific configuration
        go_config = get_ecosystem_config('gomodules')
        
        self.base_url = go_config.get('url', 'https://proxy.golang.org')
        self.sum_db_url = go_config.get('sum_db_url', 'https://sum.golang.org')
        self.pkg_dev_url = 'https://pkg.go.dev'
        
        # Cache configuration
        self.cache_ttl = go_config.get('cache_ttl', CACHE_TTL)
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        
        # Rate limiting
        self.rate_limit = go_config.get('rate_limit', RATE_LIMITS.get('gomodules', 600))
        self.rate_limit_delay = RATE_LIMIT_DELAY
        self.max_retries = MAX_RETRIES
        self.timeout = REQUEST_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('gomodules', USER_AGENTS['default'])
        
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if self._session is None or self._session.closed:
            timeout_config = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout_config,
                headers={"User-Agent": self.user_agent}
            )
    
    async def close(self):
        """Close the HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached data if not expired"""
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return data
            else:
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: Any):
        """Set cache data"""
        self._cache[cache_key] = (data, datetime.now())
    
    async def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make HTTP request with retry logic"""
        await self._ensure_session()
        
        cache_key = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        cached_data = await self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data
        
        await asyncio.sleep(self.rate_limit_delay)
        
        for attempt in range(self.max_retries):
            try:
                async with self._session.get(url, params=params) as response:
                    if response.status == 404:
                        return None
                    
                    if response.status != 200:
                        logger.error(f"HTTP {response.status} from {url}")
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(RETRY_BACKOFF_FACTOR ** attempt)
                            continue
                        return None
                    
                    # Handle different response types
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        data = await response.json()
                    else:
                        data = await response.text()
                    
                    self._set_cache(cache_key, data)
                    return data
                    
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(RETRY_BACKOFF_FACTOR ** attempt)
                else:
                    return None
        
        return None
    
    def package_exists(self, package_name: str) -> bool:
        """Quick check if package exists"""
        package_name = self._normalize_go_module_path(package_name)
        try:
            import requests
            response = requests.head(f"{self.base_url}/{package_name}/@v/list", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for Go packages (via pkg.go.dev)"""
        query = normalize_package_name(query)
        
        # Go doesn't have a centralized search API like PyPI/npm
        # We'll scrape pkg.go.dev search results
        search_url = f"{self.pkg_dev_url}/search"
        params = {'q': query, 'limit': limit}
        
        try:
            # For now, return empty as proper implementation would require web scraping
            # In production, you'd want to implement pkg.go.dev scraping
            logger.warning("Go package search not fully implemented - requires web scraping")
            return []
        except Exception as e:
            logger.error(f"Error searching Go packages: {e}")
            return []
    
    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> Optional[Dict]:
        """Get package information with caching"""
        package_name = self._normalize_go_module_path(package_name)
        
        # Get available versions
        versions_data = await self._get_versions_list(package_name)
        if not versions_data:
            return None
        
        # Get latest version info
        latest_version = await self._get_latest_version(package_name)
        if not latest_version:
            return None
        
        # Get module info
        module_info = await self._get_module_info(package_name, latest_version)
        if not module_info:
            return None
        
        # Parse go.mod for dependencies
        dependencies = await self._parse_go_mod(module_info)
        
        # Extract metadata
        info = {
            'name': package_name,
            'version': latest_version,
            'versions': versions_data,
            'description': f'Go module: {package_name}',
            'homepage': f'https://pkg.go.dev/{package_name}',
            'repository': f'https://{package_name}',
            'license': 'See repository',  # Go modules don't have standardized license info
            'dependencies': dependencies,
            'system_requirements': {
                'go': {
                    'min_version': self._extract_go_version(module_info)
                }
            },
            'ecosystem': 'gomodules'
        }
        
        return info
    
    def get_package_info(self, package_name: str) -> Optional[Dict]:
        """Synchronous wrapper for get_package_info_async"""
        package_name = self._normalize_go_module_path(package_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_package_info_async(package_name))
        finally:
            loop.close()
    
    async def get_package_version(self, package_name: str, version: str) -> Optional[Dict]:
        """Get specific version information"""
        package_name = self._normalize_go_module_path(package_name)
        
        # Normalize version (Go uses v prefix)
        if not version.startswith('v'):
            version = f'v{version}'
        
        module_info = await self._get_module_info(package_name, version)
        if not module_info:
            return None
        
        dependencies = await self._parse_go_mod(module_info)
        
        return {
            'name': package_name,
            'version': version,
            'dependencies': dependencies,
            'system_requirements': {
                'go': {
                    'min_version': self._extract_go_version(module_info)
                }
            }
        }
    
    async def get_versions(self, package_name: str) -> List[Dict]:
        """Get all available versions"""
        package_name = self._normalize_go_module_path(package_name)
        versions_data = await self._get_versions_list(package_name)
        
        if not versions_data:
            return []
        
        versions = []
        for ver in versions_data:
            # Parse version info
            ver_info = {
                'version': ver,
                'stable': not ('-' in ver or '+incompatible' in ver),
                'upload_time': None  # Could fetch from .info endpoint
            }
            versions.append(ver_info)
        
        # Sort by version (newest first)
        versions.sort(key=lambda x: parse_version(x['version'].lstrip('v')) or parse_version('0.0.0'), reverse=True)
        
        return versions
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None) -> Dict:
        """Get package dependencies"""
        package_name = self._normalize_go_module_path(package_name)
        
        if not version:
            version = await self._get_latest_version(package_name)
        elif not version.startswith('v'):
            version = f'v{version}'
        
        module_info = await self._get_module_info(package_name, version)
        if not module_info:
            return {}
        
        return await self._parse_go_mod(module_info)
    
    async def _get_versions_list(self, package_name: str) -> Optional[List[str]]:
        """Get list of available versions"""
        url = f"{self.base_url}/{package_name}/@v/list"
        data = await self._make_request(url)
        
        if data and isinstance(data, str):
            versions = [v.strip() for v in data.strip().split('\n') if v.strip()]
            return versions
        return None
    
    async def _get_latest_version(self, package_name: str) -> Optional[str]:
        """Get latest version of a package"""
        url = f"{self.base_url}/{package_name}/@latest"
        data = await self._make_request(url)
        
        if data and isinstance(data, dict):
            return data.get('Version')
        return None
    
    async def _get_module_info(self, package_name: str, version: str) -> Optional[Dict]:
        """Get module info including go.mod content"""
        # Get version info
        info_url = f"{self.base_url}/{package_name}/@v/{version}.info"
        info_data = await self._make_request(info_url)
        
        # Get go.mod content
        mod_url = f"{self.base_url}/{package_name}/@v/{version}.mod"
        mod_data = await self._make_request(mod_url)
        
        if info_data and mod_data:
            return {
                'info': info_data if isinstance(info_data, dict) else json.loads(info_data),
                'go_mod': mod_data if isinstance(mod_data, str) else ''
            }
        return None
    
    async def _parse_go_mod(self, module_info: Dict) -> Dict:
        """Parse go.mod content for dependencies"""
        dependencies = {
            'required': {},
            'indirect': {},
            'replace': {}
        }
        
        go_mod_content = module_info.get('go_mod', '')
        if not go_mod_content:
            return dependencies
        
        # Parse require statements
        require_block = False
        for line in go_mod_content.split('\n'):
            line = line.strip()
            
            if line.startswith('require ('):
                require_block = True
                continue
            elif line == ')' and require_block:
                require_block = False
                continue
            
            if require_block or line.startswith('require '):
                # Parse dependency line
                match = re.match(r'(?:require\s+)?([^\s]+)\s+([^\s]+)(?:\s+//\s+indirect)?', line)
                if match:
                    dep_name = match.group(1)
                    dep_version = match.group(2)
                    
                    if '// indirect' in line:
                        dependencies['indirect'][dep_name] = dep_version
                    else:
                        dependencies['required'][dep_name] = dep_version
            
            # Parse replace statements
            if line.startswith('replace '):
                match = re.match(r'replace\s+([^\s]+)(?:\s+[^\s]+)?\s+=>\s+([^\s]+)\s+([^\s]+)', line)
                if match:
                    old_path = match.group(1)
                    new_path = match.group(2)
                    new_version = match.group(3)
                    dependencies['replace'][old_path] = f"{new_path}@{new_version}"
        
        return dependencies
    
    def _extract_go_version(self, module_info: Dict) -> Optional[str]:
        """Extract required Go version from go.mod"""
        go_mod_content = module_info.get('go_mod', '')
        
        match = re.search(r'^\s*go\s+(\d+\.\d+(?:\.\d+)?)', go_mod_content, re.MULTILINE)
        if match:
            return match.group(1)
        return None
    
    def _normalize_go_module_path(self, path: str) -> str:
        """Normalize Go module path"""
        # Remove common prefixes
        path = path.strip()
        if path.startswith('github.com/') or path.startswith('golang.org/'):
            return path
        
        # Try to construct a valid module path
        if '/' not in path:
            # Assume it's a github package
            return f"github.com/{path}/{path}"
        
        return path