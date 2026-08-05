"""Unit tests for backend/core/cuda_index.py."""

from unittest.mock import patch

import pytest

from backend.core import cuda_index as ci


@pytest.fixture(autouse=True)
def _clear_cache():
    ci.clear_index_cache()
    yield
    ci.clear_index_cache()


class TestNormalizeCudaTag:
    def test_dotted_version(self):
        assert ci.normalize_cuda_tag("12.1") == "cu121"

    def test_underscore_separated(self):
        assert ci.normalize_cuda_tag("12_1") == "cu121"

    def test_already_tagged(self):
        assert ci.normalize_cuda_tag("cu121") == "cu121"

    def test_lowercase(self):
        assert ci.normalize_cuda_tag("cu121") == "cu121"

    def test_cuda_11_8(self):
        assert ci.normalize_cuda_tag("11.8") == "cu118"

    def test_cuda_13_0(self):
        assert ci.normalize_cuda_tag("13.0") == "cu130"

    def test_cuda_13(self):
        assert ci.normalize_cuda_tag("13") == "cu13"

    def test_empty(self):
        assert ci.normalize_cuda_tag("") == ""

    def test_garbage(self):
        assert ci.normalize_cuda_tag("nonsense") == ""

    def test_whitespace(self):
        assert ci.normalize_cuda_tag("  12.1  ") == "cu121"


class TestIsPytorchFamily:
    def test_torch(self):
        assert ci.is_pytorch_family("torch") is True

    def test_torchvision(self):
        assert ci.is_pytorch_family("torchvision") is True

    def test_torchaudio(self):
        assert ci.is_pytorch_family("torchaudio") is True

    def test_triton(self):
        assert ci.is_pytorch_family("triton") is True

    def test_case_insensitive(self):
        assert ci.is_pytorch_family("Torch") is True

    def test_flask_not_family(self):
        assert ci.is_pytorch_family("flask") is False

    def test_empty(self):
        assert ci.is_pytorch_family("") is False

    def test_none(self):
        assert ci.is_pytorch_family(None) is False


class TestParseSimpleIndex:
    def test_relative_hrefs(self):
        text = """
        <a href="torch-2.1.0%2Bcu121-cp310-cp310-linux_x86_64.whl">torch-2.1.0+cu121-...whl</a>
        <a href="torch-2.5.1%2Bcu121-cp311-cp311-linux_x86_64.whl">torch-2.5.1+cu121-...whl</a>
        """
        windows = ci.parse_simple_index(text)
        assert windows == {"2.1.0": "2.1.0+cu121", "2.5.1": "2.5.1+cu121"}

    def test_full_cdn_urls(self):
        text = (
            '<a href="https://download-r2.pytorch.org/whl/cu121/torch-2.1.0%2Bcu121-'
            'cp310-cp310-linux_x86_64.whl#sha256=abc">torch-2.1.0+cu121</a>'
        )
        windows = ci.parse_simple_index(text)
        assert windows == {"2.1.0": "2.1.0+cu121"}

    def test_literal_plus(self):
        text = (
            '<a href="https://download-r2.pytorch.org/whl/cu121/torch-2.1.0+cu121-'
            'cp310-cp310-linux_x86_64.whl">torch-2.1.0+cu121</a>'
        )
        windows = ci.parse_simple_index(text)
        assert windows == {"2.1.0": "2.1.0+cu121"}

    def test_duplicate_base_windows_dedupe(self):
        text = """
        <a href="torch-2.1.0%2Bcu121-cp310-...whl">torch-2.1.0+cu121</a>
        <a href="torch-2.1.0%2Bcu121-cp311-...whl">torch-2.1.0+cu121</a>
        """
        windows = ci.parse_simple_index(text)
        assert windows == {"2.1.0": "2.1.0+cu121"}

    def test_empty_text(self):
        assert ci.parse_simple_index("") == {}

    def test_no_wheels(self):
        assert ci.parse_simple_index("<html><body>empty</body></html>") == {}


class TestFetchIndexVersions:
    def test_cached_result_returned(self):
        with patch.object(
            ci, "_fetch_simple_index_sync", return_value='<a href="torch-1.0.0%2Bcu121-x.whl">x</a>'
        ) as mock_fetch:
            first = ci.fetch_index_versions("torch", "cu121")
            second = ci.fetch_index_versions("torch", "cu121")
        assert first == {"1.0.0": "1.0.0+cu121"}
        assert second == first
        assert mock_fetch.call_count == 1

    def test_network_failure_returns_empty(self):
        with patch.object(ci, "_fetch_simple_index_sync", side_effect=RuntimeError("boom")):
            assert ci.fetch_index_versions("torch", "cu121") == {}

    def test_parse_failure_returns_empty(self):
        with patch.object(ci, "_fetch_simple_index_sync", return_value="not html"):
            assert ci.fetch_index_versions("torch", "cu121") == {}

    def test_timeout_param_passed(self):
        with patch.object(
            ci, "_fetch_simple_index_sync", return_value="<a href='x.whl'>x</a>"
        ) as mock_fetch:
            ci.fetch_index_versions("torch", "cu121", timeout=3.5)
        mock_fetch.assert_called_once_with("torch", "cu121", 3.5)


class TestRestrictToIndexVersions:
    def test_non_family_unchanged(self):
        versions = ["1.0.0", "1.1.0"]
        assert ci.restrict_to_index_versions(versions, "flask", "cu121") == versions

    def test_family_restricted(self):
        with patch.object(
            ci,
            "fetch_index_versions",
            return_value={"2.5.1": "2.5.1+cu121", "2.1.0": "2.1.0+cu121"},
        ):
            result = ci.restrict_to_index_versions(
                ["2.9.1", "2.5.1", "2.1.0", "1.13.1"], "torch", "cu121"
            )
        assert result == ["2.5.1", "2.1.0"]

    def test_family_no_match_keeps_original(self):
        with patch.object(ci, "fetch_index_versions", return_value={"3.0.0": "3.0.0+cu121"}):
            result = ci.restrict_to_index_versions(["2.9.1"], "torch", "cu121")
        assert result == ["2.9.1"]

    def test_family_fetch_failure_keeps_original(self):
        with patch.object(ci, "fetch_index_versions", return_value={}):
            result = ci.restrict_to_index_versions(["2.9.1", "2.5.1"], "torch", "cu121")
        assert result == ["2.9.1", "2.5.1"]


class TestFetchAsync:
    @pytest.mark.asyncio
    async def test_async_wraps_sync(self):
        with patch.object(
            ci,
            "fetch_index_versions",
            return_value={"2.1.0": "2.1.0+cu121"},
        ) as mock_sync:
            result = await ci.fetch_index_versions_async("torch", "cu121")
        assert result == {"2.1.0": "2.1.0+cu121"}
        mock_sync.assert_called_once()
