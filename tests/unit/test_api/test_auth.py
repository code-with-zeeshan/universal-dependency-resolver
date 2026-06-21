"""
Tests for backend.api.auth module
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from jose import jwt

from backend.api.auth import (
    AuthService,
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    get_