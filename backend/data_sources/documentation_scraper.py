# documentation_scraper.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup
import re
from ..settings import (
    CACHE_TTL,
    LOG_LEVEL,
    KNOWN_DOC_URLS,
    DOC_SCRAPER_TIMEOUT,
    USER_AGENTS,
    DOC_SCRAPER_MAX_PAGES,
    DOC_SCRAPER_FOLLOW_REDIRECTS,
)
import logging
from urllib.parse import urljoin, urlparse, quote
from datetime import datetime
import hashlib
from ..core.utils import normalize_package_name, parse_version, compare_versions

logger = logging.getLogger(__name__)


class DocumentationScraper:
    def __init__(self):
        self.session = None
        self.scraped_urls = set()
        self.known_docs = KNOWN_DOC_URLS.copy()  # Use all URLs from settings
        self.compatibility_cache = {}
        self.cache_ttl = CACHE_TTL
        self.timeout = DOC_SCRAPER_TIMEOUT
        self.max_pages = DOC_SCRAPER_MAX_PAGES
        self.follow_redirects = DOC_SCRAPER_FOLLOW_REDIRECTS
        self.user_agent = USER_AGENTS.get("documentation", USER_AGENTS["default"])

        # Documentation search patterns
        self.doc_patterns = {
            "github": r"github\.com/[\w-]+/[\w-]+",
            "readthedocs": r"[\w-]+\.readthedocs\.io",
            "official": r"([\w-]+)\.(org|io|com|ai|dev)/docs",
        }

        # Version extraction patterns
        self.version_patterns = {
            "cuda": r"CUDA\s*(?:Toolkit\s*)?(\d+\.?\d*(?:\.\d+)?)",
            "cudnn": r"cuDNN\s*v?(\d+\.?\d*(?:\.\d+)?)",
            "python": r"Python\s*(\d+\.?\d*(?:\.\d+)?)",
            "gcc": r"GCC\s*(\d+\.?\d*(?:\.\d+)?)",
            "cmake": r"CMake\s*(\d+\.?\d*(?:\.\d+)?)",
            "numpy": r"NumPy\s*(?:>=?|==?)?\s*(\d+\.?\d*(?:\.\d+)?)",
            "tensorflow": r"TensorFlow\s*(\d+\.?\d*(?:\.\d+)?)",
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (compatible; DocScraper/1.0)"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def scrape_installation_requirements(self, package_name: str) -> Dict:
        """Scrape installation requirements from official documentation"""
        package_name = normalize_package_name(package_name)
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 (compatible; DocScraper/1.0)"}
            )

        try:
            # Check cache first
            cache_key = f"requirements:{package_name}"
            if cache_key in self.compatibility_cache:
                cached_data, timestamp = self.compatibility_cache[cache_key]
                if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                    return cached_data

            # Check if we have a known documentation URL
            doc_url = self.known_docs.get(package_name.lower())
            if not doc_url:
                # Try to find documentation URL
                doc_url = await self._find_documentation_url(package_name)

            if not doc_url:
                return {}

            # Scrape the documentation
            requirements = await self._scrape_requirements_from_url(
                doc_url, package_name
            )

            # Cache the results
            self.compatibility_cache[cache_key] = (requirements, datetime.now())

            return requirements

        except Exception as e:
            logger.error(f"Error scraping documentation for {package_name}: {e}")
            return {}

    async def _find_documentation_url(self, package_name: str) -> Optional[str]:
        """Try to find official documentation URL using multiple strategies"""
        package_name = normalize_package_name(package_name)

        # Strategy 1: Check PyPI for project URLs
        pypi_url = await self._get_pypi_documentation_url(package_name)
        if pypi_url:
            return pypi_url

        # Strategy 2: Check GitHub for README or docs
        github_url = await self._get_github_documentation_url(package_name)
        if github_url:
            return github_url

        # Strategy 3: Try common documentation patterns
        common_patterns = [
            f"https://{package_name}.readthedocs.io/en/latest/",
            f"https://{package_name}.github.io/",
            f"https://docs.{package_name}.org/",
            f"https://{package_name}.org/docs/",
            f"https://www.{package_name}.org/documentation/",
        ]

        for pattern in common_patterns:
            if await self._check_url_exists(pattern):
                return pattern

        # Strategy 4: Search using DuckDuckGo HTML API (no API key needed)
        search_url = await self._search_documentation_url(package_name)
        if search_url:
            return search_url

        return None

    async def _get_pypi_documentation_url(self, package_name: str) -> Optional[str]:
        """Get documentation URL from PyPI"""
        package_name = normalize_package_name(package_name)
        try:
            pypi_api_url = f"https://pypi.org/pypi/{package_name}/json"

            async with self.session.get(pypi_api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    info = data.get("info", {})

                    # Check various URL fields
                    for field in [
                        "docs_url",
                        "documentation_url",
                        "home_page",
                        "project_url",
                    ]:
                        url = info.get(field)
                        if url and ("doc" in url.lower() or "guide" in url.lower()):
                            return url

                    # Check project URLs
                    project_urls = info.get("project_urls", {})
                    for key, url in project_urls.items():
                        if any(
                            term in key.lower() for term in ["doc", "guide", "manual"]
                        ):
                            return url

                    # Fallback to homepage if it looks like docs
                    home_page = info.get("home_page")
                    if home_page and await self._check_url_exists(home_page):
                        return home_page

        except Exception as e:
            logger.debug(f"Failed to get PyPI info for {package_name}: {e}")

        return None

    async def _get_github_documentation_url(self, package_name: str) -> Optional[str]:
        """Try to find GitHub repository and documentation"""
        package_name = normalize_package_name(package_name)
        try:
            # Search GitHub for the package
            search_url = f"https://api.github.com/search/repositories?q={package_name}+in:name&sort=stars&order=desc"

            async with self.session.get(search_url) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("items", [])

                    if items:
                        # Get the most starred repository
                        repo = items[0]
                        repo_url = repo.get("html_url")

                        # Check for docs folder or wiki
                        if repo_url:
                            # Try common documentation locations
                            doc_locations = [
                                f"{repo_url}/wiki",
                                f"{repo_url}/tree/main/docs",
                                f"{repo_url}/tree/master/docs",
                                f"{repo_url}/tree/main/doc",
                                f"{repo_url}/tree/master/doc",
                                f"{repo_url}#installation",
                                f"{repo_url}#getting-started",
                            ]

                            for loc in doc_locations:
                                if await self._check_url_exists(loc):
                                    return loc

                            # Return main repo page as fallback
                            return repo_url

        except Exception as e:
            logger.debug(f"Failed to search GitHub for {package_name}: {e}")

        return None

    async def _search_documentation_url(self, package_name: str) -> Optional[str]:
        """Search for documentation using DuckDuckGo HTML"""
        package_name = normalize_package_name(package_name)
        try:
            # Use DuckDuckGo HTML search (no API key required)
            search_query = quote(f"{package_name} installation documentation guide")
            search_url = f"https://html.duckduckgo.com/html/?q={search_query}"

            async with self.session.get(search_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")

                    # Look for result links
                    results = soup.find_all("a", class_="result__a")

                    for result in results[:5]:  # Check first 5 results
                        url = result.get("href")
                        if url:
                            # Look for documentation indicators
                            if any(
                                indicator in url.lower()
                                for indicator in [
                                    "docs",
                                    "documentation",
                                    "install",
                                    "guide",
                                    "getting-started",
                                ]
                            ):
                                return url

        except Exception as e:
            logger.debug(f"Search failed for {package_name}: {e}")

        return None

    async def _check_url_exists(self, url: str) -> bool:
        """Check if a URL exists and is accessible"""
        try:
            async with self.session.head(
                url, allow_redirects=True, timeout=5
            ) as response:
                return response.status == 200
        except Exception:
            return False

    async def _scrape_requirements_from_url(self, url: str, package_name: str) -> Dict:
        """Scrape requirements from a documentation page"""
        try:
            async with self.session.get(url, timeout=30) as response:
                if response.status != 200:
                    return {}

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                requirements = {
                    "cuda_versions": [],
                    "python_versions": [],
                    "os_requirements": [],
                    "dependencies": [],
                    "hardware_requirements": {},
                    "notes": [],
                }

                # Package-specific scrapers
                if "tensorflow" in package_name.lower():
                    requirements.update(self._scrape_tensorflow_requirements(soup))
                elif "pytorch" in package_name.lower():
                    requirements.update(self._scrape_pytorch_requirements(soup))
                elif "tensorrt" in package_name.lower():
                    requirements.update(self._scrape_tensorrt_requirements(soup))
                else:
                    # Generic scraper
                    requirements.update(self._scrape_generic_requirements(soup))

                # Also extract from tables
                requirements.update(await self._extract_requirements_from_tables(soup))

                # Clean up duplicates
                for key in ["cuda_versions", "python_versions", "cudnn_versions"]:
                    if key in requirements and isinstance(requirements[key], list):
                        requirements[key] = sorted(list(set(requirements[key])))

                return requirements

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return {}

    def _scrape_tensorflow_requirements(self, soup: BeautifulSoup) -> Dict:
        """Scrape TensorFlow-specific requirements"""
        requirements = {
            "cuda_versions": [],
            "cudnn_versions": [],
            "python_versions": [],
        }

        # Look for version compatibility tables
        tables = soup.find_all("table")
        for table in tables:
            headers = [th.text.strip() for th in table.find_all("th")]

            if any(
                term in str(headers).lower() for term in ["cuda", "cudnn", "version"]
            ):
                rows = table.find_all("tr")[1:]  # Skip header row
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        # Extract versions from cells
                        for cell in cells:
                            text = cell.text.strip()

                            # Extract CUDA versions
                            cuda_matches = re.findall(
                                self.version_patterns["cuda"], text
                            )
                            requirements["cuda_versions"].extend(cuda_matches)

                            # Extract cuDNN versions
                            cudnn_matches = re.findall(
                                self.version_patterns["cudnn"], text
                            )
                            requirements["cudnn_versions"].extend(cudnn_matches)

                            # Extract Python versions
                            python_matches = re.findall(
                                self.version_patterns["python"], text
                            )
                            requirements["python_versions"].extend(python_matches)

        # Look for specific version requirements in text
        version_sections = soup.find_all(
            ["div", "section", "p"],
            text=re.compile(r"(requirements|compatibility|version)", re.I),
        )

        for section in version_sections:
            text = section.get_text()

            # Extract all version mentions
            for key, pattern in self.version_patterns.items():
                matches = re.findall(pattern, text)
                if matches and key in requirements:
                    requirements[key].extend(matches)

        # Clean up and validate versions - ENHANCED
        for key in ["cuda_versions", "cudnn_versions", "python_versions"]:
            if requirements[key]:
                valid_versions = []
                for v in requirements[key]:
                    parsed = parse_version(v)
                    if parsed:
                        valid_versions.append(v)
                    else:
                        logger.debug(f"Invalid {key} version found: {v}")

                # Sort versions properly
                requirements[key] = sorted(
                    list(set(valid_versions)),
                    key=lambda x: parse_version(x) or parse_version("0.0.0"),
                )

        return requirements

    def _scrape_pytorch_requirements(self, soup: BeautifulSoup) -> Dict:
        """Scrape PyTorch-specific requirements"""
        requirements = {
            "cuda_versions": [],
            "python_versions": [],
            "os_support": [],
            "rocm_versions": [],
        }

        # PyTorch has a selector interface - look for it
        selectors = soup.find_all(
            ["select", "div"], class_=re.compile(r"(selector|option)")
        )

        for selector in selectors:
            # Look for CUDA options
            if "cuda" in str(selector).lower():
                options = selector.find_all(["option", "button", "a"])
                for option in options:
                    text = option.text.strip()
                    cuda_match = re.search(r"(\d+\.?\d*)", text)
                    if cuda_match:
                        requirements["cuda_versions"].append(cuda_match.group(1))

            # Look for OS options
            if "os" in str(selector).lower() or "system" in str(selector).lower():
                options = selector.find_all(["option", "button", "a"])
                for option in options:
                    os_name = option.text.strip()
                    if os_name and len(os_name) < 20:  # Avoid long text
                        requirements["os_support"].append(os_name)

        # Look for installation commands which often contain version info
        code_blocks = soup.find_all(["code", "pre"])
        for block in code_blocks:
            text = block.text

            # Extract CUDA versions from pip install commands
            if "pip install" in text or "conda install" in text:
                cuda_matches = re.findall(r"cu(\d{2,3})", text)
                for match in cuda_matches:
                    if len(match) == 3:
                        version = f"{match[:2]}.{match[2]}"
                    else:
                        version = match
                    requirements["cuda_versions"].append(version)

                # Extract ROCm versions
                rocm_matches = re.findall(r"rocm(\d+\.?\d*)", text)
                requirements["rocm_versions"].extend(rocm_matches)

                # Extract Python versions from commands
                python_matches = re.findall(r"python(\d+\.?\d*)", text)
                requirements["python_versions"].extend(python_matches)

        # Clean up and validate versions
        for key in ["cuda_versions", "rocm_versions", "python_versions"]:
            if requirements[key]:
                valid_versions = []
                for v in requirements[key]:
                    parsed = parse_version(v)
                    if parsed:
                        valid_versions.append(v)
                    else:
                        logger.debug(f"Invalid {key} version found: {v}")

                requirements[key] = sorted(
                    list(set(valid_versions)),
                    key=lambda x: parse_version(x) or parse_version("0.0.0"),
                    reverse=True,
                )

        # Clean OS support list
        requirements["os_support"] = list(set(requirements["os_support"]))

        return requirements

    def _scrape_tensorrt_requirements(self, soup: BeautifulSoup) -> Dict:
        """Scrape TensorRT-specific requirements"""
        requirements = {
            "cuda_versions": [],
            "cudnn_versions": [],
            "os_requirements": [],
            "gcc_versions": [],
            "tensorrt_versions": [],
        }

        # Look for system requirements section
        req_sections = soup.find_all(
            ["h1", "h2", "h3"],
            text=re.compile(r"(system requirements|prerequisites)", re.I),
        )

        for section in req_sections:
            # Get the content after the heading
            current = section
            for _ in range(20):  # Check next 20 elements
                current = current.find_next_sibling()
                if not current:
                    break

                # Stop if we hit another major heading
                if current.name in ["h1", "h2", "h3"]:
                    break

                text = current.get_text()

                # Extract versions using patterns
                for key, pattern in self.version_patterns.items():
                    if key in requirements:
                        matches = re.findall(pattern, text, re.I)
                        requirements[key].extend(matches)

                # Extract OS requirements
                os_patterns = [
                    r"Ubuntu\s*(\d+\.?\d*)",
                    r"CentOS\s*(\d+\.?\d*)",
                    r"RHEL\s*(\d+\.?\d*)",
                    r"Windows\s*(\d+)",
                ]

                for pattern in os_patterns:
                    matches = re.findall(pattern, text)
                    for match in matches:
                        os_name = pattern.split("\\s")[0]
                        requirements["os_requirements"].append(f"{os_name} {match}")

        # Look for compatibility tables specific to TensorRT
        tables = soup.find_all("table")
        for table in tables:
            # Check if this is a TensorRT compatibility table
            table_text = table.get_text().lower()
            if "tensorrt" in table_text or "cuda" in table_text:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    for cell in cells:
                        cell_text = cell.get_text()

                        # Extract TensorRT versions
                        tensorrt_matches = re.findall(
                            r"TensorRT\s*(\d+\.?\d*(?:\.\d+)?)", cell_text, re.I
                        )
                        requirements["tensorrt_versions"].extend(tensorrt_matches)

                        # Extract other versions
                        for key, pattern in self.version_patterns.items():
                            if key in requirements:
                                matches = re.findall(pattern, cell_text)
                                requirements[key].extend(matches)

        # Clean up and validate versions
        for key in [
            "cuda_versions",
            "cudnn_versions",
            "gcc_versions",
            "tensorrt_versions",
        ]:
            if requirements[key]:
                valid_versions = []
                for v in requirements[key]:
                    parsed = parse_version(v)
                    if parsed:
                        valid_versions.append(v)
                    else:
                        logger.debug(f"Invalid {key} version found: {v}")

                requirements[key] = sorted(
                    list(set(valid_versions)),
                    key=lambda x: parse_version(x) or parse_version("0.0.0"),
                    reverse=True,
                )

        # Clean OS requirements
        requirements["os_requirements"] = list(set(requirements["os_requirements"]))

        return requirements

    def _scrape_generic_requirements(self, soup: BeautifulSoup) -> Dict:
        """Generic requirements scraper"""
        requirements = {
            "system_requirements": [],
            "dependencies": [],
            "python_versions": [],
            "notes": [],
        }

        # Look for requirement sections
        requirement_headings = soup.find_all(
            ["h1", "h2", "h3", "h4"],
            text=re.compile(
                r"(requirement|prerequisite|dependency|installation)", re.I
            ),
        )

        for heading in requirement_headings:
            # Get content after heading
            content = []
            current = heading.find_next_sibling()

            for _ in range(10):
                if not current:
                    break
                if current.name in ["h1", "h2", "h3", "h4"]:
                    break
                content.append(current.get_text())
                current = current.find_next_sibling()

            full_text = " ".join(content)

            # Extract versions
            for key, pattern in self.version_patterns.items():
                matches = re.findall(pattern, full_text)
                if matches:
                    # Validate versions
                    valid_matches = []
                    for m in matches:
                        if parse_version(m):
                            valid_matches.append(m)

                    if valid_matches:
                        if key == "python" and "python_versions" in requirements:
                            requirements["python_versions"].extend(valid_matches)
                        else:
                            requirements["system_requirements"].append(
                                {"type": key, "versions": list(set(valid_matches))}
                            )

            # Look for package dependencies
            if "pip install" in full_text:
                # Extract package names from pip install commands
                pip_matches = re.findall(
                    r"pip install\s+([\w\-\[\]>=<.,\s]+)", full_text
                )
                for match in pip_matches:
                    packages = re.findall(
                        r"([\w\-]+)(?:\[[\w,]+\])?(?:[>=<]+[\d.]+)?", match
                    )
                    requirements["dependencies"].extend(packages)

        # Look for lists of requirements
        lists = soup.find_all(["ul", "ol"])
        for lst in lists:
            # Check if this list is near a requirements heading
            prev = lst.find_previous_sibling(["h1", "h2", "h3", "h4"])
            if prev and re.search(
                r"(requirement|prerequisite|dependency)", prev.text, re.I
            ):
                items = lst.find_all("li")
                for item in items:
                    text = item.get_text()
                    requirements["notes"].append(text.strip())

        # Clean up and validate Python versions
        if requirements["python_versions"]:
            valid_versions = []
            for v in requirements["python_versions"]:
                parsed = parse_version(v)
                if parsed:
                    valid_versions.append(v)

            requirements["python_versions"] = sorted(
                list(set(valid_versions)),
                key=lambda x: parse_version(x) or parse_version("0.0.0"),
            )

        # Clean up dependencies
        requirements["dependencies"] = list(set(requirements["dependencies"]))

        return requirements

    async def _extract_requirements_from_tables(self, soup: BeautifulSoup) -> Dict:
        """Extract requirements from HTML tables"""
        requirements = {}

        tables = soup.find_all("table")

        for table in tables:
            # Try to identify compatibility tables
            headers = []
            header_row = table.find("tr")
            if header_row:
                headers = [
                    th.get_text(strip=True).lower()
                    for th in header_row.find_all(["th", "td"])
                ]

            # Look for version compatibility tables
            if any(
                term in " ".join(headers)
                for term in ["version", "cuda", "python", "compatibility"]
            ):
                rows = table.find_all("tr")[1:]

                for row in rows:
                    cells = [
                        td.get_text(strip=True) for td in row.find_all(["td", "th"])
                    ]

                    # Extract version information
                    for i, header in enumerate(headers):
                        if i < len(cells):
                            cell_text = cells[i]

                            # Map headers to requirement keys
                            if "cuda" in header:
                                versions = re.findall(r"(\d+\.?\d*)", cell_text)
                                valid_versions = [
                                    v for v in versions if parse_version(v)
                                ]
                                if valid_versions:
                                    if "cuda_versions" not in requirements:
                                        requirements["cuda_versions"] = []
                                    requirements["cuda_versions"].extend(valid_versions)

                            elif "python" in header:
                                versions = re.findall(r"(\d+\.?\d*)", cell_text)
                                valid_versions = [
                                    v for v in versions if parse_version(v)
                                ]
                                if valid_versions:
                                    if "python_versions" not in requirements:
                                        requirements["python_versions"] = []
                                    requirements["python_versions"].extend(
                                        valid_versions
                                    )

                            elif "cudnn" in header:
                                versions = re.findall(r"(\d+\.?\d*)", cell_text)
                                valid_versions = [
                                    v for v in versions if parse_version(v)
                                ]
                                if valid_versions:
                                    if "cudnn_versions" not in requirements:
                                        requirements["cudnn_versions"] = []
                                    requirements["cudnn_versions"].extend(
                                        valid_versions
                                    )

        # Clean up and sort all versions
        for key in ["cuda_versions", "python_versions", "cudnn_versions"]:
            if key in requirements:
                requirements[key] = sorted(
                    list(set(requirements[key])),
                    key=lambda x: parse_version(x) or parse_version("0.0.0"),
                    reverse=True,
                )

        return requirements

    async def extract_compatibility_matrix(self, package_name: str) -> Dict:
        """Extract compatibility matrix from documentation"""
        package_name = normalize_package_name(package_name)
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 (compatible; DocScraper/1.0)"}
            )

        # Check cache
        cache_key = f"compat_matrix:{package_name}"
        if cache_key in self.compatibility_cache:
            cached_data, timestamp = self.compatibility_cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return cached_data

        compatibility_matrix = {}

        try:
            # Get documentation URL
            doc_url = self.known_docs.get(package_name.lower())
            if not doc_url:
                doc_url = await self._find_documentation_url(package_name)

            if not doc_url:
                return compatibility_matrix

            # Fetch and parse the page
            async with self.session.get(doc_url, timeout=30) as response:
                if response.status != 200:
                    return compatibility_matrix

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Look for compatibility tables
                tables = soup.find_all("table")

                for table in tables:
                    matrix = self._parse_compatibility_table(table, package_name)
                    if matrix:
                        compatibility_matrix.update(matrix)

                # If no tables found, try to extract from text
                if not compatibility_matrix:
                    compatibility_matrix = self._extract_compatibility_from_text(
                        soup, package_name
                    )

                # Package-specific extractors
                if package_name.lower() == "tensorflow":
                    tf_matrix = await self._extract_tensorflow_compatibility_matrix(
                        soup
                    )
                    compatibility_matrix.update(tf_matrix)
                elif package_name.lower() == "pytorch":
                    pt_matrix = await self._extract_pytorch_compatibility_matrix(soup)
                    compatibility_matrix.update(pt_matrix)

            # Cache the results
            self.compatibility_cache[cache_key] = (compatibility_matrix, datetime.now())

        except Exception as e:
            logger.error(
                f"Error extracting compatibility matrix for {package_name}: {e}"
            )

        return compatibility_matrix

    def _parse_compatibility_table(self, table, package_name: str) -> Dict:
        """Parse a compatibility table into a matrix"""
        matrix = {}

        # Get headers
        headers = []
        header_row = table.find("tr")
        if header_row:
            headers = [
                th.get_text(strip=True) for th in header_row.find_all(["th", "td"])
            ]

        if not headers:
            return matrix

        # Identify version column and compatibility columns
        version_col = -1
        compat_cols = {}

        for i, header in enumerate(headers):
            header_lower = header.lower()
            if any(
                term in header_lower
                for term in ["version", package_name.lower(), "release"]
            ):
                version_col = i
            elif any(
                term in header_lower
                for term in ["python", "cuda", "cudnn", "gcc", "os"]
            ):
                # Extract the component name
                for term in ["python", "cuda", "cudnn", "gcc", "os"]:
                    if term in header_lower:
                        compat_cols[i] = term
                        break

        if version_col == -1:
            return matrix

        # Parse rows
        rows = table.find_all("tr")[1:]
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]

            if len(cells) > version_col:
                version = cells[version_col]

                # Clean and validate version
                version = re.sub(r"[^\d.]", "", version)
                if not version:
                    continue

                # Validate version format
                if parse_version(version) is None:  # ADD THIS
                    logger.debug(f"Invalid version format in table: {version}")
                    continue

                matrix[version] = {}

                # Extract compatibility info
                for col_idx, component in compat_cols.items():
                    if col_idx < len(cells):
                        value = cells[col_idx]

                        # Extract and validate versions
                        versions = re.findall(r"(\d+\.?\d*(?:\.\d+)?)", value)
                        valid_versions = []
                        for v in versions:
                            if parse_version(v):  # ADD THIS
                                valid_versions.append(v)

                        if valid_versions:
                            matrix[version][component] = valid_versions
                        elif value.strip() and len(value) < 50:
                            # Store as is if it's not too long
                            matrix[version][component] = [value]

        # Sort matrix by version - ENHANCED
        sorted_matrix = {}
        sorted_versions = sorted(
            matrix.keys(),
            key=lambda v: parse_version(v) or parse_version("0.0.0"),  # ADD THIS
            reverse=True,
        )
        for v in sorted_versions:
            sorted_matrix[v] = matrix[v]

        return sorted_matrix

    def _extract_compatibility_from_text(
        self, soup: BeautifulSoup, package_name: str
    ) -> Dict:
        """Extract compatibility information from text content"""
        matrix = {}

        # Look for version-specific sections
        version_sections = soup.find_all(
            ["div", "section"], text=re.compile(rf"{package_name}\s+(\d+\.?\d*)", re.I)
        )

        for section in version_sections:
            # Extract version
            version_match = re.search(r"(\d+\.?\d*(?:\.\d+)?)", section.text)
            if not version_match:
                continue

            version = version_match.group(1)
            # Validate version
            if parse_version(version) is None:  # ADD THIS
                continue

            matrix[version] = {}

            # Get surrounding text
            parent = section.parent
            if parent:
                text = parent.get_text()

                # Extract compatibility info
                for component, pattern in self.version_patterns.items():
                    matches = re.findall(pattern, text)
                    valid_matches = []
                    for m in matches:
                        if parse_version(m):  # ADD THIS
                            valid_matches.append(m)

                    if valid_matches:
                        matrix[version][component] = list(set(valid_matches))

        return matrix

    async def _extract_tensorflow_compatibility_matrix(
        self, soup: BeautifulSoup
    ) -> Dict:
        """Extract TensorFlow-specific compatibility matrix"""
        matrix = {}

        # TensorFlow often has a specific compatibility table
        # Look for it by searching for "tested build configurations"
        config_section = soup.find(
            text=re.compile(r"tested build configurations", re.I)
        )

        if config_section:
            # Find the nearest table
            parent = config_section.parent
            while parent and parent.name != "table":
                next_table = parent.find_next("table")
                if next_table:
                    parsed = self._parse_compatibility_table(next_table, "tensorflow")
                    matrix.update(parsed)
                    break
                parent = parent.parent

        return matrix

    async def _extract_pytorch_compatibility_matrix(self, soup: BeautifulSoup) -> Dict:
        """Extract PyTorch-specific compatibility matrix"""
        matrix = {}

        # PyTorch compatibility is often in the installation matrix
        # Look for CUDA version mappings
        install_section = soup.find(
            ["div", "section"], id=re.compile(r"install|getting-started")
        )

        if install_section:
            # Extract version mappings from installation commands
            code_blocks = install_section.find_all(["code", "pre"])

            current_pytorch_version = None

            for block in code_blocks:
                text = block.text

                # Look for PyTorch version mentions
                pytorch_match = re.search(r"torch==(\d+\.?\d*(?:\.\d+)?)", text)
                if pytorch_match:
                    current_pytorch_version = pytorch_match.group(1)
                    if current_pytorch_version not in matrix:
                        matrix[current_pytorch_version] = {}

                # Extract CUDA versions from install commands
                if current_pytorch_version:
                    cuda_match = re.search(r"cu(\d{2,3})", text)
                    if cuda_match:
                        cuda_ver = cuda_match.group(1)
                        if len(cuda_ver) == 3:
                            cuda_version = f"{cuda_ver[:2]}.{cuda_ver[2]}"
                        else:
                            cuda_version = cuda_ver

                        if "cuda" not in matrix[current_pytorch_version]:
                            matrix[current_pytorch_version]["cuda"] = []
                        matrix[current_pytorch_version]["cuda"].append(cuda_version)

        return matrix

    def _get_latest_compatible_version(
        self,
        versions: List[str],
        min_version: Optional[str] = None,
        max_version: Optional[str] = None,
    ) -> Optional[str]:
        """Get the latest compatible version from a list"""
        if not versions:
            return None

        # Filter valid versions
        valid_versions = [
            v for v in versions if parse_version(v) is not None
        ]  # ADD THIS

        if not valid_versions:
            return None

        # Filter by min/max constraints
        filtered = []
        for v in valid_versions:
            include = True

            if min_version and compare_versions(v, min_version) < 0:  # ADD THIS
                include = False

            if max_version and compare_versions(v, max_version) > 0:  # ADD THIS
                include = False

            if include:
                filtered.append(v)

        if not filtered:
            return None

        # Return the latest version
        latest = filtered[0]
        for v in filtered[1:]:
            if compare_versions(v, latest) > 0:  # ADD THIS
                latest = v

        return latest
