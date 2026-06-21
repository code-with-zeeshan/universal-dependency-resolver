# conda_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Set, Tuple
import json
import logging
from datetime import datetime
import re
import yaml
import tarfile
import io
from packaging import version
from urllib.parse import urljoin
from ..core.utils import normalize_package_name,  parse_version
from ..settings import CONDA_CHANNELS, CACHE_TTL, USER_AGENTS

logger = logging.getLogger(__name__)

class CondaClient:
    def __init__(self):
        self.channels = CONDA_CHANNELS.copy()  # Use channels from settings
        self.repodata_urls = {
            channel: f"{url}/{{platform}}/repodata.json"
            for channel, url in CONDA_CHANNELS.items()
        }
        self.session = None
        self._cache = {}
        self._cache_ttl = CACHE_TTL
        self._repodata_cache = {}
        self._dependency_cache = {}
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def package_exists(self, package_name: str) -> bool:
        """Check if package exists in conda channels"""
        package_name = normalize_package_name(package_name)
        # This is a simplified check - would need to check multiple channels
        try:
            import requests
            # Check conda-forge as it's the most comprehensive
            response = requests.get(
                f"https://api.anaconda.org/package/conda-forge/{package_name}",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    async def get_package_info_async(self, package_name: str) -> Dict:
        """Get package information from conda channels"""
        package_name = normalize_package_name(package_name)
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # Check cache
            cache_key = f"conda:{package_name}"
            if cache_key in self._cache:
                cached_data, timestamp = self._cache[cache_key]
                if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                    return cached_data
            
            # Search across channels
            package_info = None
            for channel_name, channel_url in self.channels.items():
                info = await self._fetch_from_anaconda_api(package_name, channel_name)
                if info:
                    package_info = info
                    package_info['channel_name'] = channel_name
                    break
            
            if not package_info:
                return None
            
            # Process the data with enhanced dependency extraction
            processed_info = await self._process_package_data_enhanced(package_info)
            
            # Cache the result
            self._cache[cache_key] = (processed_info, datetime.now())
            
            return processed_info
            
        except Exception as e:
            logger.error(f"Error fetching Conda package {package_name}: {e}")
            return None
    
    def get_package_info(self, package_name: str) -> Dict:
        """Synchronous wrapper"""
        package_name = normalize_package_name(package_name)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_package_info_async(package_name))
        finally:
            loop.close()
    
    async def _fetch_from_anaconda_api(self, package_name: str, channel: str) -> Optional[Dict]:
        """Fetch package data from Anaconda API"""
        package_name = normalize_package_name(package_name)
        try:
            api_url = f"https://api.anaconda.org/package/{channel}/{package_name}"
            
            async with self.session.get(api_url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                
                # Also fetch file information
                files_url = f"{api_url}/files"
                async with self.session.get(files_url) as files_response:
                    if files_response.status == 200:
                        files_data = await files_response.json()
                        data['files'] = files_data
                
                return data
                
        except Exception as e:
            logger.debug(f"Package {package_name} not found in {channel}: {e}")
            return None
    
    async def _process_package_data_enhanced(self, data: Dict) -> Dict:
        """Process Anaconda API data with enhanced dependency extraction"""
        latest_version = data.get('latest_version')
        channel_name = data.get('channel_name', 'conda-forge')
        
        # Process versions from files
        versions_info = []
        files = data.get('files', [])
        
        version_map = {}
        for file_info in files:
            version_str = file_info.get('version')
            parsed_version = parse_version(version_str)  # ADD THIS
            if parsed_version is None:  # ADD THIS CHECK
                logger.warning(f"Skipping invalid conda version: {version_str}")
                continue

            if version_str not in version_map:
                version_map[version_str] = {
                    'version': version_str,
                    'parsed_version': parsed_version,
                    'builds': [],
                    'platforms': set(),
                    'python_versions': set(),
                    'dependencies': None  # Will be fetched separately
                }
            
            # Extract platform
            attrs = file_info.get('attrs', {})
            platform = attrs.get('subdir', 'noarch')
            version_map[version]['platforms'].add(platform)
            
            # Extract Python version
            if 'py' in attrs.get('build', ''):
                py_match = re.search(r'py(\d)(\d+)', attrs.get('build', ''))
                if py_match:
                    py_version = f"{py_match.group(1)}.{py_match.group(2)}"
                    version_map[version]['python_versions'].add(py_version)
            
            version_map[version]['builds'].append({
                'build': attrs.get('build'),
                'build_number': attrs.get('build_number'),
                'size': file_info.get('size'),
                'upload_time': file_info.get('upload_time'),
                'md5': file_info.get('md5'),
                'sha256': file_info.get('sha256'),
                'filename': file_info.get('basename')
            })
        
        # Convert to list and fetch dependencies for latest version
        # sort by version
        for version_data in version_map.values():
            version_data['platforms'] = list(version_data['platforms'])
            version_data['python_versions'] = list(version_data['python_versions'])
            version_data.pop('parsed_version', None)  # Remove parsed version before returning
            versions_info.append(version_data)

        # Sort versions using parse_version
        versions_info.sort(
            key=lambda x: parse_version(x['version']) or parse_version('0.0.0'), 
            reverse=True
        )    
        
        # Extract dependencies for the latest version
        dependencies = await self._extract_dependencies_from_repodata(
            data.get('name'), 
            latest_version, 
            channel_name
        )
        
        # Extract system requirements
        system_requirements = self._extract_system_requirements(data, files)
        
        return {
            'name': data.get('name'),
            'version': latest_version,
            'versions': versions_info,
            'summary': data.get('summary'),
            'description': data.get('description'),
            'home': data.get('home'),
            'dev_url': data.get('dev_url'),
            'doc_url': data.get('doc_url'),
            'license': data.get('license'),
            'owner': data.get('owner', {}).get('login'),
            'channel': channel_name,
            'dependencies': dependencies,
            'system_requirements': system_requirements,
            'platforms': list(set(f['attrs'].get('subdir', 'noarch') for f in files))
        }
    
    async def _extract_dependencies_from_repodata(self, package_name: str, 
                                                 version: str, 
                                                 channel: str) -> Dict:
        """Extract dependencies from conda repodata"""
        package_name = normalize_package_name(package_name)
        cache_key = f"{channel}:{package_name}:{version}"
        
        # Check cache
        if cache_key in self._dependency_cache:
            cached_data, timestamp = self._dependency_cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return cached_data
        
        dependencies = {
            'required': {},
            'build': {},
            'run': {},
            'host': {},
            'test': {}
        }
        
        try:
            # Try multiple platforms to find the package
            platforms = ['noarch', 'linux-64', 'osx-64', 'win-64']
            
            for platform in platforms:
                repodata = await self._fetch_repodata(channel, platform)
                if not repodata:
                    continue
                
                # Look for the package in repodata
                packages = repodata.get('packages', {})
                
                for filename, pkg_info in packages.items():
                    if (pkg_info.get('name') == package_name and 
                        pkg_info.get('version') == version):
                        
                        # Extract dependencies from the 'depends' field
                        if 'depends' in pkg_info:
                            for dep in pkg_info['depends']:
                                dep_name, constraint = self._parse_conda_dependency(dep)
                                if dep_name:
                                    dep_name = normalize_package_name(dep_name)
                                    dependencies['run'][dep_name] = constraint
                        
                        # Some packages have 'requirements' field
                        if 'requirements' in pkg_info:
                            reqs = pkg_info['requirements']
                            if isinstance(reqs, dict):
                                for req_type, req_list in reqs.items():
                                    if req_type in dependencies and isinstance(req_list, list):
                                        for dep in req_list:
                                            dep_name, constraint = self._parse_conda_dependency(dep)
                                            if dep_name:
                                                dep_name = normalize_package_name(dep_name)
                                                dependencies[req_type][dep_name] = constraint
                        
                        # Cache and return
                        self._dependency_cache[cache_key] = (dependencies, datetime.now())
                        return dependencies
            
            # If not found in repodata, try to fetch from package file metadata
            return await self._extract_dependencies_from_package_metadata(
                package_name, version, channel
            )
            
        except Exception as e:
            logger.error(f"Error extracting dependencies for {package_name}: {e}")
            
        return dependencies
    
    async def _fetch_repodata(self, channel: str, platform: str) -> Optional[Dict]:
        """Fetch repodata for a channel and platform"""
        cache_key = f"{channel}:{platform}"
        
        # Check cache
        if cache_key in self._repodata_cache:
            cached_data, timestamp = self._repodata_cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return cached_data
        
        try:
            if channel in self.repodata_urls:
                url = self.repodata_urls[channel].format(platform=platform)
            else:
                # Construct URL for other channels
                base_url = self.channels.get(channel, f"https://conda.anaconda.org/{channel}")
                url = f"{base_url}/{platform}/repodata.json"
            
            logger.debug(f"Fetching repodata from: {url}")
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    # Cache the data
                    self._repodata_cache[cache_key] = (data, datetime.now())
                    return data
                    
        except Exception as e:
            logger.warning(f"Failed to fetch repodata from {channel}/{platform}: {e}")
        
        return None
    
    async def _extract_dependencies_from_package_metadata(self, package_name: str,
                                                        version: str,
                                                        channel: str) -> Dict:
        """Extract dependencies by downloading and parsing package metadata"""
        dependencies = {
            'required': {},
            'build': {},
            'run': {},
            'host': {},
            'test': {}
        }
        
        try:
            # Find package file URL
            info = await self._fetch_from_anaconda_api(package_name, channel)
            if not info or 'files' not in info:
                return dependencies
            
            # Find the right file for this version
            target_file = None
            for file_info in info['files']:
                if file_info.get('version') == version:
                    # Prefer noarch, then linux-64
                    if 'noarch' in file_info.get('basename', ''):
                        target_file = file_info
                        break
                    elif not target_file and 'linux-64' in file_info.get('basename', ''):
                        target_file = file_info
            
            if not target_file:
                return dependencies
            
            # Download and extract metadata
            download_url = target_file.get('download_url')
            if download_url:
                metadata = await self._download_and_extract_metadata(download_url)
                if metadata:
                    # Parse dependencies from metadata
                    if 'depends' in metadata:
                        for dep in metadata['depends']:
                            dep_name, constraint = self._parse_conda_dependency(dep)
                            if dep_name:
                                dep_name = normalize_package_name(dep_name)
                                dependencies['run'][dep_name] = constraint
                    
                    # Parse requirements
                    if 'requirements' in metadata:
                        reqs = metadata['requirements']
                        if isinstance(reqs, dict):
                            for req_type, req_list in reqs.items():
                                if req_type in dependencies and isinstance(req_list, list):
                                    for dep in req_list:
                                        dep_name, constraint = self._parse_conda_dependency(dep)
                                        if dep_name:
                                            dep_name = normalize_package_name(dep_name)
                                            dependencies[req_type][dep_name] = constraint
                        elif isinstance(reqs, list):
                            # Sometimes it's just a list
                            for dep in reqs:
                                dep_name, constraint = self._parse_conda_dependency(dep)
                                if dep_name:
                                    dep_name = normalize_package_name(dep_name)
                                    dependencies['run'][dep_name] = constraint
            
        except Exception as e:
            logger.error(f"Error extracting dependencies from package metadata: {e}")
        
        return dependencies
    
    async def _download_and_extract_metadata(self, url: str) -> Optional[Dict]:
        """Download conda package and extract metadata"""
        try:
            # Download only the first part of the package to get metadata
            # Conda packages are .tar.bz2 files with info/ directory containing metadata
            
            headers = {'Range': 'bytes=0-1048576'}  # Download first 1MB
            
            async with self.session.get(url, headers=headers) as response:
                if response.status in [200, 206]:  # 206 is partial content
                    content = await response.read()
                    
                    # Try to extract metadata from the tar file
                    import bz2
                    try:
                        # Decompress bz2
                        decompressed = bz2.decompress(content)
                        
                        # Read tar file
                        tar_buffer = io.BytesIO(decompressed)
                        with tarfile.open(fileobj=tar_buffer, mode='r') as tar:
                            # Look for info/index.json
                            try:
                                member = tar.getmember('info/index.json')
                                f = tar.extractfile(member)
                                if f:
                                    metadata = json.loads(f.read().decode('utf-8'))
                                    return metadata
                            except KeyError:
                                # Try info/recipe/meta.yaml
                                try:
                                    member = tar.getmember('info/recipe/meta.yaml')
                                    f = tar.extractfile(member)
                                    if f:
                                        metadata = yaml.safe_load(f.read().decode('utf-8'))
                                        return self._parse_recipe_metadata(metadata)
                                except KeyError:
                                    pass
                    except Exception as e:
                        logger.debug(f"Failed to extract metadata from package: {e}")
                        
        except Exception as e:
            logger.error(f"Error downloading package metadata: {e}")
        
        return None
    
    def _parse_recipe_metadata(self, recipe: Dict) -> Dict:
        """Parse conda recipe metadata format"""
        metadata = {}
        
        # Extract dependencies from recipe format
        requirements = recipe.get('requirements', {})
        depends = []
        
        if isinstance(requirements, dict):
            # Combine all requirement types
            for req_type in ['build', 'host', 'run']:
                if req_type in requirements:
                    req_list = requirements[req_type]
                    if isinstance(req_list, list):
                        depends.extend(req_list)
        elif isinstance(requirements, list):
            depends = requirements
        
        if depends:
            metadata['depends'] = depends
        
        # Extract other metadata
        about = recipe.get('about', {})
        metadata['name'] = recipe.get('package', {}).get('name', '')
        metadata['version'] = recipe.get('package', {}).get('version', '')
        metadata['home'] = about.get('home', '')
        metadata['license'] = about.get('license', '')
        metadata['summary'] = about.get('summary', '')
        
        return metadata
    
    def _parse_conda_dependency(self, dep_string: str) -> Tuple[str, str]:
        """Parse a conda dependency string into name and version constraint"""
        if not dep_string or not isinstance(dep_string, str):
            return None, ''
        
        # Clean up the string
        dep_string = dep_string.strip()
        
        # Handle different formats
        # Examples: "numpy >=1.19", "python 3.8.*", "cuda-toolkit =11.2", "package"
        
        # Pattern 1: package operator version (e.g., "numpy >=1.19")
        match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*([><=!]+)\s*(.+)$', dep_string)
        if match:
            return match.group(1), f"{match.group(2)}{match.group(3)}"
        
        # Pattern 2: package version (e.g., "python 3.8.*")
        match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s+([0-9].*)$', dep_string)
        if match:
            version_part = match.group(2)
            # Convert conda version patterns to standard
            if '*' in version_part:
                # "3.8.*" -> ">=3.8,<3.9"
                base_version = version_part.replace('.*', '')
                parsed_base = parse_version(base_version)  
                if parsed_base:
                    try:
                        next_major = f"{parsed_base.major}.{parsed_base.minor + 1}"
                        return match.group(1), f">={base_version},<{next_major}"
                    except:
                        return match.group(1), f"=={version_part}"
                else:
                    return match.group(1), f"=={version_part}"
            else:
                return match.group(1), f"=={version_part}"
        
        # Pattern 3: just package name
        match = re.match(r'^([a-zA-Z0-9_\-\.]+)$', dep_string)
        if match:
            return match.group(1), '*'
        
        # If no pattern matches, return the whole string as package name
        return dep_string, '*'
    
    def _extract_system_requirements(self, data: Dict, files: List[Dict]) -> Dict:
        """Extract system requirements"""
        requirements = {}
        
        # Check for CUDA requirements
        package_name = data.get('name', '').lower()
        description = (data.get('description', '') + ' ' + data.get('summary', '')).lower()
        
        # Enhanced CUDA detection
        cuda_indicators = [
            'cudatoolkit', 'cudnn', 'cuda-toolkit', 'pytorch-cuda',
            'tensorflow-gpu', 'jaxlib-cuda', 'cupy-cuda'
        ]
        
        cuda_detected = False
        cuda_versions = set()
        
        # Check package name
        for indicator in cuda_indicators:
            if indicator in package_name:
                cuda_detected = True
                # Extract version from package name
                cuda_match = re.search(r'cuda(\d+)', package_name)
                if cuda_match:
                    cuda_ver = cuda_match.group(1)
                    if len(cuda_ver) == 3:  # e.g., "116" -> "11.6"
                        cuda_versions.add(f"{cuda_ver[:2]}.{cuda_ver[2]}")
                    elif len(cuda_ver) == 2:  # e.g., "11" -> "11.x"
                        cuda_versions.add(f"{cuda_ver}.x")
                break
        
        # Check builds for CUDA information
        for file_info in files:
            build = file_info.get('attrs', {}).get('build', '')
            if 'cuda' in build:
                cuda_detected = True
                # Extract CUDA version from build string
                cuda_match = re.search(r'cuda(\d+)_', build)
                if not cuda_match:
                    cuda_match = re.search(r'cu(\d+)', build)
                
                if cuda_match:
                    cuda_ver = cuda_match.group(1)
                    if len(cuda_ver) == 3:  # e.g., "116" -> "11.6"
                        cuda_versions.add(f"{cuda_ver[:2]}.{cuda_ver[2]}")
                    elif len(cuda_ver) == 2:  # e.g., "11" -> "11.x"
                        cuda_versions.add(f"{cuda_ver}.x")
        
        if cuda_detected:
            requirements['gpu'] = {
                'required': True,
                'cuda': True,
                'description': 'NVIDIA GPU with CUDA support required'
            }
            
            if cuda_versions:
                # Sort and get the minimum required version
                sorted_versions = sorted(cuda_versions)
                requirements['gpu']['cuda_version'] = sorted_versions[0]
                requirements['gpu']['cuda_versions_supported'] = list(sorted_versions)
        
        # Check platform requirements
        platforms = list(set(f.get('attrs', {}).get('subdir', 'noarch') for f in files))
        if platforms and 'noarch' not in platforms:
            requirements['platform'] = {
                'supported': platforms
            }
        
        # Check Python requirements
        python_versions = set()
        for file_info in files:
            attrs = file_info.get('attrs', {})
            build = attrs.get('build', '')
            
            # Extract Python version from build string
            py_match = re.search(r'py(\d)(\d+)', build)
            if py_match:
                python_versions.add(f"{py_match.group(1)}.{py_match.group(2)}")
            
            # Also check dependencies in attrs
            depends = attrs.get('depends', [])
            if isinstance(depends, list):
                for dep in depends:
                    if dep.startswith('python '):
                        py_constraint = dep.replace('python ', '').strip()
                        # Extract version from constraint
                        version_match = re.search(r'(\d+\.\d+)', py_constraint)
                        if version_match:
                            python_versions.add(version_match.group(1))
        
        if python_versions:
            requirements['python'] = {
                'supported_versions': sorted(list(python_versions))
            }
        
        # Check for other system requirements
        if 'mkl' in package_name or any('mkl' in f.get('attrs', {}).get('build', '') for f in files):
            requirements['mkl'] = {
                'required': True,
                'description': 'Intel Math Kernel Library required'
            }
        
        if 'openmp' in description or 'libgomp' in description:
            requirements['openmp'] = {
                'required': True,
                'description': 'OpenMP support required'
            }
        
        return requirements
    
    async def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Search conda packages"""
        query = normalize_package_name(query)
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # Use Anaconda search API
            search_url = "https://api.anaconda.org/search"
            params = {
                'q': query,
                'type': 'conda',
                'limit': limit
            }
            
            async with self.session.get(search_url, params=params) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                
                results = []
                for item in data:
                    results.append({
                        'name': item.get('name'),
                        'channel': item.get('channel_name'),
                        'version': item.get('latest_version'),
                        'description': item.get('summary'),
                        'platforms': item.get('platforms', []),
                        'owner': item.get('owner', {}).get('login')
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error searching Conda: {e}")
            return []
    
    async def get_versions(self, package_name: str) -> List[Dict]:
        """Get all versions of a package"""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info_async(package_name)
        if not info:
            return []
        
        return info.get('versions', [])
    
    async def get_dependencies(self, package_name: str, version: Optional[str] = None) -> Dict:
        """Get dependencies for a package version"""
        package_name = normalize_package_name(package_name)
        # If no version specified, get latest
        if not version:
            info = await self.get_package_info_async(package_name)
            if not info:
                return {}
            version = info.get('version')
        
        # Try to get from cache first
        cache_key = f"deps:{package_name}:{version}"
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return cached_data
        
        # Find the channel for this package
        info = await self.get_package_info_async(package_name)
        if not info:
            return {}
        
        channel = info.get('channel', 'conda-forge')
        
        # Extract dependencies
        dependencies = await self._extract_dependencies_from_repodata(
            package_name, version, channel
        )
        
        # Cache the result
        self._cache[cache_key] = (dependencies, datetime.now())
        
        return dependencies