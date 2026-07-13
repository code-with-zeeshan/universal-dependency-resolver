"""Run the UDR API server."""

import sys

import bcrypt  # noqa: F401
import email_validator  # noqa: F401

# PyInstaller hidden imports: these modules must be explicitly imported
# because jose/__init__.py doesn't import jose.jwt, and passlib/bcrypt
# are dynamically loaded by passlib.
import jose
import jose.jwt  # noqa: F401
import passlib.handlers.bcrypt  # noqa: F401
import uvicorn

from backend.api.main import app
from backend.settings import UDR_HOST, UDR_LOG_LEVEL, UDR_PORT

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else UDR_PORT
    host = sys.argv[2] if len(sys.argv) > 2 else UDR_HOST
    log_level = UDR_LOG_LEVEL

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
