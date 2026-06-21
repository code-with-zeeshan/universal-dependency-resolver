#maven_client.py
import aiohttp
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any, Tuple, Set
from packaging import version
from datetime import datetime
from fastapi import HTTPException
from ..core.utils import normalize_package_name,  parse_version
import re
from urllib.parse import urljoin
from ..settings import (
    MAVEN_CENTRAL_URL,
    MAVEN_SEARCH_URL,
    MAVEN_ARTIFACT_URL,
    MAVEN_ADDITIONAL_REPOS,
    CACHE_TTL,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    USER_AGENTS,
    RATE_LIMITS,
    ENABLE_CACHE,
    get_ecosystem_config
)

import logging
logger = logging.getLogger(__name__)

class MavenClient:
    def __init__(self):
        # Get Maven-specific configuration
        maven_config = get_ecosystem_config('maven')
        
        # URLs from settings
        self.base_url = maven_config.get('search_url', MAVEN_SEARCH_URL)
        self.artifact_url = MAVEN_ARTIFACT_URL
        self.maven_repo_url = maven_config.get('url', MAVEN_CENTRAL_URL)
        
        # Additional repositories from settings
        self.additional_repos = MAVEN_ADDITIONAL_REPOS
        
        # Cache configuration
        self._pom_cache = {} if ENABLE_CACHE else None
        self._cache_ttl = maven_config.get('cache_ttl', CACHE_TTL)
        
        # HTTP client configuration
        self.timeout = REQUEST_TIMEOUT
        self.max_retries = MAX_RETRIES
        self.user_agent = USER_AGENTS.get('maven', USER_AGENTS['default'])
        self.rate_limit = maven_config.get('rate_limit', RATE_LIMITS.get('maven', 300))
        
        # Session for connection pooling
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'application/json, application/xml'
                }
            )
        return self._session
        
    async def __aenter__(self):
        await self._get_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _should_cache(self, url: str) -> bool:
        """Determine if response should be cached"""
        if not ENABLE_CACHE or self._pom_cache is None:
            return False
        # Don't cache search results
        return 'search' not in url
    
    async def _make_request(self, url: str, params: Optional[Dict] = None) -> Any:
        """Make HTTP request with retry and caching"""
        session = await self._get_session()
        
        # Check cache if applicable
        cache_key = f"{url}:{str(params)}"
        if self._should_cache(url) and cache_key in self._pom_cache:
            cached_data, cached_time = self._pom_cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                logger.debug(f"Cache hit for {url}")
                return cached_data
        
        # Make request with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 404:
                        return None
                    
                    if response.status != 200:
                        raise HTTPException(
                            status_code=response.status,
                            detail=f"Maven API error: {response.status}"
                        )
                    
                    # Handle JSON or XML response
                    content_type = response.headers.get('Content-Type', '')
                    if 'json' in content_type:
                        data = await response.json()
                    else:
                        data = await response.text()
                    
                    # Cache if applicable
                    if self._should_cache(url):
                        self._pom_cache[cache_key] = (data, datetime.now())
                        # Clean old cache entries if cache is too large
                        if len(self._pom_cache) > 1000:  # Arbitrary limit
                            self._clean_cache()
                    
                    return data
                    
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
        raise HTTPException(
            status_code=500,
            detail=f"Failed after {self.max_retries} attempts: {last_error}"
        )
    
    def _clean_cache(self):
        """Remove old cache entries"""
        if not self._pom_cache:
            return
            
        current_time = datetime.now()
        expired_keys = [
            key for key, (_, timestamp) in self._pom_cache.items()
            if (current_time - timestamp).total_seconds() > self._cache_ttl
        ]
        
        for key in expired_keys:
            del self._pom_cache[key]    

    def _normalize_maven_coordinates(self, group_id: str, artifact_id: str) -> Tuple[str, str]:
        """Normalize Maven coordinates (group_id and artifact_id)."""
        # Normalize artifact_id using the standard function
        artifact_id = normalize_package_name(artifact_id)
        
        # For group_id, normalize each component but keep dots
        # e.g., "org.apache.commons" -> "org.apache.commons"
        group_parts = group_id.split('.')
        normalized_parts = [normalize_package_name(part) for part in group_parts]
        group_id = '.'.join(normalized_parts)
        
        return group_id, artifact_id

    async def search_packages(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for Maven packages by query."""
        try:
            params = {
                "q": query,
                "rows": limit,
                "wt": "json"
            }
            
            data = await self._make_request(self.base_url, params=params)
            if not data:
                raise HTTPException(status_code=500, detail="Failed to search Maven packages")
            
            results = []
            for doc in data.get("response", {}).get("docs", []):
                results.append({
                    "name": f"{doc.get('g')}:{doc.get('a')}",
                    "ecosystem": "maven",
                    "version": doc.get("latestVersion"),
                    "description": doc.get("text", ["No description"])[0],
                    "system_requirements": {
                        "java_versions": ["8+"],  # Maven packages typically require Java 8+
                        "os": ["any"]
                    }
                })
            return results
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Maven search error: {str(e)}")

    async def get_package_info(self, group_id: str, artifact_id: str) -> Dict[str, Any]:
        """Get detailed info for a Maven package."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "q": f"g:{group_id} AND a:{artifact_id}",
                    "rows": 1,
                    "wt": "json"
                }
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        raise HTTPException(status_code=404, detail="Maven package not found")
                    data = await response.json()
                    docs = data.get("response", {}).get("docs", [])
                    if not docs:
                        raise HTTPException(status_code=404, detail="Maven package not found")
                    
                    doc = docs[0]
                    return {
                        "name": f"{group_id}:{artifact_id}",
                        "ecosystem": "maven",
                        "info": {
                            "group_id": group_id,
                            "artifact_id": artifact_id,
                            "latest_version": doc.get("latestVersion", "unknown"),
                            "last_updated": doc.get("timestamp", datetime.utcnow().isoformat()),
                            "repository_count": doc.get("repositoryCount", 0),
                            "available_versions": doc.get("versionCount", 0)
                        },
                        "system_requirements": {
                            "java_versions": ["8+"],
                            "os": ["any"]
                        },
                        "compatibility_matrix": {
                            "java": {"minimum": "1.8", "recommended": "11"}
                        }
                    }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Maven package info error: {str(e)}")

    async def get_package_versions(self, group_id: str, artifact_id: str, filters: Optional[Dict] = None) -> List[Dict]:
        """Get available versions for a Maven package."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            async with aiohttp.ClientSession() as session:
                params = {"q": f"g:{group_id} AND a:{artifact_id}", "core": "gav", "rows": 100, "wt": "json"}
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        raise HTTPException(status_code=404, detail="Maven package versions not found")
                    data = await response.json()
                    versions = []
                    
                    for doc in data.get("response", {}).get("docs", []):
                        version_str = doc.get("v")
                        if not version_str:
                            continue

                        # Validate version
                        parsed_version = parse_version(version_str)  # ADD THIS
                        if parsed_version is None and not self._is_maven_version(version_str):  # ADD THIS CHECK
                            logger.warning(f"Skipping invalid Maven version: {version_str}")
                            continue    
                            
                        version_info = {
                            "version": version_str,
                            "release_date": doc.get("timestamp", datetime.utcnow().isoformat()),
                            "system_requirements": {
                                "java_versions": ["8+"],
                                "os": ["any"]
                            }
                        }
                        
                        # Apply filters if provided
                        if filters:
                            # Filter by version range
                            if "version_range" in filters:
                                range_info = self._parse_version_range(filters["version_range"])
                                if not self._version_matches_range(version_str, range_info):
                                    continue
                            
                            # Filter by release type
                            if "release_type" in filters:
                                if filters["release_type"] == "stable" and ("SNAPSHOT" in version_str or "alpha" in version_str.lower() or "beta" in version_str.lower()):
                                    continue
                                elif filters["release_type"] == "snapshot" and "SNAPSHOT" not in version_str:
                                    continue
                        
                        versions.append(version_info)
                    
                    # Sort versions - handle Maven-specific versions
                    return sorted(versions, key=lambda x: self._sort_maven_version(x["version"]), reverse=True)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Maven versions error: {str(e)}")

    def _is_maven_version(self, version_str: str) -> bool:
        """Check if string is a valid Maven version (including SNAPSHOT, RC, etc.)"""
        # Maven allows versions like 1.0-SNAPSHOT, 1.0.0.RC1, etc.
        return bool(re.match(r'^\d+(\.\d+)*(-\w+)?$', version_str))
    
    def _sort_maven_version(self, version_str: str) -> tuple:
        """Create sortable tuple for Maven versions"""
        # Try standard parsing first
        parsed = parse_version(version_str)
        if parsed:
            return (parsed, 0)  # Standard versions come first
        
        # Handle Maven-specific versions
        if 'SNAPSHOT' in version_str:
            base_version = version_str.replace('-SNAPSHOT', '')
            parsed_base = parse_version(base_version)
            if parsed_base:
                return (parsed_base, 1)  # SNAPSHOTs come after releases
        
        # Fallback - use string comparison
        return (parse_version('0.0.0'), 2, version_str)        

    async def check_compatibility(self, group_id: str, artifact_id: str, version: str, system_info: Dict) -> Dict:
        """Check compatibility for a Maven package."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            # Get the POM to check actual requirements
            pom_xml = await self._fetch_pom(group_id, artifact_id, version)
            
            compatibility = {
                "compatible": True,
                "details": {},
                "warnings": [],
                "errors": []
            }
            
            if pom_xml:
                root = ET.fromstring(pom_xml)
                namespaces = {'maven': 'http://maven.apache.org/POM/4.0.0'}
                
                # Check Java version requirements
                properties = self._extract_properties(root, namespaces)
                
                java_version_props = [
                    "maven.compiler.source",
                    "maven.compiler.target", 
                    "java.version",
                    "project.build.sourceLevel"
                ]
                
                required_java = None
                for prop in java_version_props:
                    if prop in properties:
                        required_java = properties[prop]
                        break
                
                if required_java and "java_version" in system_info:
                    system_java = system_info["java_version"]
                    if self._compare_java_versions(system_java, required_java) < 0:
                        compatibility["compatible"] = False
                        compatibility["errors"].append(f"Requires Java {required_java} or higher, but system has Java {system_java}")
                    else:
                        compatibility["details"]["java_version"] = f"Compatible (requires Java {required_java}+)"
                else:
                    compatibility["details"]["java_version"] = "Compatible with Java 8+"
                
                # Check OS compatibility (usually all Maven packages are OS-independent)
                compatibility["details"]["os"] = "Compatible with any OS"
                
                # Check for native dependencies or OS-specific profiles
                profiles = self._parse_profiles(root, namespaces, properties)
                for profile_id, profile in profiles.items():
                    if "activation" in profile and "os" in profile["activation"]:
                        os_req = profile["activation"]["os"]
                        if os_req.get("name") and system_info.get("os_name"):
                            if os_req["name"].lower() not in system_info["os_name"].lower():
                                compatibility["warnings"].append(f"Profile '{profile_id}' is OS-specific for {os_req['name']}")
            
            return compatibility
            
        except Exception as e:
            return {
                "compatible": True,  # Assume compatible if we can't verify
                "details": {
                    "java_version": "Compatible with Java 8+",
                    "os": "Compatible with any OS"
                },
                "warnings": [f"Could not verify compatibility: {str(e)}"]
            }

    def _compare_java_versions(self, version1: str, version2: str) -> int:
        """Compare Java version strings. Returns -1 if version1 < version2, 0 if equal, 1 if greater."""
        # Extract major version numbers
        def extract_major(v):
            # Handle formats like "1.8", "11", "17", "1.8.0_281"
            v = v.split('_')[0]  # Remove update version
            parts = v.split('.')
            if parts[0] == '1' and len(parts) > 1:
                return int(parts[1])  # For 1.x format
            return int(parts[0])  # For modern format
        
        try:
            major1 = extract_major(version1)
            major2 = extract_major(version2)
            return (major1 > major2) - (major1 < major2)
        except:
            return 0  # If parsing fails, assume compatible

    async def get_dependencies(self, group_id: str, artifact_id: str, version: Optional[str] = None, 
                             active_profiles: Optional[List[str]] = None,
                             repositories: Optional[List[Dict]] = None) -> List[Dict]:
        """Get dependencies for a Maven package with full POM resolution."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            if not version:
                versions = await self.get_package_versions(group_id, artifact_id)
                if not versions:
                    return []
                version = versions[0]["version"]

            # Get effective POM (with parent inheritance)
            effective_pom = await self.get_effective_pom(group_id, artifact_id, version, active_profiles, repositories)
            
            return effective_pom.get('dependencies', [])

        except Exception as e:
            print(f"Error fetching dependencies: {str(e)}")
            return []

    async def get_effective_pom(self, group_id: str, artifact_id: str, version: str, 
                              active_profiles: Optional[List[str]] = None,
                              repositories: Optional[List[Dict]] = None) -> Dict:
        """Get the effective POM after all inheritance, property substitution, and profile application."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        
        # Initialize repository list with Maven Central
        if repositories is None:
            repositories = [{"id": "central", "url": self.maven_repo_url}]
        else:
            # Ensure Maven Central is included
            has_central = any(repo.get("id") == "central" for repo in repositories)
            if not has_central:
                repositories.append({"id": "central", "url": self.maven_repo_url})
        
        # Fetch and parse the POM with parent inheritance
        pom_data = await self._fetch_and_parse_pom_hierarchy(
            group_id, artifact_id, version, repositories, active_profiles
        )
        
        return pom_data

    async def _fetch_pom(self, group_id: str, artifact_id: str, version: str) -> Optional[str]:
        """Fetch POM file from Maven Central."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        # Convert group_id to path format (e.g., "org.apache.commons" -> "org/apache/commons")
        group_path = group_id.replace(".", "/")
        pom_url = f"{self.maven_repo_url}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(pom_url) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
        except Exception:
            return None

    async def _fetch_and_parse_pom_hierarchy(self, group_id: str, artifact_id: str, version: str,
                                           repositories: List[Dict], active_profiles: Optional[List[str]] = None,
                                           child_pom_data: Optional[Dict] = None) -> Dict:
        """Fetch POM and recursively fetch/merge parent POMs."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        
        # Check cache first
        cache_key = f"{group_id}:{artifact_id}:{version}"
        if cache_key in self._pom_cache:
            return self._pom_cache[cache_key].copy()
        
        # Fetch POM from repositories
        pom_xml = await self._fetch_pom_from_repos(group_id, artifact_id, version, repositories)
        if not pom_xml:
            return child_pom_data or {'dependencies': []}
        
        # Parse current POM
        current_pom = self._parse_pom_comprehensive(pom_xml, group_id, artifact_id, version, active_profiles)
        
        # If this POM has a parent, fetch and merge it
        if current_pom.get('parent'):
            parent = current_pom['parent']
            parent_pom = await self._fetch_and_parse_pom_hierarchy(
                parent['group_id'],
                parent['artifact_id'], 
                parent['version'],
                repositories + current_pom.get('repositories', []),
                active_profiles
            )
            
            # Merge parent POM with current POM
            merged_pom = self._merge_poms(parent_pom, current_pom)
        else:
            merged_pom = current_pom
        
        # If we have child POM data, merge it (child overrides parent)
        if child_pom_data:
            merged_pom = self._merge_poms(merged_pom, child_pom_data)
        
        # Apply final property substitution after all merging
        merged_pom = self._apply_final_property_substitution(merged_pom)
        
        # Cache the result
        self._pom_cache[cache_key] = merged_pom.copy()
        
        return merged_pom

    async def _fetch_pom_from_repos(self, group_id: str, artifact_id: str, version: str, 
                                   repositories: List[Dict]) -> Optional[str]:
        """Fetch POM from a list of repositories including configured ones."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        group_path = group_id.replace(".", "/")
        pom_filename = f"{artifact_id}-{version}.pom"
        pom_path = f"{group_path}/{artifact_id}/{version}/{pom_filename}"
        
        # Add additional repositories from settings
        all_repos = repositories.copy()
        for repo_url in self.additional_repos:
            if repo_url:
                all_repos.append({"url": repo_url, "id": f"additional-{len(all_repos)}"})
        
        # Ensure Maven Central is included
        if not any(repo.get("id") == "central" for repo in all_repos):
            all_repos.append({"id": "central", "url": self.maven_repo_url})
        
        for repo in all_repos:
            repo_url = repo.get("url", self.maven_repo_url).rstrip("/")
            pom_url = f"{repo_url}/{pom_path}"
            
            try:
                pom_content = await self._make_request(pom_url)
                if pom_content:
                    return pom_content
            except Exception:
                continue  # Try next repository
        
        return None

    def _merge_poms(self, parent_pom: Dict, child_pom: Dict) -> Dict:
        """Merge parent and child POMs according to Maven inheritance rules."""
        merged = {
            'properties': {},
            'dependency_management': {},
            'dependencies': [],
            'repositories': [],
            'plugin_repositories': [],
            'plugins': [],
            'plugin_management': {},
            'profiles': {},
            'exclusions': {},
            'modules': []
        }
        
        # Merge properties (child overrides parent)
        merged['properties'] = {**parent_pom.get('properties', {}), **child_pom.get('properties', {})}
        
        # Merge dependency management (child overrides parent)
        merged['dependency_management'] = {
            **parent_pom.get('dependency_management', {}),
            **child_pom.get('dependency_management', {})
        }
        
        # Merge dependencies (combine, but child can override versions via dependencyManagement)
        parent_deps = {f"{d['group_id']}:{d['artifact_id']}": d for d in parent_pom.get('dependencies', [])}
        child_deps = {f"{d['group_id']}:{d['artifact_id']}": d for d in child_pom.get('dependencies', [])}
        
        # Start with parent dependencies
        for key, dep in parent_deps.items():
            merged_dep = dep.copy()
            # Apply child's dependency management if exists
            if key in merged['dependency_management']:
                merged_dep.update(merged['dependency_management'][key])
            merged['dependencies'].append(merged_dep)
        
        # Add child dependencies (overriding parent if same artifact)
        for key, dep in child_deps.items():
            if key not in parent_deps:
                merged['dependencies'].append(dep)
            else:
                # Replace parent dependency with child's version
                for i, merged_dep in enumerate(merged['dependencies']):
                    if f"{merged_dep['group_id']}:{merged_dep['artifact_id']}" == key:
                        merged['dependencies'][i] = dep
                        break
        
        # Merge repositories (combine unique)
        repo_ids = set()
        for repo in parent_pom.get('repositories', []) + child_pom.get('repositories', []):
            if repo.get('id') not in repo_ids:
                merged['repositories'].append(repo)
                repo_ids.add(repo.get('id'))
        
        # Merge plugin repositories
        plugin_repo_ids = set()
        for repo in parent_pom.get('plugin_repositories', []) + child_pom.get('plugin_repositories', []):
            if repo.get('id') not in plugin_repo_ids:
                merged['plugin_repositories'].append(repo)
                plugin_repo_ids.add(repo.get('id'))
        
        # Merge plugins and plugin management
        merged['plugin_management'] = {
            **parent_pom.get('plugin_management', {}),
            **child_pom.get('plugin_management', {})
        }
        
        # Merge plugins (similar to dependencies)
        parent_plugins = {f"{p['group_id']}:{p['artifact_id']}": p for p in parent_pom.get('plugins', [])}
        child_plugins = {f"{p['group_id']}:{p['artifact_id']}": p for p in child_pom.get('plugins', [])}
        
        for key, plugin in parent_plugins.items():
            merged['plugins'].append(plugin)
        
        for key, plugin in child_plugins.items():
            if key not in parent_plugins:
                merged['plugins'].append(plugin)
            else:
                # Replace parent plugin with child's version
                for i, merged_plugin in enumerate(merged['plugins']):
                    if f"{merged_plugin['group_id']}:{merged_plugin['artifact_id']}" == key:
                        merged['plugins'][i] = plugin
                        break
        
        # Merge profiles (child overrides parent)
        merged['profiles'] = {**parent_pom.get('profiles', {}), **child_pom.get('profiles', {})}
        
        # Merge modules (child's modules only)
        merged['modules'] = child_pom.get('modules', [])
        
        # Keep other child-specific data
        for key in child_pom:
            if key not in merged:
                merged[key] = child_pom[key]
        
        return merged

    def _parse_pom_comprehensive(self, pom_xml: str, group_id: str, artifact_id: str, 
                                version: str, active_profiles: Optional[List[str]] = None) -> Dict:
        """Comprehensive POM parsing with all advanced features including exclusions and plugins."""
        try:
            root = ET.fromstring(pom_xml)
            namespaces = {'maven': 'http://maven.apache.org/POM/4.0.0'}
            
            # Initialize POM data structure
            pom_data = {
                'properties': {},
                'dependency_management': {},
                'dependencies': [],
                'repositories': [],
                'plugin_repositories': [],
                'plugins': [],
                'plugin_management': {},
                'profiles': {},
                'parent': None,
                'modules': []
            }
            
            # 1. Extract properties
            pom_data['properties'] = self._extract_properties(root, namespaces)
            
            # Add built-in Maven properties
            pom_data['properties'].update({
                'project.groupId': group_id,
                'project.artifactId': artifact_id,
                'project.version': version,
                'project.packaging': self._get_element_text(root, 'packaging', namespaces) or 'jar',
                'pom.groupId': group_id,
                'pom.artifactId': artifact_id,
                'pom.version': version
            })
            
            # 2. Parse parent POM reference
            parent_elem = root.find('.//maven:parent', namespaces) or root.find('.//parent')
            if parent_elem is not None:
                pom_data['parent'] = self._extract_parent_info(parent_elem, namespaces)
            
            # 3. Parse repositories
            pom_data['repositories'] = self._parse_repositories(root, namespaces, pom_data['properties'])
            
            # 4. Parse plugin repositories
            pom_data['plugin_repositories'] = self._parse_plugin_repositories(root, namespaces, pom_data['properties'])
            
            # 5. Parse dependency management
            dep_mgmt_elem = root.find('.//maven:dependencyManagement', namespaces) or root.find('.//dependencyManagement')
            if dep_mgmt_elem is not None:
                pom_data['dependency_management'] = self._parse_dependency_management(dep_mgmt_elem, namespaces, pom_data['properties'])
            
            # 6. Parse plugin management
            plugin_mgmt_elem = root.find('.//maven:build/maven:pluginManagement', namespaces) or root.find('.//build/pluginManagement')
            if plugin_mgmt_elem is not None:
                pom_data['plugin_management'] = self._parse_plugin_management(plugin_mgmt_elem, namespaces, pom_data['properties'])
            
            # 7. Parse profiles
            profiles_elem = root.find('.//maven:profiles', namespaces) or root.find('.//profiles')
            if profiles_elem is not None:
                pom_data['profiles'] = self._parse_profiles(profiles_elem, namespaces, pom_data['properties'])
            
            # 8. Parse main dependencies with exclusions
            deps_elem = root.find('.//maven:dependencies', namespaces) or root.find('.//dependencies')
            if deps_elem is not None:
                main_deps = self._parse_dependencies_section(deps_elem, namespaces, pom_data['properties'], pom_data['dependency_management'])
                pom_data['dependencies'].extend(main_deps)
            
            # 9. Parse plugins
            plugins_elem = root.find('.//maven:build/maven:plugins', namespaces) or root.find('.//build/plugins')
            if plugins_elem is not None:
                pom_data['plugins'] = self._parse_plugins_section(plugins_elem, namespaces, pom_data['properties'], pom_data['plugin_management'])
            
            # 10. Parse modules
            modules = root.findall('.//maven:module', namespaces) or root.findall('.//module')
            pom_data['modules'] = [self._substitute_properties(m.text.strip(), pom_data['properties']) for m in modules if m.text]
            
            # 11. Apply active profiles
            if active_profiles:
                pom_data = self._apply_profiles(pom_data, active_profiles)
            
            # 12. Apply default profiles
            pom_data = self._apply_default_profiles(pom_data, active_profiles)
            
            return pom_data
            
        except ET.ParseError as e:
            print(f"XML Parse error: {str(e)}")
            return {'dependencies': []}

    def _extract_properties(self, root, namespaces) -> Dict[str, str]:
        """Extract properties from POM."""
        properties = {}
        props_elem = root.find('.//maven:properties', namespaces) or root.find('.//properties')
        
        if props_elem is not None:
            for prop in props_elem:
                # Remove namespace prefix if present
                tag = prop.tag.split('}')[-1] if '}' in prop.tag else prop.tag
                if prop.text:
                    properties[tag] = prop.text.strip()
        
        return properties

    def _substitute_properties(self, value: str, properties: Dict[str, str]) -> str:
        """Substitute ${property} placeholders with actual values."""
        if not value or '${' not in value:
            return value
        
        # Pattern to match ${property.name}
        pattern = re.compile(r'\$\{([^}]+)\}')
        
        def replace_property(match):
            prop_name = match.group(1)
            # Handle nested properties
            if prop_name in properties:
                # Recursively substitute in case the property value contains other properties
                return self._substitute_properties(properties[prop_name], properties)
            return match.group(0)  # Return unchanged if property not found
        
        # Keep replacing until no more substitutions are possible (for nested properties)
        max_iterations = 10
        for _ in range(max_iterations):
            new_value = pattern.sub(replace_property, value)
            if new_value == value:
                break
            value = new_value
        
        return value

    def _extract_parent_info(self, parent_elem, namespaces) -> Optional[Dict]:
        """Extract parent POM information."""
        try:
            group_id = self._get_element_text(parent_elem, 'groupId', namespaces)
            artifact_id = self._get_element_text(parent_elem, 'artifactId', namespaces)
            version = self._get_element_text(parent_elem, 'version', namespaces)
            
            if group_id and artifact_id:
                return {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "scope": "parent",
                    "optional": False,
                    "type": "parent"
                }
        except Exception:
            pass
        return None

    def _parse_repositories(self, root, namespaces, properties) -> List[Dict]:
        """Parse repository definitions."""
        repositories = []
        
        repos_elem = root.find('.//maven:repositories', namespaces) or root.find('.//repositories')
        if repos_elem is not None:
            for repo in repos_elem.findall('.//maven:repository', namespaces) or repos_elem.findall('.//repository'):
                repo_info = {
                    'id': self._substitute_properties(self._get_element_text(repo, 'id', namespaces), properties),
                    'url': self._substitute_properties(self._get_element_text(repo, 'url', namespaces), properties),
                    'layout': self._get_element_text(repo, 'layout', namespaces) or 'default'
                }
                
                # Parse repository policies
                releases_elem = repo.find('.//maven:releases', namespaces) or repo.find('.//releases')
                if releases_elem is not None:
                    repo_info['releases'] = {
                        'enabled': self._get_element_text(releases_elem, 'enabled', namespaces) != 'false',
                        'updatePolicy': self._get_element_text(releases_elem, 'updatePolicy', namespaces) or 'daily',
                        'checksumPolicy': self._get_element_text(releases_elem, 'checksumPolicy', namespaces) or 'warn'
                    }
                
                snapshots_elem = repo.find('.//maven:snapshots', namespaces) or repo.find('.//snapshots')
                if snapshots_elem is not None:
                    repo_info['snapshots'] = {
                        'enabled': self._get_element_text(snapshots_elem, 'enabled', namespaces) == 'true',
                        'updatePolicy': self._get_element_text(snapshots_elem, 'updatePolicy', namespaces) or 'daily',
                        'checksumPolicy': self._get_element_text(snapshots_elem, 'checksumPolicy', namespaces) or 'warn'
                    }
                
                repositories.append(repo_info)
        
        return repositories

    def _parse_plugin_repositories(self, root, namespaces, properties) -> List[Dict]:
        """Parse plugin repository definitions."""
        repositories = []
        
        repos_elem = root.find('.//maven:pluginRepositories', namespaces) or root.find('.//pluginRepositories')
        if repos_elem is not None:
            for repo in repos_elem.findall('.//maven:pluginRepository', namespaces) or repos_elem.findall('.//pluginRepository'):
                repo_info = {
                    'id': self._substitute_properties(self._get_element_text(repo, 'id', namespaces), properties),
                    'url': self._substitute_properties(self._get_element_text(repo, 'url', namespaces), properties),
                    'layout': self._get_element_text(repo, 'layout', namespaces) or 'default'
                }
                repositories.append(repo_info)
        
        return repositories

    def _parse_dependency_management(self, dep_mgmt_elem, namespaces, properties) -> Dict[str, Dict]:
        """Parse dependencyManagement section."""
        dep_management = {}
        
        deps_elem = dep_mgmt_elem.find('.//maven:dependencies', namespaces) or dep_mgmt_elem.find('.//dependencies')
        if deps_elem is not None:
            for dep in deps_elem.findall('.//maven:dependency', namespaces) or deps_elem.findall('.//dependency'):
                dep_info = self._extract_dependency_info(dep, namespaces, properties, {})
                if dep_info:
                    key = f"{dep_info['group_id']}:{dep_info['artifact_id']}"
                    dep_management[key] = dep_info
        
        return dep_management

    def _parse_plugin_management(self, plugin_mgmt_elem, namespaces, properties) -> Dict[str, Dict]:
        """Parse pluginManagement section."""
        plugin_management = {}
        
        plugins_elem = plugin_mgmt_elem.find('.//maven:plugins', namespaces) or plugin_mgmt_elem.find('.//plugins')
        if plugins_elem is not None:
            for plugin in plugins_elem.findall('.//maven:plugin', namespaces) or plugins_elem.findall('.//plugin'):
                plugin_info = self._extract_plugin_info(plugin, namespaces, properties, {})
                if plugin_info:
                    key = f"{plugin_info['group_id']}:{plugin_info['artifact_id']}"
                    plugin_management[key] = plugin_info
        
        return plugin_management

    def _parse_profiles(self, profiles_elem, namespaces, parent_properties) -> Dict[str, Dict]:
        """Parse profiles section."""
        profiles = {}
        
        for profile in profiles_elem.findall('.//maven:profile', namespaces) or profiles_elem.findall('.//profile'):
            profile_id = self._get_element_text(profile, 'id', namespaces)
            if not profile_id:
                continue
            
            profile_data = {
                'id': profile_id,
                'properties': {},
                'dependencies': [],
                'dependency_management': {},
                'activeByDefault': False,
                'activation': {}
            }
            
            # Parse activation
            activation_elem = profile.find('.//maven:activation', namespaces) or profile.find('.//activation')
            if activation_elem is not None:
                active_by_default = self._get_element_text(activation_elem, 'activeByDefault', namespaces)
                profile_data['activeByDefault'] = active_by_default == 'true'
                
                # Parse other activation conditions
                profile_data['activation'] = self._parse_activation(activation_elem, namespaces)
            
            # Parse profile properties
            props_elem = profile.find('.//maven:properties', namespaces) or profile.find('.//properties')
            if props_elem is not None:
                profile_props = self._extract_properties(profile, namespaces)
                # Merge with parent properties for substitution
                all_props = {**parent_properties, **profile_props}
                # Substitute properties in profile properties
                for key, value in profile_props.items():
                    profile_data['properties'][key] = self._substitute_properties(value, all_props)
            
            # Parse profile dependencies
            deps_elem = profile.find('.//maven:dependencies', namespaces) or profile.find('.//dependencies')
            if deps_elem is not None:
                all_props = {**parent_properties, **profile_data['properties']}
                profile_data['dependencies'] = self._parse_dependencies_section(deps_elem, namespaces, all_props, {})
            
            # Parse profile dependency management
            dep_mgmt_elem = profile.find('.//maven:dependencyManagement', namespaces) or profile.find('.//dependencyManagement')
            if dep_mgmt_elem is not None:
                all_props = {**parent_properties, **profile_data['properties']}
                profile_data['dependency_management'] = self._parse_dependency_management(dep_mgmt_elem, namespaces, all_props)
            
            profiles[profile_id] = profile_data
        
        return profiles

    def _parse_activation(self, activation_elem, namespaces) -> Dict:
        """Parse profile activation conditions."""
        activation = {}
        
        # JDK version
        jdk = self._get_element_text(activation_elem, 'jdk', namespaces)
        if jdk:
            activation['jdk'] = jdk
        
        # OS
        os_elem = activation_elem.find('.//maven:os', namespaces) or activation_elem.find('.//os')
        if os_elem is not None:
            activation['os'] = {
                'name': self._get_element_text(os_elem, 'name', namespaces),
                'family': self._get_element_text(os_elem, 'family', namespaces),
                'arch': self._get_element_text(os_elem, 'arch', namespaces),
                'version': self._get_element_text(os_elem, 'version', namespaces)
            }
        
        # Property
        prop_elem = activation_elem.find('.//maven:property', namespaces) or activation_elem.find('.//property')
        if prop_elem is not None:
            activation['property'] = {
                'name': self._get_element_text(prop_elem, 'name', namespaces),
                'value': self._get_element_text(prop_elem, 'value', namespaces)
            }
        
        return activation

    def _parse_dependencies_section(self, deps_elem, namespaces, properties, dep_management) -> List[Dict]:
        """Parse a dependencies section with exclusions."""
        dependencies = []
        
        for dep in deps_elem.findall('.//maven:dependency', namespaces) or deps_elem.findall('.//dependency'):
            dep_info = self._extract_dependency_info_with_exclusions(dep, namespaces, properties, dep_management)
            if dep_info:
                dependencies.append(dep_info)
        
        return dependencies

    def _extract_dependency_info(self, dep_elem, namespaces, properties, dep_management) -> Optional[Dict]:
        """Extract dependency information with property substitution and version management."""
        try:
            # Extract basic info
            group_id = self._get_element_text(dep_elem, 'groupId', namespaces)
            artifact_id = self._get_element_text(dep_elem, 'artifactId', namespaces)
            version = self._get_element_text(dep_elem, 'version', namespaces)
            scope = self._get_element_text(dep_elem, 'scope', namespaces) or 'compile'
            optional = self._get_element_text(dep_elem, 'optional', namespaces) == 'true'
            dep_type = self._get_element_text(dep_elem, 'type', namespaces) or 'jar'
            classifier = self._get_element_text(dep_elem, 'classifier', namespaces)
            
            # Substitute properties
            group_id = self._substitute_properties(group_id, properties) if group_id else None
            artifact_id = self._substitute_properties(artifact_id, properties) if artifact_id else None
            version = self._substitute_properties(version, properties) if version else None

            # Normalize the coordinates AFTER property substitution  # ADD THIS
            if group_id and artifact_id:
                group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
            
            # Apply dependency management
            if group_id and artifact_id:
                dep_key = f"{group_id}:{artifact_id}"
                if dep_key in dep_management and not version:
                    managed_dep = dep_management[dep_key]
                    version = managed_dep.get('version', version)
                    scope = scope or managed_dep.get('scope', 'compile')
                
                # Parse version range if present
                version_info = self._parse_version_range(version) if version else None
                
                return {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "version_range": version_info,
                    "scope": scope,
                    "optional": optional,
                    "type": "dependency",
                    "classifier": classifier,
                    "packaging": dep_type
                }
        except Exception as e:
            print(f"Error extracting dependency: {str(e)}")
        return None

    def _extract_dependency_info_with_exclusions(self, dep_elem, namespaces, properties, dep_management) -> Optional[Dict]:
        """Extract dependency information including exclusions."""
        dep_info = self._extract_dependency_info(dep_elem, namespaces, properties, dep_management)
        
        if dep_info:
            # Parse exclusions
            exclusions = []
            exclusions_elem = dep_elem.find('.//maven:exclusions', namespaces) or dep_elem.find('.//exclusions')
            
            if exclusions_elem is not None:
                for exclusion in exclusions_elem.findall('.//maven:exclusion', namespaces) or exclusions_elem.findall('.//exclusion'):
                    exc_group_id = self._get_element_text(exclusion, 'groupId', namespaces)
                    exc_artifact_id = self._get_element_text(exclusion, 'artifactId', namespaces)
                    
                    if exc_group_id or exc_artifact_id:
                        exclusions.append({
                            'group_id': self._substitute_properties(exc_group_id, properties) if exc_group_id else '*',
                            'artifact_id': self._substitute_properties(exc_artifact_id, properties) if exc_artifact_id else '*'
                        })
                
            if exclusions:
                dep_info['exclusions'] = exclusions
        
        return dep_info

    def _parse_plugins_section(self, plugins_elem, namespaces, properties, plugin_management) -> List[Dict]:
        """Parse plugins section."""
        plugins = []
        
        for plugin in plugins_elem.findall('.//maven:plugin', namespaces) or plugins_elem.findall('.//plugin'):
            plugin_info = self._extract_plugin_info(plugin, namespaces, properties, plugin_management)
            if plugin_info:
                plugins.append(plugin_info)
        
        return plugins

    def _extract_plugin_info(self, plugin_elem, namespaces, properties, plugin_management) -> Optional[Dict]:
        """Extract plugin information."""
        try:
            group_id = self._get_element_text(plugin_elem, 'groupId', namespaces) or 'org.apache.maven.plugins'
            artifact_id = self._get_element_text(plugin_elem, 'artifactId', namespaces)
            version = self._get_element_text(plugin_elem, 'version', namespaces)
            
            # Substitute properties
            group_id = self._substitute_properties(group_id, properties)
            artifact_id = self._substitute_properties(artifact_id, properties)
            version = self._substitute_properties(version, properties) if version else None
            
            # Apply plugin management
            if group_id and artifact_id:
                plugin_key = f"{group_id}:{artifact_id}"
                if plugin_key in plugin_management and not version:
                    managed_plugin = plugin_management[plugin_key]
                    version = managed_plugin.get('version', version)
                
                plugin_info = {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "type": "plugin",
                    "dependencies": []
                }
                
                # Parse plugin dependencies
                deps_elem = plugin_elem.find('.//maven:dependencies', namespaces) or plugin_elem.find('.//dependencies')
                if deps_elem is not None:
                    plugin_info['dependencies'] = self._parse_dependencies_section(deps_elem, namespaces, properties, {})
                
                # Parse plugin configuration
                config_elem = plugin_elem.find('.//maven:configuration', namespaces) or plugin_elem.find('.//configuration')
                if config_elem is not None:
                    plugin_info['configuration'] = self._parse_configuration(config_elem, properties)
                
                # Parse executions
                executions = []
                for exec_elem in plugin_elem.findall('.//maven:execution', namespaces) or plugin_elem.findall('.//execution'):
                    execution = {
                        'id': self._get_element_text(exec_elem, 'id', namespaces) or 'default',
                        'phase': self._get_element_text(exec_elem, 'phase', namespaces),
                        'goals': [g.text.strip() for g in (exec_elem.findall('.//maven:goal', namespaces) or exec_elem.findall('.//goal')) if g.text]
                    }
                    executions.append(execution)
                
                if executions:
                    plugin_info['executions'] = executions
                
                return plugin_info
                
        except Exception as e:
            print(f"Error extracting plugin: {str(e)}")
        return None

    def _parse_configuration(self, config_elem, properties) -> Dict:
        """Parse plugin configuration as a dictionary."""
        config = {}
        
        for child in config_elem:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if len(child) == 0:
                # Leaf element
                if child.text:
                    config[tag] = self._substitute_properties(child.text.strip(), properties)
            else:
                # Has children
                config[tag] = self._parse_configuration(child, properties)
        
        return config

    def _parse_version_range(self, version_str: str) -> Dict[str, Any]:
        """Parse Maven version ranges."""
        if not version_str:
            return {"type": "unspecified"}
        
        # Check for version ranges
        if version_str.startswith('[') or version_str.startswith('('):
            return self._parse_version_range_syntax(version_str)
        else:
            # Fixed version
            return {
                "type": "fixed",
                "version": version_str
            }

    def _parse_version_range_syntax(self, range_str: str) -> Dict[str, Any]:
        """Parse Maven version range syntax like [1.0,2.0), (,1.0], [1.0,)"""
        range_info = {
            "type": "range",
            "raw": range_str,
            "min_version": None,
            "max_version": None,
            "min_inclusive": False,
            "max_inclusive": False
        }
        
        # Remove whitespace
        range_str = range_str.strip()
        
        # Check brackets
        if range_str.startswith('['):
            range_info["min_inclusive"] = True
        elif range_str.startswith('('):
            range_info["min_inclusive"] = False
        
        if range_str.endswith(']'):
            range_info["max_inclusive"] = True
        elif range_str.endswith(')'):
            range_info["max_inclusive"] = False
        
        # Extract version numbers
        inner = range_str[1:-1]  # Remove brackets
        parts = inner.split(',')
        
        if len(parts) == 1:
            # Single version like [1.0]
            range_info["min_version"] = parts[0].strip()
            range_info["max_version"] = parts[0].strip()
        elif len(parts) == 2:
            # Range like [1.0,2.0)
            if parts[0].strip():
                range_info["min_version"] = parts[0].strip()
            if parts[1].strip():
                range_info["max_version"] = parts[1].strip()
        
        return range_info

    async def resolve_version_from_range(self, group_id: str, artifact_id: str, version_range: Dict) -> Optional[str]:
        """Resolve a specific version from a version range."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        if version_range["type"] == "fixed":
            return version_range["version"]
        
        # Get all available versions
        versions = await self.get_package_versions(group_id, artifact_id)
        if not versions:
            return None
        
        available_versions = [v["version"] for v in versions]
        
        if version_range["type"] == "range":
            matching_versions = []
            
            for v in available_versions:
                if self._version_matches_range(v, version_range):
                    matching_versions.append(v)
            
            # Return the highest matching version
            if matching_versions:
                return sorted(matching_versions, key=lambda x: version.parse(x), reverse=True)[0]
        
        return None

    def _version_matches_range(self, version_str: str, range_info: Dict) -> bool:
        """Check if a version matches a version range."""
        try:
            v = parse_version(version_str)
            if v is None:  # ADD THIS CHECK
                # Handle Maven-specific versions
                if self._is_maven_version(version_str):
                    # For SNAPSHOT versions, extract base version
                    if 'SNAPSHOT' in version_str:
                        base_version = version_str.replace('-SNAPSHOT', '')
                        v = parse_version(base_version)
                        if v is None:
                            return False
                else:
                    return False
            
            # Check minimum
            if range_info["min_version"]:
                min_v = parse_version(range_info["min_version"])  # CHANGED THIS
                if min_v is None:  # ADD THIS CHECK
                    return False
                if range_info["min_inclusive"]:
                    if v < min_v:
                        return False
                else:
                    if v <= min_v:
                        return False
            
            # Check maximum
            if range_info["max_version"]:
                max_v = parse_version(range_info["max_version"])  # CHANGED THIS
                if max_v is None:  # ADD THIS CHECK
                    return False
                if range_info["max_inclusive"]:
                    if v > max_v:
                        return False
                else:
                    if v >= max_v:
                        return False
            
            return True
        except:
            return False

    def _apply_profiles(self, pom_data: Dict, active_profiles: List[str]) -> Dict:
        """Apply active profiles to POM data."""
        for profile_id in active_profiles:
            if profile_id in pom_data.get('profiles', {}):
                profile = pom_data['profiles'][profile_id]
                
                # Merge profile properties
                pom_data['properties'].update(profile.get('properties', {}))
                
                # Add profile dependencies
                pom_data['dependencies'].extend(profile.get('dependencies', []))
                
                # Merge profile dependency management
                if 'dependency_management' in profile:
                    pom_data['dependency_management'].update(profile['dependency_management'])
                
                # Add profile repositories
                pom_data['repositories'].extend(profile.get('repositories', []))
                
                # Add profile plugins
                pom_data['plugins'].extend(profile.get('plugins', []))
                
                # Merge profile plugin management
                if 'plugin_management' in profile:
                    pom_data['plugin_management'].update(profile['plugin_management'])
        
        return pom_data

    def _apply_default_profiles(self, pom_data: Dict, active_profiles: Optional[List[str]]) -> Dict:
        """Apply default profiles if no profiles are explicitly activated."""
        if active_profiles:
            return pom_data
        
        for profile_id, profile in pom_data.get('profiles', {}).items():
            if profile.get('activeByDefault', False):
                # Apply this profile
                pom_data['properties'].update(profile.get('properties', {}))
                pom_data['dependencies'].extend(profile.get('dependencies', []))
                if 'dependency_management' in profile:
                    pom_data['dependency_management'].update(profile['dependency_management'])
                pom_data['repositories'].extend(profile.get('repositories', []))
                pom_data['plugins'].extend(profile.get('plugins', []))
                if 'plugin_management' in profile:
                    pom_data['plugin_management'].update(profile['plugin_management'])
        
        return pom_data

    def _apply_final_property_substitution(self, pom_data: Dict) -> Dict:
        """Apply final property substitution after all merging is complete."""
        # Re-substitute all properties in dependencies
        for dep in pom_data.get('dependencies', []):
            for key in ['group_id', 'artifact_id', 'version']:
                if key in dep and dep[key]:
                    dep[key] = self._substitute_properties(dep[key], pom_data['properties'])
        
        # Re-substitute in plugins
        for plugin in pom_data.get('plugins', []):
            for key in ['group_id', 'artifact_id', 'version']:
                if key in plugin and plugin[key]:
                    plugin[key] = self._substitute_properties(plugin[key], pom_data['properties'])
        
        return pom_data

    async def get_transitive_dependencies(self, group_id: str, artifact_id: str, version: str,
                                        scope: str = "compile", repositories: Optional[List[Dict]] = None,
                                        visited: Optional[Set[str]] = None, exclusions: Optional[List[Dict]] = None) -> List[Dict]:
        """Get all transitive dependencies respecting exclusions and scope."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        if visited is None:
            visited = set()
        
        key = f"{group_id}:{artifact_id}:{version}"
        if key in visited:
            return []
        
        visited.add(key)
        
        # Check if this dependency is excluded
        if exclusions:
            for exclusion in exclusions:
                exc_group = exclusion.get('group_id', '*')
                exc_artifact = exclusion.get('artifact_id', '*')
                
                if ((exc_group == '*' or exc_group == group_id) and 
                    (exc_artifact == '*' or exc_artifact == artifact_id)):
                    return []
        
        # Get effective POM
        effective_pom = await self.get_effective_pom(group_id, artifact_id, version, None, repositories)
        
        all_dependencies = []
        
        # Process direct dependencies
        for dep in effective_pom.get('dependencies', []):
            dep_scope = dep.get('scope', 'compile')
            
            # Check scope inheritance rules
            if not self._should_include_transitive_dependency(scope, dep_scope):
                continue
            
            # Add the dependency
            all_dependencies.append(dep)
            
            # Get transitive dependencies
            if dep.get('version') and dep.get('version') != 'unspecified':
                transitive = await self.get_transitive_dependencies(
                    dep['group_id'],
                    dep['artifact_id'],
                    dep['version'],
                    dep_scope,
                    repositories + effective_pom.get('repositories', []),
                    visited,
                    dep.get('exclusions', [])
                )
                all_dependencies.extend(transitive)
        
        return all_dependencies

    def _should_include_transitive_dependency(self, parent_scope: str, dep_scope: str) -> bool:
        """Determine if a transitive dependency should be included based on scope rules."""
        # Maven scope transitivity rules
        scope_rules = {
            'compile': ['compile', 'runtime'],
            'runtime': ['runtime'],
            'test': ['compile', 'runtime', 'test'],
            'provided': [],  # Provided dependencies are not transitive
            'system': []     # System dependencies are not transitive
        }
        
        allowed_scopes = scope_rules.get(parent_scope, [])
        return dep_scope in allowed_scopes

    async def get_dependency_tree(self, group_id: str, artifact_id: str, version: Optional[str] = None, 
                                  max_depth: int = 2, visited: Optional[set] = None) -> Dict:
        """Get dependency tree with transitive dependencies (limited depth to avoid infinite recursion)."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        if visited is None:
            visited = set()
        
        # Avoid circular dependencies
        key = f"{group_id}:{artifact_id}:{version}"
        if key in visited or max_depth <= 0:
            return {
                "name": f"{group_id}:{artifact_id}",
                "version": version,
                "dependencies": []
            }
        
        visited.add(key)
        
        # Get direct dependencies
        dependencies = await self.get_dependencies(group_id, artifact_id, version)
        
        # Build tree structure
        tree = {
            "name": f"{group_id}:{artifact_id}",
            "version": version or "latest",
            "dependencies": []
        }
        
        # Recursively get transitive dependencies (with limited depth)
        for dep in dependencies:
            if dep.get("scope") not in ["test", "provided"] and not dep.get("optional"):
                dep_tree = await self.get_dependency_tree(
                    dep["group_id"], 
                    dep["artifact_id"], 
                    dep.get("version"),
                    max_depth - 1,
                    visited
                )
                tree["dependencies"].append(dep_tree)
        
        return tree

    def _get_element_text(self, parent, tag, namespaces) -> Optional[str]:
        """Get text from an XML element, trying with and without namespace."""
        # Try with namespace
        elem = parent.find(f'.//maven:{tag}', namespaces)
        if elem is not None and elem.text:
            return elem.text.strip()
        
        # Try without namespace  
        elem = parent.find(f'.//{tag}')
        if elem is not None and elem.text:
            return elem.text.strip()
        
        return None