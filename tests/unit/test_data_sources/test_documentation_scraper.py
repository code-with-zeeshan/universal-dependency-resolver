from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
