# data_sources/cocoapods_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Set
import json
import logging
from datetime import datetime
from urllib.parse import quote
import re
from backend.core.cache import cache_manager, cached, CacheKeys
from backend.core.utils import normalize_package_name, parse_version
from backend.settings import (
    CACHE_TTL, USER_AGENTS, RATE_LIMITS,
    REQUEST_TIMEOUT, MAX_RETRIES, RATE_LIMIT_DELAY,
    get_ecosystem_config
)

logger = logging.getLogger(__name__)

class CocoaPodsClient:
    def __init__(self):
        # Get CocoaPods-specific configuration
        cocoapods_config = get_ecosystem_config('cocoapods')
        
        self.base_url = cocoapods_config.get('url', 'https://trunk.cocoapods.org/api/v1')
        self.specs_url = cocoapods_config.get('specs_url', 'https://cdn.cocoapods.org')
        
        # Cache configuration
        self.cache_ttl = cocoapods_config.get('cache_ttl', CACHE_TTL)
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        
        # Rate limiting
        self.rate_limit = cocoapods_config.get('rate_limit', RATE_LIMITS.get('cocoapods', 600))
        self.rate_limit_delay = RATE_LIMIT_DELAY
        self.max_retries = MAX_RETRIES
        self.timeout = REQUEST_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('cocoapods', USER_AGENTS['default'])
        
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
                            await asyncio.sleep(RATE_LIMIT_DELAY * (attempt + 1))
                            continue
                        return None
                    
                    data = await response.json()
                    self._set_cache(cache_key, data)
                    return data
                    
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(RATE_LIMIT_DELAY * (attempt + 1))
                else:
                    return None
        
        return None
    
    def package_exists(self, package_name: str) -> bool:
        """Quick check if package exists"""
        package_name = self._normalize_pod_name(package_name)
        try:
            import requests
            response = requests.get(
                f"{self.base_url}/pods/{quote(package_name)}", 
                timeout=5,
                headers={"User-Agent": self.user_agent}
            )
            return response.status_code == 200
        except:
            return False
    
    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for CocoaPods packages"""
        query = normalize_package_name(query)
        
        # Use CocoaPods search endpoint
        url = f"{self.base_url}/pods"
        params = {'query': query}
        
        data = await self._make_request(url, params)
        if not data:
            return []
        
        results = []
        for pod in data[:limit]:
            results.append({
                'name': pod.get('name', ''),
                'version': pod.get('version', ''),
                'summary': pod.get('summary', ''),
                'platforms': pod.get('platforms', {}),
                'authors': pod.get('authors', {})
            })
        
        return results
    
    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> Optional[Dict]:
        """Get comprehensive package information"""
        package_name = self._normalize_pod_name(package_name)
        
        # Get pod information
        url = f"{self.base_url}/pods/{quote(package_name)}"
        data = await self._make_request(url)
        
        if not data:
            return None
        
        # Get version details
        versions = data.get('versions', [])
        latest_version = versions[0] if versions else None
        
        if not latest_version:
            return None
        
        # Get detailed spec for latest version
        spec_data = await self._get_podspec(package_name, latest_version)
        
        # Extract dependencies
        dependencies = self._parse_dependencies(spec_data) if spec_data else {}
        
        # Extract system requirements
        system_requirements = self._extract_system_requirements(spec_data) if spec_data else {}
        
        info = {
            'name': data.get('name', package_name),
            'version': latest_version,
            'versions': self._process_versions(versions),
            'summary': data.get('summary', ''),
            'description': spec_data.get('description', '') if spec_data else '',
            'homepage': spec_data.get('homepage', '') if spec_data else '',
            'source': spec_data.get('source', {}) if spec_data else {},
            'license': spec_data.get('license', '') if spec_data else '',
            'authors': spec_data.get('authors', {}) if spec_data else {},
            'platforms': spec_data.get('platforms', {}) if spec_data else {},
            'dependencies': dependencies,
            'system_requirements': system_requirements,
            'ecosystem': 'cocoapods'
        }
        
        return info
    
    def get_package_info(self, package_name: str) -> Optional[Dict]:
        """Synchronous wrapper for get_package_info_async"""
        package_name = self._normalize_pod_name(package_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_package_info_async(package_name))
        finally:
            loop.close()
    
    async def get_versions(self, package_name: str) -> List[Dict]:
        """Get all available versions of a pod"""
        package_name = self._normalize_pod_name(package_name)
        
        url = f"{self.base_url}/pods/{quote(package_name)}"
        data = await self._make_request(url)
        
        if not data:
            return []
        
        versions = data.get('versions', [])
        return self._process_versions(versions)
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None) -> Dict:
        """Get pod dependencies"""
        package_name = self._normalize_pod_name(package_name)
        
        if not version:
            # Get latest version
            pod_info = await self.get_package_info_async(package_name)
            if not pod_info:
                return {}
            version = pod_info['version']
        
        # Get podspec for specific version
        spec_data = await self._get_podspec(package_name, version)
        if not spec_data:
            return {}
        
        return self._parse_dependencies(spec_data)
    
    async def _get_podspec(self, pod_name: str, version: str) -> Optional[Dict]:
        """Get podspec for a specific version"""
        # Construct podspec URL
        # CocoaPods stores specs in a specific directory structure
        name_prefix = pod_name[0].upper()
        spec_url = f"{self.specs_url}/Specs/{name_prefix}/{pod_name}/{version}/{pod_name}.podspec.json"
        
        # Try JSON format first
        spec_data = await self._make_request(spec_url)
        
        if not spec_data:
            # Try alternate URL structure
            alt_url = f"{self.base_url}/pods/{quote(pod_name)}/specs/{version}"
            spec_data = await self._make_request(alt_url)
        
        return spec_data
    
    def _process_versions(self, versions: List[str]) -> List[Dict]:
        """Process version list"""
        processed = []
        
        for ver in versions:
            processed.append({
                'version': ver,
                'stable': not any(pre in ver for pre in ['alpha', 'beta', 'rc', 'pre']),
                'upload_time': None  # CocoaPods doesn't provide this easily
            })
        
        # Sort by version (newest first)
        processed.sort(key=lambda x: parse_version(x['version']) or parse_version('0.0.0'), reverse=True)
        
        return processed
    
    def _parse_dependencies(self, spec_data: Dict) -> Dict[str, List[Dict]]:
        """Parse CocoaPods dependencies"""
        dependencies = {
            'dependencies': [],
            'development_dependencies': []
        }
        
        # Parse regular dependencies
        if 'dependencies' in spec_data:
            for dep_name, dep_spec in spec_data['dependencies'].items():
                dep_info = {
                    'name': dep_name,
                    'version_spec': self._parse_version_spec(dep_spec)
                }
                dependencies['dependencies'].append(dep_info)
        
        # Parse subspecs dependencies
        if 'subspecs' in spec_data:
            for subspec in spec_data['subspecs']:
                if 'dependencies' in subspec:
                    for dep_name, dep_spec in subspec['dependencies'].items():
                        dep_info = {
                            'name': dep_name,
                            'version_spec': self._parse_version_spec(dep_spec),
                            'subspec': subspec.get('name', '')
                        }
                        dependencies['dependencies'].append(dep_info)
        
        # Parse development dependencies (test specs)
        if 'test_spec' in spec_data:
            test_spec = spec_data['test_spec']
            if isinstance(test_spec, dict) and 'dependencies' in test_spec:
                for dep_name, dep_spec in test_spec['dependencies'].items():
                    dep_info = {
                        'name': dep_name,
                        'version_spec': self._parse_version_spec(dep_spec)
                    }
                    dependencies['development_dependencies'].append(dep_info)
        
        return dependencies
    
    def _parse_version_spec(self, spec: Any) -> str:
        """Parse CocoaPods version specification"""
        if isinstance(spec, str):
            return spec
        elif isinstance(spec, list):
            # Multiple version constraints
            return ', '.join(spec)
        elif isinstance(spec, dict):
            # Complex specification
            return str(spec)
        else:
            return ''
    
    def _extract_system_requirements(self, spec_data: Dict) -> Dict[str, Any]:
        """Extract system requirements from podspec"""
        requirements = {}
        
        # Platform requirements
        if 'platforms' in spec_data:
            platforms = spec_data['platforms']
            if isinstance(platforms, dict):
                for platform, min_version in platforms.items():
                    requirements[f'{platform}_deployment_target'] = min_version
        
        # Swift version
        if 'swift_version' in spec_data:
            requirements['swift'] = {
                'version': spec_data['swift_version']
            }
        elif 'swift_versions' in spec_data:
            requirements['swift'] = {
                'versions': spec_data['swift_versions']
            }
        
        # Frameworks
        if 'frameworks' in spec_data:
            requirements['frameworks'] = spec_data['frameworks']
        
        # Libraries
        if 'libraries' in spec_data:
            requirements['libraries'] = spec_data['libraries']
        
        # Compiler flags
        if 'compiler_flags' in spec_data:
            requirements['compiler_flags'] = spec_data['compiler_flags']
        
        # Requires ARC
        if 'requires_arc' in spec_data:
            requirements['requires_arc'] = spec_data['requires_arc']
        
        return requirements
    
    def _normalize_pod_name(self, name: str) -> str:
        """Normalize CocoaPods package name"""
        # CocoaPods names are case-sensitive
        return name.strip()