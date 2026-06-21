# backend/api/auth.py
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
import secrets
import logging
from typing import Optional
from datetime import datetime

from backend.settings import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    API_KEY_HEADER,
    ENABLE_API_KEY_AUTH,
    FEATURES
)
from backend.database.models import User, APIKey, db_session

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


# Pydantic models
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = Field(default=ACCESS_TOKEN_EXPIRE_MINUTES * 60)


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    scopes: List[str] = []


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


# Authentication functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def generate_api_key() -> str:
    """Generate a secure API key"""
    return f"udr_{secrets.token_urlsafe(32)}"


async def get_current_user_from_token(token: str) -> Optional[User]:
    """Extract and validate user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if username is None or token_type != "access":
            raise credentials_exception
        
        token_data = TokenData(username=username, scopes=payload.get("scopes", []))
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    with db_session() as db:
        user = db.query(User).filter(User.username == token_data.username).first()
        if user is None:
            raise credentials_exception
        
        return user


async def get_current_user_from_api_key(api_key: str) -> Optional[User]:
    """Validate API key and return associated user"""
    if not api_key:
        return None
    
    with db_session() as db:
        key_record = db.query(APIKey).filter(
            APIKey.key == api_key,
            APIKey.is_active == True
        ).first()
        
        if not key_record:
            return None
        
        # Check expiration
        if key_record.expires_at and key_record.expires_at < datetime.utcnow():
            return None
        
        # Update last used timestamp
        key_record.last_used_at = datetime.utcnow()
        key_record.usage_count += 1
        db.commit()
        
        return key_record.user


# Dependency functions
async def get_current_user(
    request: Request,
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header)
) -> User:
    """Get current user from either JWT token or API key"""
    if not FEATURES.get('ENABLE_AUTH', False):
        # Return a mock user if auth is disabled
        return User(id=1, username="anonymous", email="anonymous@example.com")
    
    user = None
    
    # Try JWT token first
    if bearer_token and bearer_token.credentials:
        try:
            user = await get_current_user_from_token(bearer_token.credentials)
        except HTTPException:
            pass
    
    # Try API key if enabled and no user from JWT
    if not user and ENABLE_API_KEY_AUTH and api_key:
        user = await get_current_user_from_api_key(api_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure the current user is active"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_scopes(*required_scopes: str):
    """Dependency to require specific scopes"""
    async def scope_checker(current_user: User = Depends(get_current_user)):
        if not FEATURES.get('ENABLE_AUTH', False):
            return current_user
        
        user_scopes = set(current_user.scopes or [])
        required = set(required_scopes)
        
        if not required.issubset(user_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions. Required scopes: {', '.join(required_scopes)}"
            )
        
        return current_user
    
    return scope_checker


# Authentication service class
class AuthService:
    """Service for authentication operations"""
    
    @staticmethod
    async def register_user(user_data: UserCreate) -> User:
        """Register a new user"""
        with db_session() as db:
            # Check if user exists
            if db.query(User).filter(
                (User.username == user_data.username) | 
                (User.email == user_data.email)
            ).first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username or email already registered"
                )
            
            # Create new user
            hashed_password = get_password_hash(user_data.password)
            user = User(
                username=user_data.username,
                email=user_data.email,
                hashed_password=hashed_password,
                full_name=user_data.full_name,
                is_active=True,
                created_at=datetime.utcnow()
            )
            
            db.add(user)
            db.commit()
            db.refresh(user)
            
            logger.info(f"New user registered: {user.username}")
            return user
    
    @staticmethod
    async def authenticate_user(username: str, password: str) -> Optional[User]:
        """Authenticate a user with username and password"""
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            
            if not user or not verify_password(password, user.hashed_password):
                return None
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.commit()
            
            return user
    
    @staticmethod
    async def login(user_data: UserLogin) -> Token:
        """Login user and return tokens"""
        user = await AuthService.authenticate_user(user_data.username, user_data.password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create tokens
        access_token_data = {
            "sub": user.username,
            "user_id": user.id,
            "scopes": user.scopes or []
        }
        
        access_token = create_access_token(access_token_data)
        refresh_token = create_refresh_token({"sub": user.username})
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    
    @staticmethod
    async def refresh_token(refresh_token: str) -> Token:
        """Refresh access token using refresh token"""
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            token_type: str = payload.get("type")
            
            if username is None or token_type != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token"
                )
            
            # Get user
            with db_session() as db:
                user = db.query(User).filter(User.username == username).first()
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found"
                    )
                
                # Create new access token
                access_token_data = {
                    "sub": user.username,
                    "user_id": user.id,
                    "scopes": user.scopes or []
                }
                
                access_token = create_access_token(access_token_data)
                
                return Token(
                    access_token=access_token,
                    token_type="bearer",
                    expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
                )
                
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
    
    @staticmethod
    async def create_api_key(user: User, key_data: APIKeyCreate) -> APIKey:
        """Create a new API key for a user"""
        with db_session() as db:
            api_key = APIKey(
                key=generate_api_key(),
                name=key_data.name,
                description=key_data.description,
                user_id=user.id,
                scopes=key_data.scopes,
                expires_at=key_data.expires_at,
                created_at=datetime.utcnow(),
                is_active=True
            )
            
            db.add(api_key)
            db.commit()
            db.refresh(api_key)
            
            logger.info(f"API key created for user {user.username}: {api_key.name}")
            return api_key
    
    @staticmethod
    async def revoke_api_key(user: User, key_id: int) -> bool:
        """Revoke an API key"""
        with db_session() as db:
            api_key = db.query(APIKey).filter(
                APIKey.id == key_id,
                APIKey.user_id == user.id
            ).first()
            
            if not api_key:
                return False
            
            api_key.is_active = False
            api_key.revoked_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"API key revoked: {api_key.name}")
            return True


# Optional: OAuth2 password flow for testing
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """OAuth2 compatible token endpoint"""
    user = await AuthService.authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_data = {
        "sub": user.username,
        "user_id": user.id,
        "scopes": form_data.scopes
    }
    
    access_token = create_access_token(access_token_data)
    
    return {"access_token": access_token, "token_type": "bearer"}