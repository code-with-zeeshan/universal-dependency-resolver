import sys
import os

# PyInstaller hidden imports: these modules must be explicitly imported
# because jose/__init__.py doesn't import jose.jwt, and passlib/bcrypt
# are dynamically loaded by passlib.
import jose  # noqa: F401
import jose.jwt  # noqa: F401
import passlib.handlers.bcrypt  # noqa: F401
import bcrypt  # noqa: F401

import uvicorn
from backend.api.main import app

if __name__ == "__main__":
    port = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else int(os.environ.get("UDR_PORT", "8199"))
    )
    host = os.environ.get("UDR_HOST", "127.0.0.1")
    log_level = os.environ.get("UDR_LOG_LEVEL", "info")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
