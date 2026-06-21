#npm_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from ..core.utils import normalize_package_name,  parse_version
import re
from enum import Enum
import hashlib
from dataclasses import dataclass
from collections import defaultdict
from ..settings import (
    NPM_URL,
    NPM_SEARCH_URL,
    NPM_DOWNLOADS_API,
    NPM_MIRROR_URLS,
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
    DEPENDENCIES = "dependencies"
    DEV_DEPENDENCIES = "devDependencies"
    PEER_DEPENDENCIES = "peerDependencies"
    OPTIONAL_DEPENDENCIES = "optionalDependencies"
    BUNDLED_DEPENDENCIES = "bundledDependencies"

@dataclass
class VersionRequirement:
    """Represents a semver version requirement"""
    raw: str
    operator: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None
    prerelease: Optional[str] = None
    
class NPMClient:
    def __init__(self, 
                 registry_url: str = None,
                 cache_ttl: int = None,
                 max_retries: int = None,
                 rate_limit_delay: float = None,
                 timeout: int = None):
        # Get NPM-specific configuration
        npm_config = get_ecosystem_config('npm')

        # Use settings with ability to override
        self.registry_url = (registry_url or npm_config.get('url', NPM_URL)).rstrip('/')
        self.search_url = NPM_SEARCH_URL
        self.downloads_url = NPM_DOWNLOADS_API
        self.mirror_urls = NPM_MIRROR_URLS
        
        # Cache configuration
        self.cache_ttl = cache_ttl or npm_config.get('cache_ttl', CACHE_TTL)
        self.cache_enabled = ENABLE_CACHE
        
        # Rate limiting configuration
        self.max_retries = max_retries or MAX_RETRIES
        self.rate_limit_delay = rate_limit_delay or RATE_LIMIT_DELAY
        self.rate_limit = npm_config.get('rate_limit', RATE_LIMITS.get('npm', 600))
        self.retry_backoff_factor = RETRY_BACKOFF_FACTOR
        self.retry_max_delay = RETRY_MAX_DELAY
        
        # Timeout configuration
        self.timeout = timeout or REQUEST_TIMEOUT
        self.connect_timeout = CONNECT_TIMEOUT
        
        # User agent
        self.user_agent = USER_AGENTS.get('npm', USER_AGENTS['default'])
        
        # Session and cache
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Tuple[Any, datetime]] = {} if self.cache_enabled else None
        self._semver_cache: Dict[str, VersionRequirement] = {}
        
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

        # Try main URL first, then mirrors if available
        urls_to_try = [url]
        if self.mirror_urls and 'registry.npmjs.org' in url:
            # Add mirror URLs
            for mirror in self.mirror_urls:
                mirror_url = url.replace(self.registry_url, mirror.rstrip('/'))
                urls_to_try.append(mirror_url)
        
        last_error = None
        for attempt_url in urls_to_try:
            for attempt in range(self.max_retries):
                try:
                    async with self._session.get(attempt_url, params=params, headers=headers) as response:
                        if response.status == 429:  # Rate limited
                            retry_after = int(response.headers.get('Retry-After', 60))
                            logger.warning(f"Rate limited, waiting {retry_after}s")
                            await asyncio.sleep(min(retry_after, self.retry_max_delay))
                            continue
                        
                        if response.status == 404:
                            return None
                        
                        if response.status != 200:
                            logger.error(f"HTTP {response.status} from {attempt_url}")
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
                    logger.error(f"Timeout for {attempt_url}")
                    last_error = "Timeout"
                except Exception as e:
                    logger.error(f"Request error for {attempt_url}: {e}")
                    last_error = str(e)
                
                if attempt < self.max_retries - 1:
                    delay = min(self.retry_backoff_factor ** attempt, self.retry_max_delay)
                    await asyncio.sleep(delay)
        
        logger.error(f"All attempts failed. Last error: {last_error}")
        return None
    
    async def search_packages(self, query: str, limit: int = 20, 
                            quality: Optional[float] = None,
                            popularity: Optional[float] = None,
                            maintenance: Optional[float] = None) -> List[Dict]:
        """
        Search NPM packages with advanced filtering
        
        Args:
            query: Search query
            limit: Maximum results
            quality: Minimum quality score (0-1)
            popularity: Minimum popularity score (0-1)
            maintenance: Minimum maintenance score (0-1)
        """
        query = normalize_package_name(query)
        params = {
            'text': query,
            'size': min(limit, 250)  # API max
        }
        
        data = await self._make_request(self.search_url, params=params)
        if not data:
            return []
        
        results = []
        for obj in data.get('objects', []):
            package = obj.get('package', {})
            score = obj.get('score', {})
            
            # Apply score filters
            detail = score.get('detail', {})
            if quality and detail.get('quality', 0) < quality:
                continue
            if popularity and detail.get('popularity', 0) < popularity:
                continue
            if maintenance and detail.get('maintenance', 0) < maintenance:
                continue
            
            # Extract comprehensive info
            result = {
                'name': package.get('name'),
                'version': package.get('version'),
                'description': package.get('description'),
                'keywords': package.get('keywords', []),
                'date': package.get('date'),
                'publisher': self._extract_publisher(package.get('publisher')),
                'maintainers': package.get('maintainers', []),
                'repository': self._extract_repository(package.get('links', {})),
                'npm_url': package.get('links', {}).get('npm'),
                'homepage': package.get('links', {}).get('homepage'),
                'bugs': package.get('links', {}).get('bugs'),
                'license': package.get('license'),
                'scope': package.get('scope'),
                'score': {
                    'final': score.get('final', 0),
                    'quality': detail.get('quality', 0),
                    'popularity': detail.get('popularity', 0),
                    'maintenance': detail.get('maintenance', 0)
                },
                'searchScore': obj.get('searchScore', 0)
            }
            
            results.append(result)
        
        return results
    
    async def get_package_info(self, package_name: str, 
                             include_readme: bool = True,
                             include_versions: bool = True) -> Optional[Dict]:
        """Get comprehensive package information"""
        package_name = normalize_package_name(package_name)
        # URL encode package name for scoped packages
        encoded_name = quote(package_name, safe='@/')
        url = f"{self.registry_url}/{encoded_name}"
        
        data = await self._make_request(url)
        if not data:
            return None
        
        # Get latest version
        latest_version = data.get('dist-tags', {}).get('latest')
        if not latest_version:
            return None
        
        latest_data = data.get('versions', {}).get(latest_version, {})
        
        # Get download stats
        downloads = await self._get_download_stats(package_name)
        
        # Check for TypeScript definitions
        types_info = await self._check_typescript_support(package_name, latest_data)
        
        # Get security vulnerabilities
        vulnerabilities = await self._check_vulnerabilities(package_name, latest_version)
        
        # Process all versions if requested
        versions_info = []
        if include_versions:
            versions_info = self._process_versions(data.get('versions', {}), data.get('time', {}))
        
        # Extract comprehensive metadata
        info = {
            'name': data.get('name'),
            'version': latest_version,
            'description': data.get('description'),
            'keywords': data.get('keywords', []),
            'homepage': data.get('homepage'),
            'bugs': data.get('bugs'),
            'license': data.get('license'),
            'author': self._format_person(data.get('author')),
            'maintainers': [self._format_person(m) for m in data.get('maintainers', [])],
            'repository': self._extract_repository_info(data.get('repository')),
            'readme': data.get('readme') if include_readme else None,
            'readmeFilename': data.get('readmeFilename'),
            'dist_tags': data.get('dist-tags', {}),
            'versions': versions_info,
            'time': {
                'created': data.get('time', {}).get('created'),
                'modified': data.get('time', {}).get('modified')
            },
            'users': data.get('users', {}),  # Users who starred
            'downloads': downloads,
            'typescript': types_info,
            'vulnerabilities': vulnerabilities,
            'latest_version_info': {
                'dependencies': self._categorize_dependencies(latest_data),
                'engines': latest_data.get('engines', {}),
                'bin': latest_data.get('bin'),
                'scripts': latest_data.get('scripts', {}),
                'dist': latest_data.get('dist', {}),
                'deprecated': latest_data.get('deprecated'),
                'funding': latest_data.get('funding'),
                'exports': latest_data.get('exports'),
                'type': latest_data.get('type'),  # "module" or "commonjs"
                'main': latest_data.get('main'),
                'module': latest_data.get('module'),
                'browser': latest_data.get('browser'),
                'files': latest_data.get('files', []),
                'directories': latest_data.get('directories', {}),
                'cpu': latest_data.get('cpu', []),
                'os': latest_data.get('os', []),
                'workspaces': latest_data.get('workspaces'),
                'publishConfig': latest_data.get('publishConfig', {})
            },
            'system_requirements': self._extract_detailed_requirements(latest_data)
        }
        
        return info
    
    async def get_package_version(self, package_name: str, version: str) -> Optional[Dict]:
        """Get specific version information"""
        package_name = normalize_package_name(package_name)
        encoded_name = quote(package_name, safe='@/')
        url = f"{self.registry_url}/{encoded_name}/{version}"
        
        data = await self._make_request(url)
        if not data:
            return None
        
        return {
            'name': data.get('name'),
            'version': data.get('version'),
            'description': data.get('description'),
            'main': data.get('main'),
            'module': data.get('module'),
            'browser': data.get('browser'),
            'type': data.get('type'),
            'dependencies': self._categorize_dependencies(data),
            'engines': data.get('engines', {}),
            'dist': data.get('dist', {}),
            'deprecated': data.get('deprecated'),
            'cpu': data.get('cpu', []),
            'os': data.get('os', []),
            'system_requirements': self._extract_detailed_requirements(data)
        }
    
    async def get_versions(self, package_name: str, 
                         include_prereleases: bool = True,
                         include_deprecated: bool = False) -> List[Dict]:
        """Get all versions with filtering options"""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info(package_name, include_readme=False, include_versions=True)
        if not info:
            return []
        
        versions = []
        for version_info in info.get('versions', []):
            # Filter prereleases
            if not include_prereleases and self._is_prerelease(version_info['version']):
                continue
            
            # Filter deprecated
            if not include_deprecated and version_info.get('deprecated'):
                continue
            
            versions.append(version_info)
        
        return versions
    
    async def resolve_version(self, package_name: str, version_spec: str) -> Optional[str]:
        """Resolve a version specification to a specific version"""
        package_name = normalize_package_name(package_name)
        versions = await self.get_versions(package_name, include_deprecated=False)
        if not versions:
            return None
        
        # Parse version requirement
        requirement = self._parse_version_requirement(version_spec)
        
        # Find matching versions
        matching_versions = []
        for v in versions:
            if self._version_matches_requirement(v['version'], requirement):
                matching_versions.append(v['version'])
        
        if not matching_versions:
            return None
        
        # Return the highest matching version
        return max(matching_versions, key=lambda v:  parse_version(v) or parse_version("0.0.0"))
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None,
                             types: Optional[List[DependencyType]] = None,
                             include_transitive: bool = False,
                             max_depth: int = 3) -> Dict[str, Any]:
        """Get package dependencies with optional transitive resolution"""
        package_name = normalize_package_name(package_name)
        if version:
            pkg_data = await self.get_package_version(package_name, version)
        else:
            info = await self.get_package_info(package_name, include_readme=False, include_versions=False)
            if not info:
                return {}
            pkg_data = info.get('latest_version_info', {})
        
        if not pkg_data:
            return {}
        
        deps = pkg_data.get('dependencies', {})
        
        # Filter by dependency types
        if types:
            type_names = [t.value for t in types]
            deps = {k: v for k, v in deps.items() if k in type_names}
        
        result = {
            'direct': deps,
            'transitive': {}
        }
        
        # Resolve transitive dependencies if requested
        if include_transitive:
            visited = set()
            result['transitive'] = await self._resolve_transitive_dependencies(
                deps.get('dependencies', {}),
                visited,
                max_depth
            )
        
        return result
    
    async def _resolve_transitive_dependencies(self, dependencies: Dict[str, str], 
                                             visited: Set[str], 
                                             max_depth: int,
                                             current_depth: int = 0) -> Dict[str, Dict]:
        """Recursively resolve transitive dependencies"""
        if current_depth >= max_depth:
            return {}
        
        transitive = {}
        
        for dep_name, version_spec in dependencies.items():
            normalized_dep_name = normalize_package_name(dep_name)
            if normalized_dep_name in visited:
                continue
            
            visited.add(normalized_dep_name)
            
            # Resolve version
            resolved_version = await self.resolve_version(normalized_dep_name, version_spec)
            if not resolved_version:
                continue
            
            # Get dependencies of this package
            dep_info = await self.get_package_version(normalized_dep_name, resolved_version)
            if not dep_info:
                continue
            
            dep_deps = dep_info.get('dependencies', {}).get('dependencies', {})
            
            transitive[dep_name] = {
                'version': resolved_version,
                'dependencies': dep_deps
            }
            
            # Recurse
            if dep_deps:
                sub_transitive = await self._resolve_transitive_dependencies(
                    dep_deps,
                    visited,
                    max_depth,
                    current_depth + 1
                )
                transitive.update(sub_transitive)
        
        return transitive
    
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
        
        # Check Node.js version
        engines = pkg_data.get('engines', {})
        if 'node' in engines and 'node_version' in system_info:
            if not self._check_node_compatibility(system_info['node_version'], engines['node']):
                errors.append(f"Requires Node.js {engines['node']}, but system has {system_info['node_version']}")
        
        # Check npm version
        if 'npm' in engines and 'npm_version' in system_info:
            if not self._check_npm_compatibility(system_info['npm_version'], engines['npm']):
                warnings.append(f"Recommends npm {engines['npm']}, but system has {system_info['npm_version']}")
        
        # Check OS compatibility
        supported_os = pkg_data.get('os', [])
        if supported_os and 'os' in system_info:
            if not self._check_os_compatibility(system_info['os'], supported_os):
                errors.append(f"Not compatible with OS: {system_info['os']}")
        
        # Check CPU architecture
        supported_cpu = pkg_data.get('cpu', [])
        if supported_cpu and 'cpu' in system_info:
            if not self._check_cpu_compatibility(system_info['cpu'], supported_cpu):
                errors.append(f"Not compatible with CPU architecture: {system_info['cpu']}")
        
        # Check for native dependencies
        if self._has_native_dependencies(pkg_data):
            if not system_info.get('has_build_tools', False):
                warnings.append("Package contains native dependencies requiring C++ build tools")
        
        # Check peer dependencies
        peer_deps = pkg_data.get('dependencies', {}).get('peerDependencies', {})
        if peer_deps and 'installed_packages' in system_info:
            for peer_name, peer_version in peer_deps.items():
                if peer_name not in system_info['installed_packages']:
                    warnings.append(f"Peer dependency missing: {peer_name}@{peer_version}")
                else:
                    installed_version = system_info['installed_packages'][peer_name]
                    if not self._version_satisfies(installed_version, peer_version):
                        warnings.append(f"Peer dependency version mismatch: {peer_name} requires {peer_version}, but {installed_version} is installed")
        
        return {
            'compatible': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'requirements': pkg_data.get('system_requirements', {})
        }
    
    async def get_dependency_tree(self, package_name: str, version: Optional[str] = None,
                                max_depth: int = 3) -> Dict[str, Any]:
        """Build a complete dependency tree"""
        package_name = normalize_package_name(package_name)
        tree = {
            'name': package_name,
            'version': version or 'latest',
            'dependencies': {}
        }
        
        # Resolve version if needed
        if not version:
            info = await self.get_package_info(package_name, include_readme=False, include_versions=False)
            if not info:
                return tree
            version = info['version']
            tree['version'] = version
        
        # Build tree recursively
        visited = set()
        tree['dependencies'] = await self._build_dependency_tree(
            package_name, version, visited, max_depth
        )
        
        return tree
    
    async def _build_dependency_tree(self, package_name: str, version: str,
                                   visited: Set[str], max_depth: int,
                                   current_depth: int = 0) -> Dict[str, Any]:
        """Recursively build dependency tree"""
        package_name = normalize_package_name(package_name)
        if current_depth >= max_depth:
            return {}
        
        key = f"{package_name}@{version}"
        if key in visited:
            return {'circular': True}
        
        visited.add(key)
        
        pkg_data = await self.get_package_version(package_name, version)
        if not pkg_data:
            return {}
        
        tree = {}
        deps = pkg_data.get('dependencies', {}).get('dependencies', {})
        
        for dep_name, version_spec in deps.items():
            normalized_dep_name = normalize_package_name(dep_name)
            resolved_version = await self.resolve_version(normalized_dep_name, version_spec)
            if not resolved_version:
                tree[dep_name] = {
                    'version': version_spec,
                    'resolved': False
                }
                continue
            
            tree[dep_name] = {
                'version': resolved_version,
                'resolved': True,
                'dependencies': await self._build_dependency_tree(
                    normalized_dep_name, resolved_version, visited, max_depth, current_depth + 1
                )
            }
        
        return tree
    
    async def analyze_package(self, package_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Comprehensive package analysis including quality metrics"""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info(package_name)
        if not info:
            return {}
        
        if not version:
            version = info['version']
        
        pkg_data = await self.get_package_version(package_name, version)
        if not pkg_data:
            return {}
        
        # Calculate various metrics
        analysis = {
            'name': package_name,
            'version': version,
            'metadata': {
                'description': info.get('description'),
                'license': info.get('license'),
                'author': info.get('author'),
                'homepage': info.get('homepage'),
                'repository': info.get('repository')
            },
            'metrics': {
                'size': pkg_data.get('dist', {}).get('unpackedSize', 0),
                'files_count': pkg_data.get('dist', {}).get('fileCount', 0),
                'has_readme': bool(info.get('readme')),
                'has_license': bool(info.get('license')),
                'has_repository': bool(info.get('repository')),
                'has_homepage': bool(info.get('homepage')),
                'has_types': info.get('typescript', {}).get('has_types', False),
                'last_publish': info.get('time', {}).get('modified'),
                'versions_count': len(info.get('versions', [])),
                'maintainers_count': len(info.get('maintainers', [])),
                'keywords_count': len(info.get('keywords', [])),
                'weekly_downloads': info.get('downloads', {}).get('weekly', 0)
            },
            'dependencies_analysis': {
                'direct_count': len(pkg_data.get('dependencies', {}).get('dependencies', {})),
                'dev_count': len(pkg_data.get('dependencies', {}).get('devDependencies', {})),
                'peer_count': len(pkg_data.get('dependencies', {}).get('peerDependencies', {})),
                'optional_count': len(pkg_data.get('dependencies', {}).get('optionalDependencies', {})),
                'has_native': self._has_native_dependencies(pkg_data),
                'has_deprecated': await self._has_deprecated_dependencies(pkg_data)
            },
            'security': {
                'vulnerabilities': info.get('vulnerabilities', []),
                'has_vulnerabilities': len(info.get('vulnerabilities', [])) > 0
            },
            'compatibility': {
                'node_versions': pkg_data.get('engines', {}).get('node'),
                'npm_versions': pkg_data.get('engines', {}).get('npm'),
                'platforms': {
                    'os': pkg_data.get('os', ['any']),
                    'cpu': pkg_data.get('cpu', ['any'])
                }
            },
            'quality_score': self._calculate_quality_score(info, pkg_data)
        }
        
        return analysis
    
    async def _get_download_stats(self, package_name: str) -> Dict[str, int]:
        """Get download statistics"""
        package_name = normalize_package_name(package_name)
        try:
            # Get last day, week, month, and year downloads
            endpoints = {
                'daily': f"/point/last-day/{quote(package_name)}",
                'weekly': f"/point/last-week/{quote(package_name)}",
                'monthly': f"/point/last-month/{quote(package_name)}",
                'yearly': f"/point/last-year/{quote(package_name)}"
            }
            
            stats = {}
            for period, endpoint in endpoints.items():
                url = f"{self.downloads_url}{endpoint}"
                data = await self._make_request(url)
                if data:
                    stats[period] = data.get('downloads', 0)
                else:
                    stats[period] = 0
            
            return stats
        except:
            return {'daily': 0, 'weekly': 0, 'monthly': 0, 'yearly': 0}
    
    async def _check_typescript_support(self, package_name: str, latest_data: Dict) -> Dict[str, Any]:
        """Check TypeScript support"""
        types_info = {
            'has_types': False,
            'types_package': None,
            'included': False
        }
        
        # Check if types are included
        if latest_data.get('types') or latest_data.get('typings'):
            types_info['has_types'] = True
            types_info['included'] = True
            return types_info
        
        # Check for @types package
        normalized_name = normalize_package_name(package_name)
        types_package_name = f"@types/{normalized_name.replace('@', '').replace('/', '__')}"
        types_exists = await self._package_exists(types_package_name)
        
        if types_exists:
            types_info['has_types'] = True
            types_info['types_package'] = types_package_name
        
        return types_info
    
    async def _package_exists(self, package_name: str) -> bool:
        """Check if a package exists"""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info(package_name, include_readme=False, include_versions=False)
        return info is not None
    
    async def _check_vulnerabilities(self, package_name: str, version: str) -> List[Dict]:
        """Check for known vulnerabilities (placeholder - would integrate with npm audit)"""
        package_name = normalize_package_name(package_name)
        # In a real implementation, this would query npm audit or a vulnerability database
        return []
    
    async def _has_deprecated_dependencies(self, pkg_data: Dict) -> bool:
        """Check if package has deprecated dependencies"""
        deps = pkg_data.get('dependencies', {}).get('dependencies', {})
        
        for dep_name, version_spec in deps.items():
            resolved_version = await self.resolve_version(dep_name, version_spec)
            if resolved_version:
                dep_info = await self.get_package_version(dep_name, resolved_version)
                if dep_info and dep_info.get('deprecated'):
                    return True
        
        return False
    
    def _calculate_quality_score(self, info: Dict, pkg_data: Dict) -> float:
        """Calculate a quality score based on various metrics"""
        score = 0.0
        max_score = 10.0
        
        # Documentation
        if info.get('readme'):
            score += 1.0
        if info.get('homepage'):
            score += 0.5
        if info.get('repository'):
            score += 0.5
        if info.get('license'):
            score += 1.0
        
        # Code quality indicators
        if info.get('keywords') and len(info['keywords']) > 0:
            score += 0.5
        if pkg_data.get('scripts', {}).get('test'):
            score += 1.0
        if info.get('typescript', {}).get('has_types'):
            score += 1.0
        
        # Maintenance
        if info.get('time', {}).get('modified'):
            last_modified = datetime.fromisoformat(info['time']['modified'].replace('Z', '+00:00'))
            days_since_update = (datetime.now(last_modified.tzinfo) - last_modified).days
            if days_since_update < 365:
                score += 1.0
            elif days_since_update < 730:
                score += 0.5
        
        # Popularity
        weekly_downloads = info.get('downloads', {}).get('weekly', 0)
        if weekly_downloads > 1000000:
            score += 2.0
        elif weekly_downloads > 10000:
            score += 1.5
        elif weekly_downloads > 1000:
            score += 1.0
        elif weekly_downloads > 100:
            score += 0.5
        
        # Security
        if not info.get('vulnerabilities'):
            score += 1.0
        
        return min(score / max_score, 1.0)
    
    def _process_versions(self, versions_data: Dict, time_data: Dict) -> List[Dict]:
        """Process version data"""
        versions = []
        
        for version, data in versions_data.items():
            # Validate version first
            if parse_version(version) is None: 
                logger.warning(f"Skipping invalid npm version: {version}")
                continue

            versions.append({
                'version': version,
                'deprecated': data.get('deprecated'),
                'published': time_data.get(version),
                'node': data.get('engines', {}).get('node'),
                'npm': data.get('engines', {}).get('npm'),
                'dist': {
                    'tarball': data.get('dist', {}).get('tarball'),
                    'shasum': data.get('dist', {}).get('shasum'),
                    'integrity': data.get('dist', {}).get('integrity'),
                    'size': data.get('dist', {}).get('unpackedSize', 0),
                    'fileCount': data.get('dist', {}).get('fileCount', 0)
                },
                'hasNativeDeps': self._has_native_dependencies(data)
            })
        
        # Sort by version (newest first)
        versions.sort(
            key=lambda x: parse_version(x['version']) or parse_version('0.0.0'), 
            reverse=True
        )
        
        return versions
    
    def _categorize_dependencies(self, version_data: Dict) -> Dict[str, Dict]:
        """Categorize dependencies by type"""
        return {
            'dependencies': version_data.get('dependencies', {}),
            'devDependencies': version_data.get('devDependencies', {}),
            'peerDependencies': version_data.get('peerDependencies', {}),
            'optionalDependencies': version_data.get('optionalDependencies', {}),
            'bundledDependencies': version_data.get('bundledDependencies', [])
        }
    
    def _extract_detailed_requirements(self, version_data: Dict) -> Dict[str, Any]:
        """Extract detailed system requirements"""
        requirements = {
            'node': None,
            'npm': None,
            'os': [],
            'cpu': [],
            'build_tools_required': False,
            'python_required': False,
            'native_modules': []
        }
        
        # Engine requirements
        engines = version_data.get('engines', {})
        if 'node' in engines:
            requirements['node'] = {
                'spec': engines['node'],
                'minimum': self._extract_min_version(engines['node'])
            }
        if 'npm' in engines:
            requirements['npm'] = {
                'spec': engines['npm'],
                'minimum': self._extract_min_version(engines['npm'])
            }
        
        # Platform requirements
        requirements['os'] = version_data.get('os', ['any'])
        requirements['cpu'] = version_data.get('cpu', ['any'])
        
        # Check for native dependencies
        deps = version_data.get('dependencies', {})
        native_indicators = [
            'node-gyp', 'prebuild', 'prebuild-install', 'node-pre-gyp',
            'bindings', 'nan', 'node-addon-api'
        ]
        
        for dep in deps:
            if any(indicator in dep.lower() for indicator in native_indicators):
                requirements['build_tools_required'] = True
                requirements['native_modules'].append(dep)
        
        # Check for Python requirement (common for native modules)
        if requirements['build_tools_required']:
            requirements['python_required'] = True
        
        # Check scripts for native compilation
        scripts = version_data.get('scripts', {})
        if any('node-gyp' in script or 'prebuild' in script for script in scripts.values()):
            requirements['build_tools_required'] = True
        
        return requirements
    
    def _parse_version_requirement(self, spec: str) -> VersionRequirement:
        """Parse a semver version requirement"""
        if spec in self._semver_cache:
            return self._semver_cache[spec]
        
        req = VersionRequirement(raw=spec)
        
        # Handle common patterns
        patterns = {
            r'^(\d+)\.(\d+)\.(\d+)$': lambda m: {'major': int(m[1]), 'minor': int(m[2]), 'patch': int(m[3])},
            r'^\^(\d+)\.(\d+)\.(\d+)': lambda m: {'operator': '^', 'major': int(m[1]), 'minor': int(m[2]), 'patch': int(m[3])},
            r'^~(\d+)\.(\d+)\.(\d+)': lambda m: {'operator': '~', 'major': int(m[1]), 'minor': int(m[2]), 'patch': int(m[3])},
            r'^>=?(\d+)\.(\d+)\.(\d+)': lambda m: {'operator': '>=', 'major': int(m[1]), 'minor': int(m[2]), 'patch': int(m[3])},
            r'^<=?(\d+)\.(\d+)\.(\d+)': lambda m: {'operator': '<=', 'major': int(m[1]), 'minor': int(m[2]), 'patch': int(m[3])},
            r'^\*|^$': lambda m: {'operator': '*'}
        }
        
        for pattern, handler in patterns.items():
            match = re.match(pattern, spec.strip())
            if match:
                for key, value in handler(match).items():
                    setattr(req, key, value)
                break
        
        self._semver_cache[spec] = req
        return req
    
    def _version_matches_requirement(self, version: str, requirement: VersionRequirement) -> bool:
        """Check if a version satisfies a requirement"""
        try:
            v = parse_version(version) 
            if v is None:  
                return False
            
            if requirement.operator == '*':
                return True
            
            if requirement.operator == '^':
                # Caret: compatible with version
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)  
                if req_v is None:  
                    return False

                if requirement.major > 0:
                    return v >= req_v and v.major == requirement.major
                elif requirement.minor > 0:
                    return v >= req_v and v.major == 0 and v.minor == requirement.minor
                else:
                    return v == req_v
            
            elif requirement.operator == '~':
                # Tilde: approximately equivalent
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)  # CHANGED
                next_minor_str = f"{requirement.major}.{requirement.minor + 1}.0"
                next_minor = parse_version(next_minor_str)  
                
                if req_v is None or next_minor is None: 
                    return False
                    
                return v >= req_v and v < next_minor
            
            elif requirement.operator == '>=':
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str) 
                if req_v is None: 
                    return False
                return v >= req_v
            
            elif requirement.operator == '<=':
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)  
                if req_v is None: 
                    return False
                return v <= req_v
            
            else:
                # Exact match
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)  
                if req_v is None: 
                    return False
                return v == req_v
                
        except:
            return False
    
    def _version_satisfies(self, installed: str, required: str) -> bool:
        """Check if installed version satisfies requirement"""
        req = self._parse_version_requirement(required)
        return self._version_matches_requirement(installed, req)
    
    def _check_node_compatibility(self, system_version: str, required: str) -> bool:
        """Check Node.js version compatibility"""
        return self._version_satisfies(system_version, required)
    
    def _check_npm_compatibility(self, system_version: str, required: str) -> bool:
        """Check npm version compatibility"""
        return self._version_satisfies(system_version, required)
    
    def _check_os_compatibility(self, system_os: str, supported: List[str]) -> bool:
        """Check OS compatibility"""
        if not supported or 'any' in supported:
            return True
        
        # Handle negations
        blocked = [os[1:] for os in supported if os.startswith('!')]
        allowed = [os for os in supported if not os.startswith('!')]
        
        if system_os in blocked:
            return False
        
        if allowed and system_os not in allowed:
            return False
        
        return True
    
    def _check_cpu_compatibility(self, system_cpu: str, supported: List[str]) -> bool:
        """Check CPU architecture compatibility"""
        if not supported or 'any' in supported:
            return True
        
        # Handle negations
        blocked = [cpu[1:] for cpu in supported if cpu.startswith('!')]
        allowed = [cpu for cpu in supported if not cpu.startswith('!')]
        
        if system_cpu in blocked:
            return False
        
        if allowed and system_cpu not in allowed:
            return False
        
        return True
    
    def _extract_min_version(self, version_spec: str) -> Optional[str]:
        """Extract minimum version from a spec"""
        # Simple extraction - could be enhanced
        match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', version_spec)
        if match:
            return match.group(0)
        return None
    
    def _has_native_dependencies(self, version_data: Dict) -> bool:
        """Check if package has native dependencies"""
        # Check direct indicators
        if version_data.get('gypfile'):
            return True
        
        # Check dependencies
        deps = version_data.get('dependencies', {})
        native_packages = [
            'node-gyp', 'prebuild', 'prebuild-install', 'node-pre-gyp',
            'bindings', 'nan', 'node-addon-api'
        ]
        
        return any(pkg in deps for pkg in native_packages)
    
    def _is_prerelease(self, version: str) -> bool:
        """Check if version is a prerelease"""
        return bool(re.search(r'-(alpha|beta|rc|pre|dev|canary|next)', version))
    
    def _format_person(self, person: Union[str, Dict]) -> Dict[str, str]:
        """Format person data (author/maintainer)"""
        if isinstance(person, str):
            # Parse "Name <email> (url)" format
            match = re.match(r'^([^<]+?)(?:\s*<([^>]+)>)?(?:\s*\(([^)]+)\))?$', person)
            if match:
                return {
                    'name': match.group(1).strip(),
                    'email': match.group(2),
                    'url': match.group(3)
                }
            return {'name': person}
        elif isinstance(person, dict):
            return {
                'name': person.get('name', ''),
                'email': person.get('email'),
                'url': person.get('url')
            }
        return {}
    
    def _extract_publisher(self, publisher: Union[str, Dict]) -> Dict[str, str]:
        """Extract publisher information"""
        if isinstance(publisher, dict):
            return {
                'username': publisher.get('username', ''),
                'email': publisher.get('email')
            }
        return {'username': str(publisher) if publisher else ''}
    
    def _extract_repository(self, links: Dict) -> Optional[str]:
        """Extract repository URL from links"""
        repo = links.get('repository')
        if repo:
            return repo
        
        # Try to extract from other links
        for key in ['homepage', 'bugs']:
            url = links.get(key, '')
            if 'github.com' in url or 'gitlab.com' in url or 'bitbucket.org' in url:
                # Extract base repo URL
                match = re.match(r'(https?://[^/]+/[^/]+/[^/]+)', url)
                if match:
                    return match.group(1)
        
        return None
    
    def _extract_repository_info(self, repository: Union[str, Dict]) -> Dict[str, str]:
        """Extract repository information"""
        if isinstance(repository, str):
            return {'type': 'git', 'url': repository}
        elif isinstance(repository, dict):
            return {
                'type': repository.get('type', 'git'),
                'url': repository.get('url', ''),
                'directory': repository.get('directory')
            }
        return {}

# Example usage
async def example_usage():
    async with NPMClient() as client:
        # Search with quality filters
        results = await client.search_packages(
            "react",
            limit=10,
            quality=0.8,
            popularity=0.5
        )
        
        # Get comprehensive package info
        info = await client.get_package_info("express", include_readme=True)
        
        # Resolve version from spec
        version = await client.resolve_version("lodash", "^4.17.0")
        
        # Get dependency tree
        tree = await client.get_dependency_tree("axios", max_depth=2)
        
        # Check compatibility
        compat = await client.check_compatibility(
            "node-sass",
            "7.0.0",
            {
                'node_version': '16.0.0',
                'npm_version': '8.0.0',
                'os': 'darwin',
                'cpu': 'x64',
                'has_build_tools': True
            }
        )
        
        # Analyze package quality
        analysis = await client.analyze_package("webpack")
        
        print(f"Quality score: {analysis['quality_score']}")

if __name__ == "__main__":
    asyncio.run(example_usage())