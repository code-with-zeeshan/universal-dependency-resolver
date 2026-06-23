# tests/unit/test_core/test_data_aggregator.py
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from backend.core.data_aggregator import DataAggregator, Ecosystem


class TestDataAggregator:
    @pytest.fixture
    def aggregator(self):
        """Create DataAggregator instance for testing"""
        return DataAggregator(enable_caching=False)  # Disable caching for tests

    @pytest.mark.asyncio
    async def test_initialization(self, aggregator):
        """Test DataAggregator initialization"""
        assert isinstance(aggregator.sources, dict)
        assert Ecosystem.PYPI in aggregator.sources
        assert Ecosystem.NPM in aggregator.sources
        assert aggregator.enable_caching is False
        assert aggregator.cache_ttl == 3600

    @pytest.mark.asyncio
    async def test_context_manager(self, aggregator):
        """Test async context manager functionality"""
        async with aggregator:
            assert aggregator.executor is not None
        # After context exit, executor should be shutdown
        # (This is hard to test directly, but we can check it doesn't raise)

    @pytest.mark.asyncio
    async def test_get_package_info_basic(self, aggregator):
        """Test basic package info retrieval"""
        # Mock a client response
        mock_client = AsyncMock()
        mock_client.get_package_info.return_value = {
            "name": "test-package",
            "version": "1.0.0",
            "description": "Test package",
            "dependencies": {},
            "system_requirements": {},
            "versions": ["1.0.0"],
            "quality_metrics": {"overall_score": 0.8},
        }

        with patch.object(aggregator, "sources") as mock_sources:
            mock_sources.__getitem__.return_value = mock_client

            result = await aggregator.get_package_info("test-package", "pypi")

            assert result["name"] == "test-package"
            assert result["version"] == "1.0.0"
            mock_client.get_package_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_packages_basic(self, aggregator):
        """Test basic package search"""
        mock_client = AsyncMock()
        mock_client.search_packages.return_value = [
            {"name": "test-pkg", "version": "1.0.0", "description": "Test"}
        ]

        with patch.object(aggregator, "sources") as mock_sources:
            mock_sources.__getitem__.return_value = mock_client

            result = await aggregator.search_packages("test", ["pypi"])

            assert "pypi" in result
            assert len(result["pypi"]) == 1
            assert result["pypi"][0]["name"] == "test-pkg"

    @pytest.mark.asyncio
    async def test_check_compatibility_basic(self, aggregator):
        """Test basic compatibility checking"""
        packages = [{"name": "numpy", "version": "1.24.0", "ecosystem": "pypi"}]
        system_info = {"python": "3.9.0", "os": "linux"}

        # Mock package info
        mock_pkg_info = {
            "name": "numpy",
            "ecosystems": {"pypi": {}},
            "system_requirements": {},
            "quality_metrics": {"overall_score": 0.9},
        }

        with patch.object(aggregator, "get_package_info", return_value=mock_pkg_info):
            result = await aggregator.check_compatibility(packages, system_info)

            assert "overall_compatible" in result
            assert "package_compatibility" in result
            assert "numpy" in result["package_compatibility"]

    @pytest.mark.asyncio
    async def test_empty_packages_error(self, aggregator):
        """Test error handling for empty packages"""
        with pytest.raises(ValueError):
            await aggregator.get_package_info("", "pypi")

    @pytest.mark.asyncio
    async def test_invalid_ecosystem_handling(self, aggregator):
        """Test handling of invalid ecosystem"""
        # Should handle gracefully
        result = await aggregator.search_packages("test", ["invalid_ecosystem"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_caching_disabled(self, aggregator):
        """Test that caching is disabled for this test instance"""
        cache_key = aggregator._get_cache_key("test_method", "arg1", "arg2")
        cached = await aggregator._get_cached(cache_key)
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_operations(self, aggregator):
        """Test cache set/get operations"""
        # Enable caching for this test
        aggregator.enable_caching = True

        cache_key = "test_key"
        test_data = {"test": "data"}

        aggregator._set_cache(cache_key, test_data)
        cached = await aggregator._get_cached(cache_key)

        assert cached == test_data

    @pytest.mark.asyncio
    async def test_normalize_package_name_called(self, aggregator):
        """Test that package names are normalized"""
        with patch(
            "backend.core.data_aggregator.normalize_package_name"
        ) as mock_normalize:
            mock_normalize.return_value = "normalized-name"
            mock_client = AsyncMock()
            mock_client.get_package_info.return_value = {"name": "normalized-name"}

            with patch.object(aggregator, "sources") as mock_sources:
                mock_sources.__getitem__.return_value = mock_client

                await aggregator.get_package_info("Test.Package", "pypi")

                mock_normalize.assert_called_with("Test.Package")
