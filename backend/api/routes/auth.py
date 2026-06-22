# backend/api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Dict
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from backend.api.auth import (
    AuthService, 
    get_current_user,
    get_current_active_user,
    UserCreate,
    UserLogin,
    APIKeyCreate,
    Token,
    login_for_access_token,
    OAuth2PasswordRequestForm
)
from backend.database.models import User
from backend.api.dependencies import limiter

router = APIRouter()

# Response models
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    scopes: List[str] = []

class APIKeyResponse(BaseModel):
    id: int
    name: str
    key: str  # Only returned on creation
    description: Optional[str]
    scopes: List[str]
    created_at: datetime
    expires_at: Optional[datetime]

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

# Routes
@router.post("/register", response_model=UserResponse)
@limiter.limit("5/hour")
async def register(request: Request, user_data: UserCreate) -> UserResponse:
    """Register a new user"""
    user = await AuthService.register_user(user_data)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        scopes=user.scopes or []
    )

@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, user_data: UserLogin) -> Token:
    """Login and receive access tokens"""
    return await AuthService.login(user_data)

@router.post("/token", response_model=Token)
@limiter.limit("10/minute")
async def token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """OAuth2 compatible token endpoint"""
    return await login_for_access_token(form_data)

@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
async def refresh_token(request: Request, refresh_token: str) -> Token:
    """Refresh access token using refresh token"""
    return await AuthService.refresh_token(refresh_token)

@router.post("/logout")
@limiter.limit("30/minute")
async def logout(request: Request, current_user: User = Depends(get_current_user)) -> dict:
    """Logout user (client should discard tokens)"""
    # In a more complex system, you might want to blacklist the token
    return {"message": "Successfully logged out"}

@router.get("/profile", response_model=UserResponse)
@limiter.limit("60/minute")
async def get_profile(request: Request, current_user: User = Depends(get_current_user)) -> UserResponse:
    """Get current user profile"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        scopes=current_user.scopes or []
    )

@router.put("/profile", response_model=UserResponse)
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    profile_data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user)
) -> UserResponse:
    """Update user profile"""
    from backend.database.models import db_session
    
    with db_session() as db:
        user = db.query(User).filter(User.id == current_user.id).first()
        
        if profile_data.full_name is not None:
            user.full_name = profile_data.full_name
        
        if profile_data.email is not None:
            # Check if email is already taken
            existing = db.query(User).filter(
                User.email == profile_data.email,
                User.id != current_user.id
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
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
            scopes=user.scopes or []
        )

@router.post("/change-password")
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user)
) -> dict:
    """Change user password"""
    from backend.database.models import db_session
    from backend.api.auth import verify_password, get_password_hash
    
    with db_session() as db:
        user = db.query(User).filter(User.id == current_user.id).first()
        
        # Verify current password
        if not verify_password(password_data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        # Update password
        user.hashed_password = get_password_hash(password_data.new_password)
        db.commit()
        
        return {"message": "Password changed successfully"}

@router.get("/api-keys", response_model=List[APIKeyResponse])
@limiter.limit("30/minute")
async def get_api_keys(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> List[APIKeyResponse]:
    """Get user's API keys"""
    from backend.database.models import db_session, APIKey
    
    with db_session() as db:
        keys = db.query(APIKey).filter(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True
        ).all()
        
        return [
            APIKeyResponse(
                id=key.id,
                name=key.name,
                key="*" * 20 + key.key[-8:],  # Mask key, show only last 8 chars
                description=key.description,
                scopes=key.scopes or [],
                created_at=key.created_at,
                expires_at=key.expires_at
            )
            for key in keys
        ]

@router.post("/api-keys", response_model=APIKeyResponse)
@limiter.limit("10/day")
async def create_api_key(
    request: Request,
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user)
) -> APIKeyResponse:
    """Create a new API key"""
    api_key = await AuthService.create_api_key(current_user, key_data)
    
    # Return the full key only on creation
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=api_key.key,  # Full key returned only once
        description=api_key.description,
        scopes=api_key.scopes or [],
        created_at=api_key.created_at,
        expires_at=api_key.expires_at
    )

@router.delete("/api-keys/{key_id}")
@limiter.limit("30/minute")
async def revoke_api_key(
    request: Request,
    key_id: int,
    current_user: User = Depends(get_current_user)
) -> dict:
    """Revoke an API key"""
    success = await AuthService.revoke_api_key(current_user, key_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return {"message": "API key revoked successfully"}

# Optional: Add these utility endpoints

@router.get("/verify")
@limiter.limit("60/minute")
async def verify_token(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> dict:
    """Verify if current token is valid"""
    return {
        "valid": True,
        "username": current_user.username,
        "user_id": current_user.id
    }

@router.post("/check-username")
@limiter.limit("30/minute")
async def check_username_availability(request: Request, username: str) -> dict:
    """Check if username is available"""
    from backend.database.models import db_session
    
    with db_session() as db:
        exists = db.query(User).filter(User.username == username).first() is not None
        
    return {"available": not exists}

@router.post("/check-email")
@limiter.limit("30/minute")
async def check_email_availability(request: Request, email: str) -> dict:
    """Check if email is available"""
    from backend.database.models import db_session
    
    with db_session() as db:
        exists = db.query(User).filter(User.email == email).first() is not None
        
    return {"available": not exists}