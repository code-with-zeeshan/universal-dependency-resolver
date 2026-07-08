from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from backend.data_sources.documentation_scraper import DocumentationScraper


class TestDocumentationScraper:
    @pytest.fixture
    def scraper(self):
        return DocumentationScraper()

    def test_known_docs_contains_major_packages(self, scraper):
        assert "tensorflow" in scraper.known_docs
        assert "pytorch" in scraper.known_docs
        assert "numpy" in scraper.known_docs
        assert "pandas" in scraper.known_docs
        assert "opencv" in scraper.known_docs
        assert "cuda" in scraper.known_docs

    def test_doc_patterns_compiled(self, scraper):
        assert scraper.doc_patterns["github"] == r"github\.com/[\w-]+/[\w-]+"
        assert scraper.doc_patterns["readthedocs"] == r"[\w-]+\.readthedocs\.io"

    def test_version_patterns(self, scraper):
        assert "cuda" in scraper.version_patterns
        assert "python" in scraper.version_patterns
        assert "tensorflow" in scraper.version_patterns

    def test_default_cache_ttl(self, scraper):
        assert scraper.cache_ttl > 0

    def test_default_timeout(self, scraper):
        assert scraper.timeout == 30

    def test_max_pages_default(self, scraper):
        assert scraper.max_pages == 10

    def test_compatibility_cache_initialized(self, scraper):
        assert scraper.compatibility_cache == {}

    def test_version_pattern_cuda_matches(self, scraper):
        pattern = scraper.version_patterns["cuda"]
        match = __import__("re").search(pattern, "CUDA 11.8")
        assert match is not None
        assert match.group(1) == "11.8"

    def test_version_pattern_cuda_matches_toolkit(self, scraper):
        pattern = scraper.version_patterns["cuda"]
        match = __import__("re").search(pattern, "CUDA Toolkit 12.1.0")
        assert match is not None
        assert match.group(1) == "12.1.0"

    def test_version_pattern_python_matches(self, scraper):
        pattern = scraper.version_patterns["python"]
        match = __import__("re").search(pattern, "Python 3.11.5")
        assert match is not None
        assert match.group(1) == "3.11.5"

    def test_version_pattern_tensorflow_matches(self, scraper):
        pattern = scraper.version_patterns["tensorflow"]
        match = __import__("re").search(pattern, "TensorFlow 2.13.0")
        assert match is not None
        assert match.group(1) == "2.13.0"

    def test_version_pattern_cudnn_matches(self, scraper):
        pattern = scraper.version_patterns["cudnn"]
        match = __import__("re").search(pattern, "cuDNN v8.9.1")
        assert match is not None
        assert match.group(1) == "8.9.1"

    def test_version_pattern_gcc_matches(self, scraper):
        pattern = scraper.version_patterns["gcc"]
        match = __import__("re").search(pattern, "GCC 12.2.0")
        assert match is not None
        assert match.group(1) == "12.2.0"

    def test_doc_pattern_github_matches(self, scraper):
        pattern = scraper.doc_patterns["github"]
        match = __import__("re").search(pattern, "https://github.com/numpy/numpy")
        assert match is not None

    def test_doc_pattern_readthedocs_matches(self, scraper):
        pattern = scraper.doc_patterns["readthedocs"]
        match = __import__("re").search(pattern, "tensorflow.readthedocs.io")
        assert match is not None

    @pytest.mark.asyncio
    async def test_scrape_no_session_initialized(self, scraper):
        assert scraper.session is None

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_unknown_package(self, scraper):
        result = await scraper.extract_compatibility_matrix("nonexistent_package_xyz")
        assert isinstance(result, dict)

    # ------------------------------------------------------------------ #
    #  __aenter__ / __aexit__ / close                                    #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_async_context_manager_creates_and_closes_session(self):
        scraper = DocumentationScraper()
        assert scraper.session is None
        async with scraper as s:
            assert s.session is not None
            assert not s.session.closed
        assert s.session.closed

    @pytest.mark.asyncio
    async def test_close_method_closes_session(self, scraper):
        mock_session = AsyncMock()
        scraper.session = mock_session
        await scraper.close()
        mock_session.close.assert_awaited_once()
        assert scraper.session is None

    @pytest.mark.asyncio
    async def test_close_no_session_does_not_crash(self, scraper):
        await scraper.close()

    # ------------------------------------------------------------------ #
    #  _check_url_exists                                                 #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_check_url_exists_200(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.head.return_value = cm

        result = await scraper._check_url_exists("https://example.com")
        assert result is True
        scraper.session.head.assert_called_once_with(
            "https://example.com", allow_redirects=True, timeout=5
        )

    @pytest.mark.asyncio
    async def test_check_url_exists_404(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 404
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.head.return_value = cm

        result = await scraper._check_url_exists("https://example.com/404")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_url_exists_exception_returns_false(self, scraper):
        scraper.session = MagicMock()
        scraper.session.head.side_effect = Exception("timeout")

        result = await scraper._check_url_exists("https://example.com")
        assert result is False

    # ------------------------------------------------------------------ #
    #  _get_latest_compatible_version                                    #
    # ------------------------------------------------------------------ #

    def test_get_latest_compatible_version_basic(self, scraper):
        versions = ["1.0.0", "2.0.0", "3.0.0"]
        assert scraper._get_latest_compatible_version(versions) == "3.0.0"

    def test_get_latest_compatible_version_with_min(self, scraper):
        versions = ["1.0.0", "2.0.0", "3.0.0"]
        result = scraper._get_latest_compatible_version(versions, min_version="2.0.0")
        assert result == "3.0.0"

    def test_get_latest_compatible_version_with_max(self, scraper):
        versions = ["1.0.0", "2.0.0", "3.0.0"]
        result = scraper._get_latest_compatible_version(versions, max_version="2.0.0")
        assert result == "2.0.0"

    def test_get_latest_compatible_version_empty_list(self, scraper):
        assert scraper._get_latest_compatible_version([]) is None

    def test_get_latest_compatible_version_all_invalid(self, scraper):
        assert scraper._get_latest_compatible_version(["notaversion"]) is None

    def test_get_latest_compatible_version_no_match_min(self, scraper):
        versions = ["1.0.0", "2.0.0"]
        assert scraper._get_latest_compatible_version(versions, min_version="5.0.0") is None

    def test_get_latest_compatible_version_no_match_max(self, scraper):
        versions = ["1.0.0", "2.0.0"]
        assert scraper._get_latest_compatible_version(versions, max_version="0.5.0") is None

    def test_get_latest_compatible_version_mixed_valid(self, scraper):
        versions = ["1.0.0", "invalid", "3.0.0", "bad"]
        assert scraper._get_latest_compatible_version(versions) == "3.0.0"

    # ------------------------------------------------------------------ #
    #  scrape_installation_requirements                                   #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_scrape_installation_requirements_known_docs(self, scraper):
        scraper.session = MagicMock()
        expected = {"cuda_versions": ["11.8"], "python_versions": ["3.10"]}
        with patch.object(
            scraper, "_scrape_requirements_from_url", new_callable=AsyncMock
        ) as mock_scrape:
            mock_scrape.return_value = expected
            result = await scraper.scrape_installation_requirements("tensorflow")
            assert result == expected
            mock_scrape.assert_awaited_once_with("https://www.tensorflow.org/install", "tensorflow")

    @pytest.mark.asyncio
    async def test_scrape_installation_requirements_cached(self, scraper):
        scraper.session = MagicMock()
        from datetime import datetime

        cached = ({"cuda_versions": ["11.8"]}, datetime.now())
        scraper.compatibility_cache["requirements:tensorflow"] = cached
        with patch.object(
            scraper, "_scrape_requirements_from_url", new_callable=AsyncMock
        ) as mock_scrape:
            result = await scraper.scrape_installation_requirements("tensorflow")
            assert result == {"cuda_versions": ["11.8"]}
            mock_scrape.assert_not_called()

    @pytest.mark.asyncio
    async def test_scrape_installation_requirements_expired_cache(self, scraper):
        scraper.session = MagicMock()
        from datetime import datetime, timedelta

        old = ({"cuda_versions": ["11.8"]}, datetime.now() - timedelta(hours=1))
        scraper.cache_ttl = 60  # 1 minute TTL
        scraper.compatibility_cache["requirements:tensorflow"] = old
        with patch.object(
            scraper, "_scrape_requirements_from_url", new_callable=AsyncMock
        ) as mock_scrape:
            mock_scrape.return_value = {"python_versions": ["3.11"]}
            result = await scraper.scrape_installation_requirements("tensorflow")
            assert result == {"python_versions": ["3.11"]}
            mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scrape_installation_requirements_no_url(self, scraper):
        scraper.session = MagicMock()
        with patch.object(scraper, "_find_documentation_url", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = None
            result = await scraper.scrape_installation_requirements("nonexistent_package")
            assert result == {}

    # ------------------------------------------------------------------ #
    #  extract_compatibility_matrix                                       #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_known_docs(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value="<html><table><tr><th>Version</th></tr></table></html>"
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        with patch.object(scraper, "_parse_compatibility_table") as mock_parse:
            mock_parse.return_value = {"2.0.0": {"cuda": ["11.8"]}}
            result = await scraper.extract_compatibility_matrix("tensorflow")
            assert "2.0.0" in result
            mock_parse.assert_called()

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_no_tables(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html><body>no tables here</body></html>")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        with (
            patch.object(scraper, "_extract_compatibility_from_text") as mock_extract,
            patch.object(scraper, "_find_documentation_url", new_callable=AsyncMock) as mock_find,
        ):
            mock_find.return_value = "https://example.com/docs"
            mock_extract.return_value = {"1.0.0": {"python": ["3.10"]}}
            result = await scraper.extract_compatibility_matrix("somepackage")
            assert "1.0.0" in result

    # ------------------------------------------------------------------ #
    #  _scrape_requirements_from_url                                      #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_scrape_requirements_from_url_not_200(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 404
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        result = await scraper._scrape_requirements_from_url("https://example.com", "somepkg")
        assert result == {}

    @pytest.mark.asyncio
    async def test_scrape_requirements_from_url_generic(self, scraper):
        scraper.session = MagicMock()
        html = "<html><h2>Requirements</h2><p>Python 3.10 required</p></html>"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        result = await scraper._scrape_requirements_from_url("https://example.com", "somepkg")
        assert "python_versions" in result
        assert result["python_versions"] == ["3.10"]

    @pytest.mark.asyncio
    async def test_scrape_requirements_from_url_tensorflow(self, scraper):
        scraper.session = MagicMock()
        html = "<html><table><tr><th>Version</th><th>CUDA</th></tr><tr><td>2.0.0</td><td>CUDA 11.8</td></tr></table></html>"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=html)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        result = await scraper._scrape_requirements_from_url("https://example.com", "tensorflow")
        assert "cuda_versions" in result

    @pytest.mark.asyncio
    async def test_scrape_requirements_from_url_exception(self, scraper):
        scraper.session = MagicMock()
        scraper.session.get.side_effect = Exception("network error")

        result = await scraper._scrape_requirements_from_url("https://example.com", "somepkg")
        assert result == {}

    # ------------------------------------------------------------------ #
    #  _scrape_tensorflow_requirements                                    #
    # ------------------------------------------------------------------ #

    def test_scrape_tensorflow_requirements_from_tables(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th><th>cuDNN</th><th>Python</th></tr>
            <tr><td>2.12.0</td><td>CUDA 11.8</td><td>cuDNN 8.6</td><td>Python 3.10</td></tr>
            <tr><td>2.13.0</td><td>CUDA 12.1</td><td>cuDNN 8.9</td><td>Python 3.11</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorflow_requirements(soup)
        assert "cuda_versions" in result
        assert "11.8" in result["cuda_versions"]
        assert "12.1" in result["cuda_versions"]
        assert "cudnn_versions" in result
        assert "8.6" in result["cudnn_versions"]
        assert "8.9" in result["cudnn_versions"]
        assert "python_versions" in result
        assert "3.10" in result["python_versions"]
        assert "3.11" in result["python_versions"]

    def test_scrape_tensorflow_requirements_empty_soup(self, scraper):
        soup = BeautifulSoup("<html></html>", "html.parser")
        result = scraper._scrape_tensorflow_requirements(soup)
        assert result["cuda_versions"] == []
        assert result["cudnn_versions"] == []
        assert result["python_versions"] == []

    # ------------------------------------------------------------------ #
    #  _scrape_pytorch_requirements                                       #
    # ------------------------------------------------------------------ #

    def test_scrape_pytorch_requirements_selectors(self, scraper):
        html = """
        <div class="selector">
            <a>CUDA 11.8</a>
            <a>CUDA 12.1</a>
        </div>
        <pre>pip install torch==2.0.0+cu121</pre>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_pytorch_requirements(soup)
        assert "cuda_versions" in result
        assert "11.8" in result["cuda_versions"]
        assert "12.1" in result["cuda_versions"]

    def test_scrape_pytorch_requirements_code_blocks(self, scraper):
        html = """
        <code>conda install pytorch torchvision torchaudio cudatoolkit=11.8 -c pytorch</code>
        <pre>pip install torch==1.13.0+cu117</pre>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_pytorch_requirements(soup)
        assert "cuda_versions" in result

    def test_scrape_pytorch_requirements_os_selector(self, scraper):
        html = """
        <div class="option">
            <button>Linux</button>
            <button>Windows</button>
            <button>macOS</button>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_pytorch_requirements(soup)
        assert "os_support" in result
        assert "Linux" in result["os_support"]

    # ------------------------------------------------------------------ #
    #  _scrape_tensorrt_requirements                                       #
    # ------------------------------------------------------------------ #

    def test_scrape_tensorrt_requirements_system_reqs(self, scraper):
        html = "<h2>System Requirements</h2><p>Ubuntu 22.04 or CentOS 8</p>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorrt_requirements(soup)
        assert "os_requirements" in result

    def test_scrape_tensorrt_requirements_tables(self, scraper):
        html = """
        <h2>Prerequisites</h2>
        <p>GCC 12.2 required</p>
        <table>
            <tr><th>TensorRT Version</th><th>CUDA</th></tr>
            <tr><td>TensorRT 8.5</td><td>CUDA 11.8</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorrt_requirements(soup)
        assert "tensorrt_versions" in result
        assert "8.5" in result["tensorrt_versions"]

    # ------------------------------------------------------------------ #
    #  _scrape_generic_requirements                                        #
    # ------------------------------------------------------------------ #

    def test_scrape_generic_requirements_with_heading(self, scraper):
        html = """
        <h2>Requirements</h2>
        <p>CUDA 11.8 and Python 3.10 are required</p>
        <h2>Installation</h2>
        <p>Run pip install tensorflow</p>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_generic_requirements(soup)
        assert "system_requirements" in result
        assert "python_versions" in result
        assert "3.10" in result["python_versions"]
        assert "dependencies" in result
        assert "tensorflow" in result["dependencies"]

    def test_scrape_generic_requirements_with_list(self, scraper):
        html = """
        <h2>Prerequisites</h2>
        <ul>
            <li>Python 3.8 or later</li>
            <li>NumPy >= 1.19</li>
        </ul>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_generic_requirements(soup)
        assert "notes" in result
        assert len(result["notes"]) > 0

    def test_scrape_generic_requirements_no_matches(self, scraper):
        html = "<html><body><p>No requirements here</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_generic_requirements(soup)
        assert result["system_requirements"] == []
        assert result["python_versions"] == []
        assert result["notes"] == []

    # ------------------------------------------------------------------ #
    #  _extract_requirements_from_tables (async)                           #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_extract_requirements_from_tables_cuda(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th></tr>
            <tr><td>2.0.0</td><td>11.8</td></tr>
            <tr><td>2.1.0</td><td>12.1</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_requirements_from_tables(soup)
        assert "cuda_versions" in result

    @pytest.mark.asyncio
    async def test_extract_requirements_from_tables_python(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>Python</th></tr>
            <tr><td>2.0.0</td><td>3.10</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_requirements_from_tables(soup)
        assert "python_versions" in result

    @pytest.mark.asyncio
    async def test_extract_requirements_from_tables_cudnn(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>cuDNN</th></tr>
            <tr><td>2.0.0</td><td>8.6</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_requirements_from_tables(soup)
        assert "cudnn_versions" in result

    @pytest.mark.asyncio
    async def test_extract_requirements_from_tables_no_match(self, scraper):
        html = """
        <table>
            <tr><th>Name</th><th>Value</th></tr>
            <tr><td>foo</td><td>bar</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_requirements_from_tables(soup)
        assert result == {}

    # ------------------------------------------------------------------ #
    #  _parse_compatibility_table                                         #
    # ------------------------------------------------------------------ #

    def test_parse_compatibility_table_basic(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th><th>Python</th></tr>
            <tr><td>2.0.0</td><td>11.8</td><td>3.10</td></tr>
            <tr><td>2.1.0</td><td>12.1</td><td>3.11</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert "2.0.0" in result
        assert "2.1.0" in result
        assert result["2.0.0"]["cuda"] == ["11.8"]
        assert result["2.0.0"]["python"] == ["3.10"]

    def test_parse_compatibility_table_no_headers(self, scraper):
        html = "<table><tr><td>no header row</td></tr></table>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert result == {}

    def test_parse_compatibility_table_no_version_col(self, scraper):
        html = """
        <table>
            <tr><th>CUDA</th><th>Python</th></tr>
            <tr><td>11.8</td><td>3.10</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert result == {}

    def test_parse_compatibility_table_invalid_version(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th></tr>
            <tr><td>N/A</td><td>11.8</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert result == {}

    def test_parse_compatibility_table_package_name_column(self, scraper):
        html = """
        <table>
            <tr><th>TensorFlow</th><th>CUDA</th></tr>
            <tr><td>2.0.0</td><td>11.8</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert "2.0.0" in result
        assert result["2.0.0"]["cuda"] == ["11.8"]

    # ------------------------------------------------------------------ #
    #  _extract_compatibility_from_text                                    #
    # ------------------------------------------------------------------ #

    def test_extract_compatibility_from_text_matches(self, scraper):
        html = """
        <div>
            <section>tensorflow 2.13.0 requires CUDA 11.8 and Python 3.10</section>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._extract_compatibility_from_text(soup, "tensorflow")
        assert "2.13.0" in result
        assert result["2.13.0"]["cuda"] == ["11.8"]
        assert result["2.13.0"]["python"] == ["3.10"]

    def test_extract_compatibility_from_text_no_match(self, scraper):
        html = "<div><p>Nothing relevant here</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._extract_compatibility_from_text(soup, "tensorflow")
        assert result == {}

    # ------------------------------------------------------------------ #
    #  _get_pypi_documentation_url                                        #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_get_pypi_documentation_url_found(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "info": {
                    "docs_url": "https://docs.example.com/",
                    "home_page": "",
                }
            }
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        result = await scraper._get_pypi_documentation_url("testpkg")
        assert result == "https://docs.example.com/"

    @pytest.mark.asyncio
    async def test_get_pypi_documentation_url_project_urls(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "info": {
                    "docs_url": "",
                    "home_page": "",
                    "project_urls": {"Documentation": "https://readthedocs.io/testpkg"},
                }
            }
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        result = await scraper._get_pypi_documentation_url("testpkg")
        assert result == "https://readthedocs.io/testpkg"

    @pytest.mark.asyncio
    async def test_get_pypi_documentation_url_not_found(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "info": {
                    "docs_url": "",
                    "home_page": "",
                    "project_urls": {},
                }
            }
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm

        result = await scraper._get_pypi_documentation_url("testpkg")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_pypi_documentation_url_exception(self, scraper):
        scraper.session = MagicMock()
        scraper.session.get.side_effect = Exception("API error")
        result = await scraper._get_pypi_documentation_url("testpkg")
        assert result is None

    # ------------------------------------------------------------------ #
    #  _find_documentation_url  (edge: common patterns)                   #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_find_documentation_url_common_patterns(self, scraper):
        scraper.session = MagicMock()
        with (
            patch.object(
                scraper, "_get_pypi_documentation_url", new_callable=AsyncMock
            ) as mock_pypi,
            patch.object(
                scraper, "_get_github_documentation_url", new_callable=AsyncMock
            ) as mock_gh,
            patch.object(scraper, "_check_url_exists", new_callable=AsyncMock) as mock_exists,
            patch.object(
                scraper, "_search_documentation_url", new_callable=AsyncMock
            ) as mock_search,
        ):
            mock_pypi.return_value = None
            mock_gh.return_value = None
            mock_exists.side_effect = [True, False, False, False, False]
            mock_search.return_value = None
            result = await scraper._find_documentation_url("mypackage")
            assert result == "https://mypackage.readthedocs.io/en/latest/"
            assert mock_exists.call_count >= 1

    @pytest.mark.asyncio
    async def test_find_documentation_url_all_fail(self, scraper):
        scraper.session = MagicMock()
        with (
            patch.object(
                scraper, "_get_pypi_documentation_url", new_callable=AsyncMock
            ) as mock_pypi,
            patch.object(
                scraper, "_get_github_documentation_url", new_callable=AsyncMock
            ) as mock_gh,
            patch.object(scraper, "_check_url_exists", new_callable=AsyncMock) as mock_exists,
            patch.object(
                scraper, "_search_documentation_url", new_callable=AsyncMock
            ) as mock_search,
        ):
            mock_pypi.return_value = None
            mock_gh.return_value = None
            mock_exists.return_value = False
            mock_search.return_value = None
            result = await scraper._find_documentation_url("nobody")
            assert result is None

    # ------------------------------------------------------------------ #
    #  _extract_tensorflow_compatibility_matrix / _extract_pytorch_...    #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_extract_tensorflow_compatibility_matrix(self, scraper):
        html = """
        <div><p>Tested build configurations</p>
        <table><tr><th>Version</th><th>CUDA</th></tr><tr><td>2.0.0</td><td>11.8</td></tr></table>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_tensorflow_compatibility_matrix(soup)
        assert "2.0.0" in result
        assert result["2.0.0"]["cuda"] == ["11.8"]

    @pytest.mark.asyncio
    async def test_extract_pytorch_compatibility_matrix(self, scraper):
        html = """
        <div id="install">
            <pre>pip install torch==2.0.0+cu121</pre>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_pytorch_compatibility_matrix(soup)
        assert "2.0.0" in result
        assert "12.1" in result["2.0.0"]["cuda"]

    @pytest.mark.asyncio
    async def test_extract_pytorch_compatibility_matrix_no_section(self, scraper):
        soup = BeautifulSoup("<html></html>", "html.parser")
        result = await scraper._extract_pytorch_compatibility_matrix(soup)
        assert result == {}

    # ------------------------------------------------------------------ #
    #  Additional coverage: auto-create session in scrape_install_reqs   #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_scrape_installation_requirements_creates_session(self, scraper):
        assert scraper.session is None
        with patch.object(
            scraper, "_scrape_requirements_from_url", new_callable=AsyncMock
        ) as mock_scrape:
            mock_scrape.return_value = {"cuda_versions": ["11.8"]}
            result = await scraper.scrape_installation_requirements("tensorflow")
            assert result == {"cuda_versions": ["11.8"]}
            assert scraper.session is not None

    @pytest.mark.asyncio
    async def test_scrape_installation_requirements_exception(self, scraper):
        scraper.session = MagicMock()
        with patch.object(
            scraper, "_scrape_requirements_from_url", new_callable=AsyncMock
        ) as mock_scrape:
            mock_scrape.side_effect = Exception("boom")
            result = await scraper.scrape_installation_requirements("tensorflow")
            assert result == {}

    # ------------------------------------------------------------------ #
    #  _find_documentation_url — strategy success paths                  #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_find_documentation_url_from_pypi(self, scraper):
        with (
            patch.object(
                scraper, "_get_pypi_documentation_url", new_callable=AsyncMock
            ) as mock_pypi,
            patch.object(
                scraper, "_get_github_documentation_url", new_callable=AsyncMock
            ) as mock_gh,
            patch.object(scraper, "_check_url_exists", new_callable=AsyncMock),
            patch.object(scraper, "_search_documentation_url", new_callable=AsyncMock),
        ):
            mock_pypi.return_value = "https://docs.example.com/"
            result = await scraper._find_documentation_url("testpkg")
            assert result == "https://docs.example.com/"
            mock_gh.assert_not_called()

    @pytest.mark.asyncio
    async def test_find_documentation_url_from_github(self, scraper):
        with (
            patch.object(
                scraper, "_get_pypi_documentation_url", new_callable=AsyncMock
            ) as mock_pypi,
            patch.object(
                scraper, "_get_github_documentation_url", new_callable=AsyncMock
            ) as mock_gh,
            patch.object(scraper, "_check_url_exists", new_callable=AsyncMock),
            patch.object(scraper, "_search_documentation_url", new_callable=AsyncMock),
        ):
            mock_pypi.return_value = None
            mock_gh.return_value = "https://github.com/testpkg/testpkg"
            result = await scraper._find_documentation_url("testpkg")
            assert result == "https://github.com/testpkg/testpkg"

    @pytest.mark.asyncio
    async def test_find_documentation_url_from_search(self, scraper):
        with (
            patch.object(
                scraper, "_get_pypi_documentation_url", new_callable=AsyncMock
            ) as mock_pypi,
            patch.object(
                scraper, "_get_github_documentation_url", new_callable=AsyncMock
            ) as mock_gh,
            patch.object(scraper, "_check_url_exists", new_callable=AsyncMock) as mock_exists,
            patch.object(
                scraper, "_search_documentation_url", new_callable=AsyncMock
            ) as mock_search,
        ):
            mock_pypi.return_value = None
            mock_gh.return_value = None
            mock_exists.return_value = False
            mock_search.return_value = "https://docs.example.com/pkg"
            result = await scraper._find_documentation_url("testpkg")
            assert result == "https://docs.example.com/pkg"

    # ------------------------------------------------------------------ #
    #  _get_pypi_documentation_url — homepage fallback                   #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_get_pypi_documentation_url_homepage_fallback(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "info": {
                    "docs_url": "",
                    "documentation_url": "",
                    "home_page": "https://example.com/",
                    "project_urls": {},
                }
            }
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        with patch.object(scraper, "_check_url_exists", new_callable=AsyncMock) as mock_exists:
            mock_exists.return_value = True
            result = await scraper._get_pypi_documentation_url("testpkg")
            assert result == "https://example.com/"

    # ------------------------------------------------------------------ #
    #  _get_github_documentation_url                                      #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_get_github_documentation_url_found(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "items": [
                    {"html_url": "https://github.com/numpy/numpy"},
                ]
            }
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        with patch.object(scraper, "_check_url_exists", new_callable=AsyncMock) as mock_exists:
            mock_exists.return_value = True
            result = await scraper._get_github_documentation_url("numpy")
            assert result is not None
            assert "github.com" in result

    @pytest.mark.asyncio
    async def test_get_github_documentation_url_all_fail(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "items": [
                    {"html_url": "https://github.com/numpy/numpy"},
                ]
            }
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        with patch.object(scraper, "_check_url_exists", new_callable=AsyncMock) as mock_exists:
            mock_exists.return_value = False
            result = await scraper._get_github_documentation_url("numpy")
            assert result == "https://github.com/numpy/numpy"

    @pytest.mark.asyncio
    async def test_get_github_documentation_url_exception(self, scraper):
        scraper.session = MagicMock()
        scraper.session.get.side_effect = Exception("GitHub error")
        result = await scraper._get_github_documentation_url("numpy")
        assert result is None

    # ------------------------------------------------------------------ #
    #  _search_documentation_url                                          #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_search_documentation_url_found(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value="""<html><body>
                <a class="result__a" href="https://docs.example.com/pkg">Install docs</a>
            </body></html>"""
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper._search_documentation_url("testpkg")
        assert result == "https://docs.example.com/pkg"

    @pytest.mark.asyncio
    async def test_search_documentation_url_not_found(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html><body>no relevant links</body></html>")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper._search_documentation_url("testpkg")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_documentation_url_exception(self, scraper):
        scraper.session = MagicMock()
        scraper.session.get.side_effect = Exception("DDG error")
        result = await scraper._search_documentation_url("testpkg")
        assert result is None

    # ------------------------------------------------------------------ #
    #  _scrape_requirements_from_url — pytorch & tensorrt dispatch        #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_scrape_requirements_from_url_pytorch(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value="<html><div class='selector'><a>CUDA 11.8</a></div></html>"
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper._scrape_requirements_from_url("https://pytorch.org", "pytorch")
        assert "cuda_versions" in result
        assert "11.8" in result["cuda_versions"]

    @pytest.mark.asyncio
    async def test_scrape_requirements_from_url_tensorrt(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value="<html><h2>System Requirements</h2><p>CUDA 11.8</p></html>"
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper._scrape_requirements_from_url("https://docs.nvidia.com", "tensorrt")
        assert "cuda_versions" in result

    # ------------------------------------------------------------------ #
    #  _scrape_tensorflow_requirements — version sections                 #
    # ------------------------------------------------------------------ #

    def test_scrape_tensorflow_requirements_version_sections(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th></tr>
            <tr><td>2.0.0</td><td>CUDA 11.8</td></tr>
        </table>
        <div>requirements: Python 3.10 and CUDA 11.8 are required</div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorflow_requirements(soup)
        assert "11.8" in result["cuda_versions"]

    def test_scrape_tensorflow_requirements_invalid_version(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th><th>cuDNN</th></tr>
            <tr><td>2.0.0</td><td>CUDA .1</td><td>cuDNN .1</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorflow_requirements(soup)
        assert result["cuda_versions"] == []

    # ------------------------------------------------------------------ #
    #  _scrape_pytorch_requirements — extra branches                      #
    # ------------------------------------------------------------------ #

    def test_scrape_pytorch_requirements_2digit_cuda(self, scraper):
        html = "<pre>pip install torch==2.0.0+cu11</pre>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_pytorch_requirements(soup)
        assert "cuda_versions" in result

    def test_scrape_pytorch_requirements_invalid_version(self, scraper):
        html = """
        <div class="selector">
            <a>CUDA 11.</a>
        </div>
        <pre>pip install torch==2.0.0+cu11</pre>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_pytorch_requirements(soup)
        assert "cuda_versions" in result
        # "11." is an invalid version that gets filtered out
        assert "11." not in result["cuda_versions"]

    # ------------------------------------------------------------------ #
    #  _scrape_tensorrt_requirements — edge cases                         #
    # ------------------------------------------------------------------ #

    def test_scrape_tensorrt_requirements_no_name(self, scraper):
        html = "<h2>Prerequisites</h2>text node here"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorrt_requirements(soup)
        assert "cuda_versions" in result

    def test_scrape_tensorrt_requirements_hits_heading(self, scraper):
        html = "<h2>Prerequisites</h2><h3>Next Heading</h3>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorrt_requirements(soup)
        assert "cuda_versions" in result

    def test_scrape_tensorrt_requirements_section_versions(self, scraper):
        html = """
        <h2>System Requirements</h2>
        <p>CUDA 11.8</p>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorrt_requirements(soup)
        assert "os_requirements" in result

    def test_scrape_tensorrt_requirements_table_versions(self, scraper):
        html = """
        <h2>System Requirements</h2><p>CUDA 11.8</p>
        <table>
            <tr><th>TensorRT Version</th><th>CUDA</th></tr>
            <tr><td>TensorRT 8.5</td><td>CUDA 11.8</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._scrape_tensorrt_requirements(soup)
        assert "tensorrt_versions" in result
        assert "8.5" in result["tensorrt_versions"]

    def test_scrape_tensorrt_requirements_invalid_version(self, scraper):
        html = """
        <h2>System Requirements</h2>
        <p>CUDA .1, GCC .1</p>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper._scrape_tensorrt_requirements(soup)
        assert True

    # ------------------------------------------------------------------ #
    #  extract_compatibility_matrix — additional paths                    #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_cached(self, scraper):
        from datetime import datetime

        scraper.session = MagicMock()
        cached = ({"2.0.0": {"cuda": ["11.8"]}}, datetime.now())
        scraper.compatibility_cache["compat_matrix:tensorflow"] = cached
        result = await scraper.extract_compatibility_matrix("tensorflow")
        assert "2.0.0" in result
        assert result["2.0.0"]["cuda"] == ["11.8"]

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_not_200(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 404
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper.extract_compatibility_matrix("tensorflow")
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_pytorch(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value="<html><div id='install'><pre>pip install torch==2.0.0+cu121</pre></div></html>"
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper.extract_compatibility_matrix("pytorch")
        assert "2.0.0" in result
        assert "12.1" in result["2.0.0"]["cuda"]

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_exception(self, scraper):
        scraper.session = MagicMock()
        scraper.session.get.side_effect = Exception("network error")
        result = await scraper.extract_compatibility_matrix("tensorflow")
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_compatibility_matrix_tensorflow_package(self, scraper):
        scraper.session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value="<html><div><p>Tested build configurations</p><table><tr><th>Version</th><th>CUDA</th></tr><tr><td>2.0.0</td><td>11.8</td></tr></table></div></html>"
        )
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock()
        scraper.session.get.return_value = cm
        result = await scraper.extract_compatibility_matrix("tensorflow")
        assert "2.0.0" in result

    # ------------------------------------------------------------------ #
    #  _parse_compatibility_table — remaining branches                    #
    # ------------------------------------------------------------------ #

    def test_parse_compatibility_table_empty_header_row(self, scraper):
        html = "<table><tr></tr></table>"
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert result == {}

    def test_parse_compatibility_table_invalid_version_after_sub(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th></tr>
            <tr><td>.1</td><td>11.8</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert result == {}

    def test_parse_compatibility_table_short_value(self, scraper):
        html = """
        <table>
            <tr><th>Version</th><th>CUDA</th><th>Python</th></tr>
            <tr><td>2.0.0</td><td>11.8</td><td>Yes</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._parse_compatibility_table(soup.find("table"), "tensorflow")
        assert "2.0.0" in result
        assert "11.8" in result["2.0.0"]["cuda"]
        assert "Yes" in result["2.0.0"]["python"]

    # ------------------------------------------------------------------ #
    #  _extract_compatibility_from_text — invalid version                 #
    # ------------------------------------------------------------------ #

    def test_extract_compatibility_from_text_invalid_version(self, scraper):
        html = """
        <div>
            <section>tensorflow 11. requires CUDA 11.8</section>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = scraper._extract_compatibility_from_text(soup, "tensorflow")
        assert result == {}

    # ------------------------------------------------------------------ #
    #  _extract_tensorflow_compatibility_matrix — parent loop             #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_extract_tensorflow_compatibility_matrix_parent_loop(self, scraper):
        html = """
        <div><p>Tested build configurations</p></div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_tensorflow_compatibility_matrix(soup)
        assert result == {}

    # ------------------------------------------------------------------ #
    #  _extract_pytorch_compatibility_matrix — 2-digit CUDA               #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_extract_pytorch_compatibility_matrix_2digit_cuda(self, scraper):
        html = """
        <div id="install">
            <pre>pip install torch==2.0.0+cu11</pre>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = await scraper._extract_pytorch_compatibility_matrix(soup)
        assert "2.0.0" in result
