import pytest
from fastapi import HTTPException

from backend.data_sources.utils import safe_data_source_call


class TestSafeDataSourceCall:
    @pytest.mark.asyncio
    async def test_successful_call(self):
        async def good():
            return "result"

        result = await safe_data_source_call(good())
        assert result == "result"

    @pytest.mark.asyncio
    async def test_re_raises_http_exception(self):
        async def raises_http():
            raise HTTPException(status_code=404, detail="Not found")

        with pytest.raises(HTTPException) as exc:
            await safe_data_source_call(raises_http())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wraps_generic_exception(self):
        async def raises_generic():
            raise ValueError("Something broke")

        with pytest.raises(HTTPException) as exc:
            await safe_data_source_call(raises_generic(), "Custom error")
        assert exc.value.status_code == 500
        assert "Custom error" in exc.value.detail

    @pytest.mark.asyncio
    async def test_default_error_message(self):
        async def raises_generic():
            raise RuntimeError("fail")

        with pytest.raises(HTTPException) as exc:
            await safe_data_source_call(raises_generic())
        assert "Data source operation failed" in exc.value.detail
