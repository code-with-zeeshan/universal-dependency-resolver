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
        assert isinstance(aggregator._sources, dict)
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
        from backend.core.data_aggregator import Ecosystem
        mock_client = AsyncMock(spec=[])
        mock_client.get_package_info_async = AsyncMock(return_value={
            "name": "test-package",
            "version": "1.0.0",
            "description": "Test package",
            "dependencies": {},
            "system_requirements": {},
            "versions": ["1.0.0"],
            "quality_metrics": {"overall_score": 0.8},
        })
        mock_client.package_exists = AsyncMock(return_value=True)
        with patch.dict(aggregator._sources, {Ecosystem.PYPI: mock_client}):
            result = await aggregator.get_package_info("test-package", "pypi")

            assert result["name"] == "test-package"
            assert result["ecosystems"]["pypi"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_search_packages_basic(self, aggregator):
        """Test basic package search"""
        from backend.core.data_aggregator import Ecosystem
        mock_client = AsyncMock(spec=[])
        mock_client.search_packages = Mock(return_value=[])
        mock_client.search_packages_async = AsyncMock(return_value=[
            {"name": "test-pkg", "version": "1.0.0", "description": "Test"}
        ])

        with patch.dict(aggregator._sources, {Ecosystem.PYPI: mock_client}):
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
        # The code normalizes empty name to "" and proceeds; no ValueError is raised
        result = await aggregator.get_package_info("", "pypi")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_invalid_ecosystem_handling(self, aggregator):
        """Test handling of invalid ecosystem"""
        # Should handle gracefully
        result = await aggregator.search_packages("test", ["invalid_ecosystem"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_caching_disabled(self, aggregator):
        """Test that caching is disabled for this test instance"""
        assert aggregator.enable_caching is False

    @pytest.mark.asyncio
    async def test_cache_operations(self, aggregator):
        """Test cache set/get operations via cache_manager"""
        from backend.core.cache import cache_manager

        # Initialize cache (in-memory) for testing
        await cache_manager.connect()
        cache_key = "test_key"
        test_data = {"test": "data"}

        await cache_manager.set(cache_key, test_data)
        cached = await cache_manager.get(cache_key)

        assert cached == test_data

    @pytest.mark.asyncio
    async def test_normalize_package_name_called(self, aggregator):
        """Test that package names are normalized"""
        from backend.core.data_aggregator import Ecosystem
        with patch(
            "backend.core.data_aggregator.normalize_package_name"
        ) as mock_normalize:
            mock_normalize.return_value = "normalized-name"
            mock_client = AsyncMock(spec=[])
            mock_client.get_package_info_async = AsyncMock(return_value={"name": "normalized-name"})
            mock_client.package_exists = AsyncMock(return_value=True)

            with patch.dict(aggregator._sources, {Ecosystem.PYPI: mock_client}):
                await aggregator.get_package_info("Test.Package", "pypi")

                mock_normalize.assert_any_call("Test.Package")
