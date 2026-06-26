import sys
import os
import uvicorn
from backend.api.main import app

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('UDR_PORT', '8199'))
    host = os.environ.get('UDR_HOST', '127.0.0.1')
    log_level = os.environ.get('UDR_LOG_LEVEL', 'info')

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
