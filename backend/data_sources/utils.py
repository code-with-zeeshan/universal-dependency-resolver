"""Module docstring."""

from typing import Any

from fastapi import HTTPException


async def safe_data_source_call(coro, error_msg: str = "Data source operation failed") -> Any:
    """Safely execute an async data source operation with standard error handling.
    Re-raises HTTPException as-is, wraps other exceptions in HTTPException with 500 status.
    """
    try:
        return await coro
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{error_msg}: {e!s}")
