# pypi_client.py
from typing import Dict, List, Optional, Any, Set
from packaging.requirements import Requirement
from ..core.utils import normalize_package_name, parse_version, run_async
from datetime import datetime
import logging
import re
import asyncio
import xmlrpc.client
from bs4 import BeautifulSoup
from ..settings import CACHE_TTL
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class PyPIClient(BaseDataSourceClient):
    def __init__(self):
        super().__init__(
            ecosystem="pypi",
            base_url="https://pypi.org/pypi",
        )
        self.search_url = "https://pypi.org/search/"
        self.xmlrpc_url = "https://pypi.org/pypi"
        self._search_cache = {}
        self._search_cache_ttl = CACHE_TTL // 2

    async def package_exists(self, package_name: str) -> bool:
        """Check if package exists on PyPI"""
        package_name = normalize_package_name(package_name)
        try:
            session = self._get_session()
            response = await asyncio.wait_for(
                session.head(f"{self.base_url}/{package_name}/json"),
                timeout=5,
            )
            return response.status == 200
        except Exception:
            return False

    async def get_package_info_async(
        self, package_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get comprehensive package information from PyPI"""
        package_name = normalize_package_name(package_name)

        cache_key = f"pypi:{package_name}"
        data = await self.cached_get(cache_key, f"{self.base_url}/{package_name}/json")
        if data is None:
            return None

        try:
            info = await self._process_package_data_enhanced(data)
            return info
        except Exception as e:
            logger.error(f"Error processing PyPI package {package_name}: {e}")
            return None

    def get_package_info(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Synchronous wrapper for get_package_info_async"""
        package_name = normalize_package_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def _process_package_data_enhanced(
        self, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process raw PyPI data with enhanced extraction"""
        info = data.get("info", {})
        releases = data.get("releases", {})
        urls = data.get("urls", [])

        # Get latest stable version
        latest_version = info.get("version")
        if not latest_version and releases:
            # Find latest stable version
            stable_versions = []
            for v in releases.keys():
                parsed_v = parse_version(v)  # CHANGED from version.parse(v)
                if parsed_v and not parsed_v.is_prerelease:  # ADD null check
                    stable_versions.append(v)

            if stable_versions:
                # Sort using parse_version
                latest_version = max(
                    stable_versions,
                    key=lambda v: parse_version(v) or parse_version("0.0.0"),
                )

        # Process versions with more detail
        versions_info = []
        for ver, files in releases.items():
            ver_info = {
                "version": ver,
                "upload_time": None,
                "python_versions": set(),
                "size": 0,
                "has_binary_wheel": False,
                "has_source": False,
                "yanked": False,
                "requires_python": None,
                "platforms": set(),
            }

            for file_info in files:
                if file_info.get("upload_time"):
                    ver_info["upload_time"] = file_info["upload_time"]

                # Check if yanked
                if file_info.get("yanked", False):
                    ver_info["yanked"] = True

                if file_info.get("packagetype") == "bdist_wheel":
                    ver_info["has_binary_wheel"] = True

                    # Extract detailed Python version info from wheel filename
                    filename = file_info.get("filename", "")
                    python_versions = self._extract_python_versions_from_wheel(filename)
                    ver_info["python_versions"].update(python_versions)

                    # Extract platform info
                    platform = self._extract_platform_from_wheel(filename)
                    if platform:
                        ver_info["platforms"].add(platform)

                elif file_info.get("packagetype") == "sdist":
                    ver_info["has_source"] = True

                ver_info["size"] += file_info.get("size", 0)

                # Get requires_python if available
                if file_info.get("requires_python"):
                    ver_info["requires_python"] = file_info["requires_python"]

            # Convert sets to lists
            ver_info["python_versions"] = sorted(list(ver_info["python_versions"]))
            ver_info["platforms"] = sorted(list(ver_info["platforms"]))

            versions_info.append(ver_info)

        # Extract dependencies with enhanced parsing
        dependencies = await self._extract_dependencies_enhanced(
            info.get("requires_dist", []), info.get("requires_python")
        )

        # Extract system requirements with more detail
        system_requirements = self._extract_system_requirements_enhanced(info, urls)

        # Extract development status
        dev_status = self._extract_development_status(info.get("classifiers", []))

        return {
            "name": info.get("name"),
            "version": latest_version,
            "versions": versions_info,
            "description": info.get("summary"),
            "long_description": info.get("description"),
            "homepage": info.get("home_page"),
            "repository": self._extract_repository_url(info),
            "documentation": self._extract_documentation_url(info),
            "author": info.get("author"),
            "author_email": info.get("author_email"),
            "maintainer": info.get("maintainer"),
            "maintainer_email": info.get("maintainer_email"),
            "license": info.get("license"),
            "keywords": self._parse_keywords(info.get("keywords", "")),
            "classifiers": info.get("classifiers", []),
            "dependencies": dependencies,
            "system_requirements": system_requirements,
            "python_requires": info.get("requires_python"),
            "downloads": self._extract_download_stats(info),
            "development_status": dev_status,
            "project_urls": info.get("project_urls", {}),
        }

    def _extract_python_versions_from_wheel(self, filename: str) -> Set[str]:
        """Extract Python versions from wheel filename"""
        python_versions = set()

        # Pattern: package-version-pyX.Y-none-any.whl or package-version-pyX-none-any.whl
        # Or: package-version-pyXY-none-any.whl
        patterns = [
            r"-py(\d)\.(\d+)-",  # py3.9
            r"-py(\d)(\d+)-",  # py39
            r"-py(\d)-",  # py3
            r"-cp(\d)(\d+)-",  # cp39 (CPython)
            r"-pp(\d)(\d+)-",  # pp39 (PyPy)
        ]

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                if len(match.groups()) == 2:
                    python_versions.add(f"{match.group(1)}.{match.group(2)}")
                else:
                    python_versions.add(f"{match.group(1)}.x")

        # Check for py2.py3
        if "-py2.py3-" in filename:
            python_versions.update(["2.7", "3.x"])

        return python_versions

    def _extract_platform_from_wheel(self, filename: str) -> Optional[str]:
        """Extract platform from wheel filename"""
        # Common platform tags
        platform_mapping = {
            "win_amd64": "Windows x64",
            "win32": "Windows x86",
            "macosx": "macOS",
            "manylinux": "Linux",
            "linux_x86_64": "Linux x64",
            "any": "Any",
        }

        for tag, platform in platform_mapping.items():
            if tag in filename:
                return platform

        return None

    async def _extract_dependencies_enhanced(
        self, requires_dist: List[str], python_requires: Optional[str]
    ) -> Dict[str, Any]:
        """Extract and categorize dependencies with enhanced parsing"""
        deps = {
            "required": {},
            "optional": {},
            "dev": {},
            "test": {},
            "docs": {},
            "extras": {},
        }

        for req_str in requires_dist:
            if not req_str:
                continue

            try:
                # Parse requirement using packaging library
                req = Requirement(req_str)

                # Extract package name and version spec
                pkg_name = req.name
                version_spec = str(req.specifier) if req.specifier else "*"

                # Categorize based on markers and extras
                category = "required"

                if req.marker:
                    marker_str = str(req.marker)

                    # Parse extra dependencies
                    if "extra" in marker_str:
                        extra_match = re.search(
                            r'extra\s*==\s*["\']([^"\']+)["\']', marker_str
                        )
                        if extra_match:
                            extra_name = extra_match.group(1)

                            # Common extra categories
                            if extra_name in ["dev", "develop", "development"]:
                                category = "dev"
                            elif extra_name in ["test", "tests", "testing"]:
                                category = "test"
                            elif extra_name in ["doc", "docs", "documentation"]:
                                category = "docs"
                            else:
                                # Store in extras with the extra name
                                if extra_name not in deps["extras"]:
                                    deps["extras"][extra_name] = {}
                                deps["extras"][extra_name][pkg_name] = version_spec
                                continue

                    # Check for platform-specific dependencies
                    elif any(
                        platform in marker_str
                        for platform in ["win32", "linux", "darwin"]
                    ):
                        category = "optional"

                    # Check for Python version-specific dependencies
                    elif "python_version" in marker_str:
                        # Still required but with conditions
                        if (
                            python_requires
                            and self._is_compatible_with_python_requires(
                                marker_str, python_requires
                            )
                        ):
                            category = "required"
                        else:
                            category = "optional"

                # Add to appropriate category
                deps[category][pkg_name] = {
                    "version_spec": version_spec,
                    "marker": str(req.marker) if req.marker else None,
                }

            except Exception as e:
                logger.warning(f"Failed to parse requirement '{req_str}': {e}")
                # Fallback to simple parsing
                parts = req_str.split(";")
                pkg_part = parts[0].strip()

                if " " in pkg_part:
                    pkg_name = pkg_part.split()[0]
                    version_spec = " ".join(pkg_part.split()[1:])
                else:
                    pkg_name = pkg_part
                    version_spec = "*"

                deps["required"][pkg_name] = {
                    "version_spec": version_spec,
                    "marker": None,
                }

        # Clean up the structure for backward compatibility
        cleaned_deps = {}
        for category, packages in deps.items():
            if packages:  # Only include non-empty categories
                if category == "extras":
                    cleaned_deps[category] = packages
                else:
                    # Simplify structure for non-extras
                    cleaned_deps[category] = {
                        pkg: info["version_spec"] if isinstance(info, dict) else info
                        for pkg, info in packages.items()
                    }

        return cleaned_deps

    def _is_compatible_with_python_requires(
        self, marker_str: str, python_requires: str
    ) -> bool:
        """Check if a marker is compatible with python_requires"""
        try:
            # This is a simplified check
            # In reality, you'd want to parse both the marker and python_requires
            # and check for intersection
            return True
        except Exception:
            return True

    def _extract_system_requirements_enhanced(
        self, info: Dict[str, Any], urls: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract system requirements with enhanced detection"""
        requirements = {}

        classifiers = info.get("classifiers", [])
        description = (
            info.get("description", "") + " " + info.get("summary", "")
        ).lower()

        # Check for GPU/CUDA requirements
        cuda_info = self._extract_cuda_requirements(
            classifiers, description, info.get("name", "")
        )
        if cuda_info:
            requirements["gpu"] = cuda_info

        # Check Python version requirements
        python_requires = info.get("requires_python")
        if python_requires:
            requirements["python"] = {
                "version_spec": python_requires,
                "min_version": self._extract_min_python_version(python_requires),
            }

        # Check for OS-specific requirements
        os_info = self._extract_os_requirements(classifiers, urls)
        if os_info:
            requirements["os"] = os_info

        # Check for architecture requirements
        arch_info = self._extract_architecture_requirements(classifiers, urls)
        if arch_info:
            requirements["architecture"] = arch_info

        # Check for other system libraries
        system_libs = self._extract_system_library_requirements(
            description, classifiers
        )
        if system_libs:
            requirements["system_libraries"] = system_libs

        # Check for compiler requirements
        compiler_info = self._extract_compiler_requirements(description, classifiers)
        if compiler_info:
            requirements["compiler"] = compiler_info

        return requirements

    def _extract_cuda_requirements(
        self, classifiers: List[str], description: str, package_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract CUDA/GPU requirements"""
        cuda_versions = set()
        cudnn_versions = set()

        # Check classifiers
        for classifier in classifiers:
            if "CUDA" in classifier:
                cuda_match = re.search(r"CUDA :: (\d+\.?\d*)", classifier)
                if cuda_match:
                    cuda_versions.add(cuda_match.group(1))

        # Check package name and description
        cuda_indicators = [
            "cuda",
            "gpu",
            "nvidia",
            "tensorflow-gpu",
            "torch-gpu",
            "jax-cuda",
            "cupy-cuda",
        ]

        package_requires_cuda = any(
            indicator in package_name.lower() for indicator in cuda_indicators
        )
        desc_mentions_cuda = any(
            indicator in description for indicator in cuda_indicators
        )

        if cuda_versions or package_requires_cuda or desc_mentions_cuda:
            # Extract CUDA versions from description
            cuda_pattern = r"cuda\s*(\d+\.?\d*)"
            desc_cuda_matches = re.findall(cuda_pattern, description, re.I)
            cuda_versions.update(desc_cuda_matches)

            # Extract cuDNN versions
            cudnn_pattern = r"cudnn\s*(\d+\.?\d*)"
            cudnn_matches = re.findall(cudnn_pattern, description, re.I)
            cudnn_versions.update(cudnn_matches)

            return {
                "required": True,
                "cuda_versions": sorted(list(cuda_versions)),
                "cudnn_versions": sorted(list(cudnn_versions)),
                "description": "NVIDIA GPU with CUDA support required",
            }

        return None

    def _extract_os_requirements(
        self, classifiers: List[str], urls: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract OS requirements from classifiers and wheel files"""
        supported_os = set()

        # From classifiers
        os_mapping = {
            "Operating System :: POSIX": ["Linux", "macOS", "Unix"],
            "Operating System :: POSIX :: Linux": ["Linux"],
            "Operating System :: MacOS": ["macOS"],
            "Operating System :: Microsoft :: Windows": ["Windows"],
            "Operating System :: Unix": ["Unix"],
            "Operating System :: OS Independent": ["Any"],
        }

        for classifier in classifiers:
            for pattern, os_list in os_mapping.items():
                if classifier.startswith(pattern):
                    supported_os.update(os_list)

        # From wheel filenames
        for url_info in urls:
            filename = url_info.get("filename", "")
            if filename.endswith(".whl"):
                if "win" in filename:
                    supported_os.add("Windows")
                elif "macosx" in filename:
                    supported_os.add("macOS")
                elif "linux" in filename or "manylinux" in filename:
                    supported_os.add("Linux")

        if supported_os and "Any" not in supported_os:
            return {"supported": sorted(list(supported_os))}

        return {}

    def _extract_architecture_requirements(
        self, classifiers: List[str], urls: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract architecture requirements"""
        architectures = set()

        # From wheel filenames
        for url_info in urls:
            filename = url_info.get("filename", "")
            if filename.endswith(".whl"):
                if "amd64" in filename or "x86_64" in filename:
                    architectures.add("x86_64")
                elif "i686" in filename or "win32" in filename:
                    architectures.add("x86")
                elif "aarch64" in filename or "arm64" in filename:
                    architectures.add("ARM64")
                elif "armv7" in filename:
                    architectures.add("ARMv7")

        if architectures:
            return {"supported": sorted(list(architectures))}

        return {}

    def _extract_system_library_requirements(
        self, description: str, classifiers: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract system library requirements"""
        libraries = []

        # Common system libraries and their patterns
        lib_patterns = {
            "openssl": r"(openssl|libssl)",
            "blas": r"(blas|openblas|mkl)",
            "lapack": r"lapack",
            "fftw": r"fftw",
            "hdf5": r"hdf5",
            "netcdf": r"netcdf",
            "gdal": r"gdal",
            "geos": r"geos",
            "proj": r"proj",
            "boost": r"boost",
            "qt": r"(qt5|qt4|pyqt)",
            "gtk": r"gtk",
            "x11": r"x11",
            "opengl": r"opengl",
            "opencl": r"opencl",
        }

        for lib_name, pattern in lib_patterns.items():
            if re.search(pattern, description, re.I):
                libraries.append({"name": lib_name, "required": True})

        return libraries

    def _extract_compiler_requirements(
        self, description: str, classifiers: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Extract compiler requirements"""
        compilers = {}

        # Check for C/C++ extensions
        if any("Programming Language :: C" in c for c in classifiers):
            compilers["c"] = True
        if any("Programming Language :: C++" in c for c in classifiers):
            compilers["cpp"] = True

        # Check for specific compiler versions in description
        gcc_match = re.search(r"gcc\s*([><=]+)?\s*(\d+\.?\d*)", description, re.I)
        if gcc_match:
            compilers["gcc"] = {
                "version": gcc_match.group(2),
                "operator": gcc_match.group(1) or ">=",
            }

        if compilers:
            return compilers

        return None

    def _extract_min_python_version(self, python_requires: str) -> Optional[str]:
        """Extract minimum Python version from version spec"""
        if not python_requires:
            return None

        # Parse common patterns
        patterns = [
            r">=\s*(\d+\.?\d*)",
            r">\s*(\d+\.?\d*)",
            r"==\s*(\d+\.?\d*)",
            r"~=\s*(\d+\.?\d*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, python_requires)
            if match:
                return match.group(1)

        return None

    def _extract_repository_url(self, info: Dict[str, Any]) -> Optional[str]:
        """Extract repository URL from project URLs"""
        project_urls = info.get("project_urls", {})

        # Common repository URL keys
        repo_keys = ["Source", "Repository", "Code", "GitHub", "GitLab", "Bitbucket"]

        for key in repo_keys:
            if key in project_urls:
                return project_urls[key]

        # Check home page if it's a repository
        home_page = info.get("home_page", "")
        if any(
            host in home_page for host in ["github.com", "gitlab.com", "bitbucket.org"]
        ):
            return home_page

        return None

    def _extract_documentation_url(self, info: Dict[str, Any]) -> Optional[str]:
        """Extract documentation URL from project URLs"""
        project_urls = info.get("project_urls", {})

        # Common documentation URL keys
        doc_keys = ["Documentation", "Docs", "Doc", "Manual", "Guide"]

        for key in doc_keys:
            if key in project_urls:
                return project_urls[key]

        return None

    def _parse_keywords(self, keywords_str: str) -> List[str]:
        """Parse keywords string into list"""
        if not keywords_str:
            return []

        # Handle both comma and space separated keywords
        if "," in keywords_str:
            keywords = [k.strip() for k in keywords_str.split(",")]
        else:
            keywords = keywords_str.split()

        # Filter out empty strings
        return [k for k in keywords if k]

    def _extract_development_status(self, classifiers: List[str]) -> Optional[str]:
        """Extract development status from classifiers"""
        for classifier in classifiers:
            if classifier.startswith("Development Status ::"):
                return classifier.split("::")[1].strip()
        return None

    def _extract_download_stats(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract download statistics"""
        downloads = info.get("downloads", {})

        return {
            "last_day": downloads.get("last_day", 0),
            "last_week": downloads.get("last_week", 0),
            "last_month": downloads.get("last_month", 0),
        }

    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search for packages on PyPI using multiple methods"""
        cache_key = f"search:{query}:{limit}"
        if cache_key in self._search_cache:
            cached_data, timestamp = self._search_cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._search_cache_ttl:
                return cached_data

        try:
            # Method 1: Try the XML-RPC API (deprecated but still works)
            results = await self._search_xmlrpc(query, limit)

            if not results:
                # Method 2: Web scraping fallback
                results = await self._search_web_scraping(query, limit)

            if not results:
                # Method 3: Try exact and fuzzy matches
                results = await self._search_fallback(query, limit)

            # Cache results
            self._search_cache[cache_key] = (results, datetime.now())

            return results

        except Exception as e:
            logger.error(f"Error searching PyPI: {e}")
            return []

    async def _search_xmlrpc(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search using PyPI XML-RPC API"""
        try:
            # Use asyncio to run the XML-RPC call in a thread
            loop = asyncio.get_event_loop()

            def xmlrpc_search():
                client = xmlrpc.client.ServerProxy(self.xmlrpc_url)
                # Search with OR operator for better results
                search_results = client.search({"name": query, "summary": query}, "or")
                return search_results[:limit]

            results = await loop.run_in_executor(None, xmlrpc_search)

            # Process results
            processed_results = []
            for result in results:
                processed_results.append(
                    {
                        "name": result.get("name"),
                        "version": result.get("version"),
                        "description": result.get("summary"),
                        "score": result.get("_pypi_ordering", 0),
                    }
                )

            # Sort by relevance score
            processed_results.sort(key=lambda x: x["score"], reverse=True)

            return processed_results

        except Exception as e:
            logger.debug(f"XML-RPC search failed: {e}")
            return []

    async def _search_web_scraping(
        self, query: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Search by scraping PyPI search page"""
        try:
            search_url = f"https://pypi.org/search/"
            params = {
                "q": query,
                "o": "",  # Relevance ordering
            }

            async with self._get_session().get(search_url, params=params) as response:
                if response.status != 200:
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                results = []

                # Find search results
                packages = soup.find_all("a", class_="package-snippet")

                for package in packages[:limit]:
                    name_elem = package.find("span", class_="package-snippet__name")
                    version_elem = package.find(
                        "span", class_="package-snippet__version"
                    )
                    desc_elem = package.find("p", class_="package-snippet__description")

                    if name_elem:
                        results.append(
                            {
                                "name": name_elem.text.strip(),
                                "version": version_elem.text.strip()
                                if version_elem
                                else "",
                                "description": desc_elem.text.strip()
                                if desc_elem
                                else "",
                                "url": f"https://pypi.org{package.get('href', '')}",
                            }
                        )

                return results

        except Exception as e:
            logger.debug(f"Web scraping search failed: {e}")
            return []

    async def _search_fallback(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback search using exact and fuzzy matching"""
        results = []

        try:
            # Normalize the original query
            normalized_query = normalize_package_name(query)

            # Try exact match
            exact_match = await self.get_package_info_async(query)
            if exact_match:
                results.append(
                    {
                        "name": exact_match["name"],
                        "version": exact_match["version"],
                        "description": exact_match["description"],
                    }
                )

            # Try common variations
            variations = [
                query.lower(),
                query.upper(),
                query.replace("-", "_"),
                query.replace("_", "-"),
                f"python-{query}",
                f"py{query}",
                f"{query}py",
            ]

            for variation in variations:
                if len(results) >= limit:
                    break

                # Normalize each variation before checking
                normalized_variation = normalize_package_name(variation)
                if normalized_variation != normalized_query:
                    match = await self.get_package_info_async(normalized_variation)
                    if match and not any(r["name"] == match["name"] for r in results):
                        results.append(
                            {
                                "name": match["name"],
                                "version": match["version"],
                                "description": match["description"],
                            }
                        )

        except Exception as e:
            logger.debug(f"Fallback search failed: {e}")

        return results[:limit]

    async def get_versions(self, package_name: str) -> List[Dict[str, Any]]:
        """Get all available versions of a package"""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info_async(package_name)
        if not info:
            return []

        versions = []
        for ver_info in info.get("versions", []):
            versions.append(
                {
                    "version": ver_info["version"],
                    "upload_time": ver_info.get("upload_time"),
                    "python_requires": ver_info.get("requires_python"),
                    "python_versions": ver_info.get("python_versions", []),
                    "has_binary": ver_info.get("has_binary_wheel", False),
                    "has_source": ver_info.get("has_source", False),
                    "yanked": ver_info.get("yanked", False),
                    "platforms": ver_info.get("platforms", []),
                }
            )

        # Sort by version number (newest first)
        versions.sort(
            key=lambda x: parse_version(x["version"]) or parse_version("0.0.0"),
            reverse=True,
        )

        return versions

    async def get_dependencies(
        self, package_name: str, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get dependencies for a specific package version"""
        package_name = normalize_package_name(package_name)

        url = (
            f"{self.base_url}/{package_name}/{version}/json"
            if version
            else f"{self.base_url}/{package_name}/json"
        )
        data = await self._get(url)
        if data is None:
            return {}

        info = data.get("info", {})
        return await self._extract_dependencies_enhanced(
            info.get("requires_dist", []), info.get("requires_python")
        )
