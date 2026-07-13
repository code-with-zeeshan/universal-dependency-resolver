"""Module docstring."""

# backend/api/routes/auth.py
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.api.auth import (
    APIKeyCreate,
    AuthService,
    OAuth2PasswordRequestForm,
    Token,
    UserCreate,
    UserLogin,
    get_current_user,
    login_for_access_token,
)
from backend.api.dependencies import limiter
from backend.orchestrator.db_service import User

router = APIRouter()


# Response models
class UserResponse(BaseModel):
    """User Response functionality."""

    id: int
    username: str
    email: str
    full_name: str | None
    is_active: bool
    scopes: list[str] = []


class APIKeyResponse(BaseModel):
    """Api Key Response functionality."""

    id: int
    name: str
    key: str  # Only returned on creation
    description: str | None
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None


class ProfileUpdateRequest(BaseModel):
    """Profile Update Request functionality."""

    full_name: str | None = None
    email: str | None = None


class PasswordChangeRequest(BaseModel):
    """Password Change Request functionality."""

    current_password: str
    new_password: str


# Routes
@router.post("/register", response_model=UserResponse)
@limiter.limit("5/hour")
async def register(request: Request, user_data: UserCreate) -> UserResponse:
    """Register a new user."""
    user: dict = await AuthService.register_user(user_data)
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        full_name=user["full_name"],
        is_active=user["is_active"],
        scopes=user.get("scopes", []),
    )


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, user_data: UserLogin) -> Token:
    """Login and receive access tokens."""
    return await AuthService.login(user_data)


@router.post("/token", response_model=Token)
@limiter.limit("10/minute")
async def token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """OAuth2 compatible token endpoint."""
    return await login_for_access_token(form_data)


@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
async def refresh_token(request: Request, refresh_token: str) -> Token:
    """Refresh access token using refresh token."""
    return await AuthService.refresh_token(refresh_token)


@router.post("/logout")
@limiter.limit("30/minute")
async def logout(request: Request, current_user: User = Depends(get_current_user)) -> dict:
    """Logout user (client should discard tokens)."""
    # In a more complex system, you might want to blacklist the token
    return {"message": "Successfully logged out"}


@router.get("/profile", response_model=UserResponse)
@limiter.limit("60/minute")
async def get_profile(
    request: Request, current_user: User = Depends(get_current_user)
) -> UserResponse:
    """Get current user profile."""
    u: Any = current_user
    return UserResponse(
        id=u.id,
        username=u.username,
        email=u.email,
        full_name=u.full_name,
        is_active=u.is_active,
        scopes=u.scopes or [],
    )


@router.put("/profile", response_model=UserResponse)
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    profile_data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Update user profile."""
    from backend.orchestrator.db_service import db_session

    with db_session() as db:
        user = db.query(User).filter(User.id == current_user.id).first()

        if profile_data.full_name is not None:
            user.full_name = profile_data.full_name

        if profile_data.email is not None:
            # Check if email is already taken
            existing = (
                db.query(User)
                .filter(User.email == profile_data.email, User.id != current_user.id)
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use",
                )

            user.email = profile_data.email

        db.commit()
        db.refresh(user)

        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            scopes=user.scopes or [],
        )


@router.post("/change-password")
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Change user password."""
    from backend.api.auth import get_password_hash, verify_password
    from backend.orchestrator.db_service import db_session

    with db_session() as db:
        user = db.query(User).filter(User.id == current_user.id).first()

        # Verify current password
        if not verify_password(password_data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Update password
        user.hashed_password = get_password_hash(password_data.new_password)
        db.commit()

        return {"message": "Password changed successfully"}


@router.get("/api-keys", response_model=list[APIKeyResponse])
@limiter.limit("30/minute")
async def get_api_keys(
    request: Request, current_user: User = Depends(get_current_user)
) -> list[APIKeyResponse]:
    """Get user's API keys."""
    from backend.orchestrator.db_service import APIKey, db_session

    with db_session() as db:
        keys = db.query(APIKey).filter(APIKey.user_id == current_user.id, APIKey.is_active).all()

        return [
            APIKeyResponse(
                id=key.id,
                name=key.name,
                key="*" * 20 + key.key[-8:],  # Mask key, show only last 8 chars
                description=key.description,
                scopes=key.scopes or [],
                created_at=key.created_at,
                expires_at=key.expires_at,
            )
            for key in keys
        ]


@router.post("/api-keys", response_model=APIKeyResponse)
@limiter.limit("10/day")
async def create_api_key(
    request: Request,
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
) -> APIKeyResponse:
    """Create a new API key."""
    api_key, raw_key = await AuthService.create_api_key(current_user, key_data)

    # Return the full raw key only on creation (stored as bcrypt hash)
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        description=api_key.description,
        scopes=api_key.scopes or [],
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.delete("/api-keys/{key_id}")
@limiter.limit("30/minute")
async def revoke_api_key(
    request: Request, key_id: int, current_user: User = Depends(get_current_user)
) -> dict:
    """Revoke an API key."""
    success = await AuthService.revoke_api_key(current_user, key_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    return {"message": "API key revoked successfully"}


# Optional: Add these utility endpoints


@router.get("/verify")
@limiter.limit("60/minute")
async def verify_token(request: Request, current_user: User = Depends(get_current_user)) -> dict:
    """Verify if current token is valid."""
    return {
        "valid": True,
        "username": current_user.username,
        "user_id": current_user.id,
    }


@router.post("/check-username")
@limiter.limit("30/minute")
async def check_username_availability(request: Request, email_or_username: str) -> dict:
    """Check if a username OR email is available.

    Uses a single generic endpoint to prevent username/email enumeration.
    Always returns a boolean — never reveals which field matched.
    """
    from backend.orchestrator.db_service import db_session

    with db_session() as db:
        exists = (
            db.query(User)
            .filter((User.username == email_or_username) | (User.email == email_or_username))
            .first()
            is not None
        )

    return {"available": not exists}


# ---------------------------------------------------------------------------
# Lock-file signing key management (C6)
# ---------------------------------------------------------------------------


@router.get("/signing-key")
@limiter.limit("30/minute")
async def show_signing_key(
    request: Request,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Show the current Ed25519 public signing key.

    Mirrors ``udr auth show-key``.
    """
    import base64
    import hashlib
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    signing_dir = Path.home() / ".config" / "udr"
    key_path = signing_dir / "signing.key"
    if not key_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="No signing key found. Generate one with POST /auth/gen-key",
        )
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(private_key, ed25519.Ed25519PrivateKey):
        raise HTTPException(status_code=500, detail="Invalid signing key file")
    pub_bytes = private_key.public_key().public_bytes_raw()
    fingerprint = hashlib.sha256(pub_bytes).hexdigest()
    return {
        "status": "success",
        "algorithm": "Ed25519",
        "public_key_base64": base64.b64encode(pub_bytes).decode(),
        "fingerprint": fingerprint,
        "key_directory": str(signing_dir),
    }


class GenKeyResponse(BaseModel):
    status: str
    message: str
    public_key_base64: str
    fingerprint: str
    key_directory: str


@router.post("/gen-key", response_model=GenKeyResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/day")
async def gen_signing_key(
    request: Request,
    current_user=Depends(get_current_user),
) -> GenKeyResponse:
    """Generate a new Ed25519 signing key for lock file signing.

    Mirrors ``udr auth gen-key``.
    """
    import base64
    import hashlib
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes_raw()

    signing_dir = Path.home() / ".config" / "udr"
    signing_dir.mkdir(parents=True, exist_ok=True)
    key_path = signing_dir / "signing.key"
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)
    key_path.chmod(0o600)
    pub_path = signing_dir / "signing.pub"
    pub_path.write_text(base64.b64encode(pub_bytes).decode() + "\n")
    pub_path.chmod(0o644)

    fingerprint = hashlib.sha256(pub_bytes).hexdigest()
    return GenKeyResponse(
        status="success",
        message="Ed25519 signing key generated",
        public_key_base64=base64.b64encode(pub_bytes).decode(),
        fingerprint=fingerprint,
        key_directory=str(signing_dir),
    )
