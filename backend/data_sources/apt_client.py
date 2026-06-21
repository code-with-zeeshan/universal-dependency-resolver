# data_sources/apt_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Set
import json
import logging
from datetime import datetime
import re
import gzip
from io import BytesIO
from backend.core.cache import cache_manager, cached, CacheKeys
from urllib.parse import quote, urljoin
from backend.core.utils import normalize_package_name, parse_version, compare_versions
from backend.settings import (
    CACHE_TTL, USER_AGENTS, RATE_LIMITS,
    REQUEST_TIMEOUT, MAX_RETRIES, RATE_LIMIT_DELAY,
    get_ecosystem_config
)

logger = logging.getLogger(__name__)

class APTClient:
    def __init__(self):
        # Get APT-specific configuration
        apt_config = get_ecosystem_config('apt')
        
        # Default Debian/Ubuntu repositories
        self.repositories = apt_config.get('repositories', [
            'http://deb.debian.org/debian',
            'http://archive.ubuntu.com/ubuntu',
            'http://security.debian.org/debian-security'
        ])
        
        self.main_repo = self.repositories[0]
        self.distributions = apt_config.get('distributions', ['stable', 'testing', 'unstable'])
        self.components = apt_config.get('components', ['main', 'contrib', 'non-free'])
        
        # Cache configuration
        self.cache_ttl = apt_config.get('cache_ttl', CACHE_TTL)
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._packages_cache: Dict[str, Any] = {}
        
        # Rate limiting
        self.rate_limit = apt_config.get('rate_limit', RATE_LIMITS.get('apt', 600))
        self.rate_limit_delay = RATE_LIMIT_DELAY
        self.max_retries = MAX_RETRIES
        self.timeout = REQUEST_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('apt', USER_AGENTS['default'])
        
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
    
    def package_exists(self, package_name: str) -> bool:
        """Quick check if package exists"""
        package_name = normalize_package_name(package_name)
        # This would require parsing Packages files
        # For now, return True to attempt full lookup
        return True
    
    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for packages in APT repositories"""
        query = normalize_package_name(query)
        results = []
        
        # Load package list for stable distribution
        packages = await self._get_packages_list('stable', 'main')
        if not packages:
            return results
        
        # Search through packages
        for pkg_name, pkg_info in packages.items():
            if query in pkg_name or (pkg_info.get('description') and query in pkg_info['description'].lower()):
                results.append({
                    'name': pkg_name,
                    'version': pkg_info.get('version', ''),
                    'description': pkg_info.get('description', ''),
                    'section': pkg_info.get('section', ''),
                    'priority': pkg_info.get('priority', '')
                })
                
                if len(results) >= limit:
                    break
        
        return results
    
    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> Optional[Dict]:
        """Get package information from APT repositories"""
        package_name = normalize_package_name(package_name)
        
        # Search across distributions
        package_data = None
        versions_list = []
        
        for dist in self.distributions:
            for component in self.components:
                packages = await self._get_packages_list(dist, component)
                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    versions_list.append({
                        'version': pkg_data.get('version', ''),
                        'distribution': dist,
                        'component': component,
                        'architecture': pkg_data.get('architecture', 'all')
                    })
                    
                    if not package_data:
                        package_data = pkg_data
        
        if not package_data:
            return None
        
        # Extract dependencies
        dependencies = self._parse_dependencies(package_data)
        
        # Extract system requirements
        system_requirements = self._extract_system_requirements(package_data)
        
        info = {
            'name': package_name,
            'version': package_data.get('version', ''),
            'versions': versions_list,
            'description': package_data.get('description', ''),
            'homepage': package_data.get('homepage', ''),
            'maintainer': package_data.get('maintainer', ''),
            'section': package_data.get('section', ''),
            'priority': package_data.get('priority', ''),
            'architecture': package_data.get('architecture', 'all'),
            'size': package_data.get('size', 0),
            'installed_size': package_data.get('installed-size', 0),
            'dependencies': dependencies,
            'system_requirements': system_requirements,
            'ecosystem': 'apt'
        }
        
        return info
    
    def get_package_info(self, package_name: str) -> Optional[Dict]:
        """Synchronous wrapper for get_package_info_async"""
        package_name = normalize_package_name(package_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_package_info_async(package_name))
        finally:
            loop.close()
    
    async def get_versions(self, package_name: str) -> List[Dict]:
        """Get all available versions across distributions"""
        package_name = normalize_package_name(package_name)
        versions = []
        
        for dist in self.distributions:
            for component in self.components:
                packages = await self._get_packages_list(dist, component)
                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    versions.append({
                        'version': pkg_data.get('version', ''),
                        'distribution': dist,
                        'component': component,
                        'architecture': pkg_data.get('architecture', 'all'),
                        'upload_time': None  # APT doesn't provide this easily
                    })
        
        # Sort by version
        versions.sort(key=lambda x: parse_version(x['version'].split('-')[0]) or parse_version('0.0.0'), reverse=True)
        
        return versions
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None) -> Dict:
        """Get package dependencies"""
        package_name = normalize_package_name(package_name)
        
        # Find package data
        package_data = None
        for dist in self.distributions:
            for component in self.components:
                packages = await self._get_packages_list(dist, component)
                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    if not version or pkg_data.get('version') == version:
                        package_data = pkg_data
                        break
            if package_data:
                break
        
        if not package_data:
            return {}
        
        return self._parse_dependencies(package_data)
    
    async def _get_packages_list(self, distribution: str, component: str) -> Dict[str, Dict]:
        """Get and parse Packages file for a distribution/component"""
        cache_key = f"packages:{distribution}:{component}"
        
        if cache_key in self._packages_cache:
            return self._packages_cache[cache_key]
        
        # Construct URL for Packages.gz file
        url = f"{self.main_repo}/dists/{distribution}/{component}/binary-amd64/Packages.gz"
        
        try:
            await self._ensure_session()
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Packages from {url}: {response.status}")
                    return {}
                
                # Download and decompress
                content = await response.read()
                with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                    packages_content = gz.read().decode('utf-8', errors='ignore')
                
                # Parse packages
                packages = self._parse_packages_file(packages_content)
                self._packages_cache[cache_key] = packages
                
                return packages
                
        except Exception as e:
            logger.error(f"Error fetching packages list: {e}")
            return {}
    
    def _parse_packages_file(self, content: str) -> Dict[str, Dict]:
        """Parse APT Packages file format"""
        packages = {}
        current_package = {}
        current_field = None
        
        for line in content.split('\n'):
            if not line.strip():
                # Empty line marks end of package entry
                if 'package' in current_package:
                    pkg_name = current_package['package']
                    packages[pkg_name] = current_package
                current_package = {}
                current_field = None
                continue
            
            if line.startswith(' '):
                # Continuation of previous field
                if current_field:
                    current_package[current_field] += '\n' + line.strip()
            else:
                # New field
                match = re.match(r'^([^:]+):\s*(.*)$', line)
                if match:
                    field_name = match.group(1).lower()
                    field_value = match.group(2)
                    current_package[field_name] = field_value
                    current_field = field_name
        
        # Don't forget the last package
        if 'package' in current_package:
            pkg_name = current_package['package']
            packages[pkg_name] = current_package
        
        return packages
    
    def _parse_dependencies(self, package_data: Dict) -> Dict[str, List[Dict]]:
        """Parse Debian package dependencies"""
        dependencies = {
            'depends': [],
            'recommends': [],
            'suggests': [],
            'enhances': [],
            'conflicts': [],
            'breaks': [],
            'provides': [],
            'replaces': []
        }
        
        dep_fields = ['depends', 'recommends', 'suggests', 'enhances', 
                      'conflicts', 'breaks', 'provides', 'replaces']
        
        for field in dep_fields:
            if field in package_data:
                deps_str = package_data[field]
                parsed_deps = self._parse_dependency_string(deps_str)
                dependencies[field] = parsed_deps
        
        return dependencies
    
    def _parse_dependency_string(self, deps_str: str) -> List[Dict]:
        """Parse Debian dependency string format"""
        dependencies = []
        
        # Split by comma for AND dependencies
        for dep_group in deps_str.split(','):
            dep_group = dep_group.strip()
            
            # Handle OR dependencies (separated by |)
            or_deps = []
            for or_dep in dep_group.split('|'):
                or_dep = or_dep.strip()
                
                # Parse individual dependency
                match = re.match(r'^([a-z0-9][a-z0-9+.-]+)(?:\s*\(([^)]+)\))?', or_dep)
                if match:
                    dep_name = match.group(1)
                    version_spec = match.group(2) if match.group(2) else ''
                    
                    or_deps.append({
                        'name': dep_name,
                        'version_spec': version_spec
                    })
            
            if len(or_deps) == 1:
                dependencies.append(or_deps[0])
            elif or_deps:
                dependencies.append({
                    'or_dependencies': or_deps
                })
        
        return dependencies
    
    def _extract_system_requirements(self, package_data: Dict) -> Dict[str, Any]:
        """Extract system requirements from package data"""
        requirements = {
            'architecture': package_data.get('architecture', 'all'),
            'essential': package_data.get('essential', 'no') == 'yes',
            'priority': package_data.get('priority', 'optional')
        }
        
        # Check for specific runtime requirements in dependencies
        if 'depends' in package_data:
            deps_str = package_data['depends'].lower()
            
            # Check for libc version
            libc_match = re.search(r'libc6\s*\(>=\s*([^)]+)\)', deps_str)
            if libc_match:
                requirements['libc_version'] = libc_match.group(1)
            
            # Check for kernel version
            kernel_match = re.search(r'linux-[a-z-]+\s*\(>=\s*([^)]+)\)', deps_str)
            if kernel_match:
                requirements['kernel_version'] = kernel_match.group(1)
        
        return requirements