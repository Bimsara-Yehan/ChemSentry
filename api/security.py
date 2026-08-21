"""ChemSentry Security — JWT auth, RBAC, password hashing (M4).

Handles authentication (JWT token generation/validation) and authorization
(role-based access control for sign-off workflow).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from api.models import UserRole, UserInfo


# ============================================================================
# Configuration
# ============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


# ============================================================================
# Token Management
# ============================================================================

def create_access_token(
    user_id: str,
    username: str,
    role: UserRole,
    expires_delta: Optional[timedelta] = None
) -> tuple[str, int]:
    """Create a JWT token for a user.
    
    Args:
        user_id: Unique user identifier
        username: Username
        role: UserRole (VIEWER, ANALYST, ADMIN)
        expires_delta: Custom expiration time (default: JWT_EXPIRATION_HOURS)
    
    Returns:
        (token_string, expires_in_seconds)
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=JWT_EXPIRATION_HOURS)
    
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role.value,
        "exp": expire,
        "iat": now
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    expires_in = int(expires_delta.total_seconds())
    
    return token, expires_in


def verify_token(token: str) -> UserInfo:
    """Verify JWT token and extract user info.
    
    Args:
        token: JWT token string
    
    Returns:
        UserInfo with user_id, username, role
    
    Raises:
        HTTPException (401) if token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        username = payload.get("username")
        role_str = payload.get("role")
        
        if not all([user_id, username, role_str]):
            raise ValueError("Missing required claims")
        
        role = UserRole(role_str)
        return UserInfo(user_id=user_id, username=username, role=role)
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# ============================================================================
# Dependency Injection for FastAPI Routes
# ============================================================================

security = HTTPBearer()


async def get_current_user(credentials = Depends(security)) -> UserInfo:
    """FastAPI dependency: Extract and verify user from Bearer token.
    
    HTTPBearer returns an object with a 'credentials' attribute.
    
    Usage:
        @app.get("/protected")
        def protected_route(user: UserInfo = Depends(get_current_user)):
            return {"user": user}
    """
    token = credentials.credentials
    return verify_token(token)


def require_role(required_role: UserRole):
    """FastAPI dependency factory: Require minimum role.
    
    Usage:
        @app.post("/admin-only")
        def admin_only(user: UserInfo = Depends(require_role(UserRole.ADMIN))):
            return {"admin": user}
    """
    def role_checker(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        # Role hierarchy: VIEWER < ANALYST < ADMIN
        role_hierarchy = {
            UserRole.VIEWER: 1,
            UserRole.ANALYST: 2,
            UserRole.ADMIN: 3
        }
        if role_hierarchy[user.role] < role_hierarchy[required_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role.value} role"
            )
        return user
    
    return role_checker


# ============================================================================
# Password Hashing (for future user DB)
# ============================================================================

def hash_password(password: str) -> str:
    """Hash a password for storage.
    
    Note: bcrypt has a 72-byte limit on passwords. Longer passwords are truncated.
    """
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hash.
    
    Note: Truncates input to 72 bytes to match bcrypt's limit.
    """
    plain_bytes = plain.encode('utf-8')[:72]
    return bcrypt.checkpw(plain_bytes, hashed.encode('utf-8'))


# ============================================================================
# Demo Users (for local testing)
# ============================================================================

# Demo users (passwords hashed on first access to avoid module import issues)
_DEMO_USERS_CACHE = None


def _get_demo_users():
    """Lazy-load and hash demo user passwords."""
    global _DEMO_USERS_CACHE
    if _DEMO_USERS_CACHE is None:
        _DEMO_USERS_CACHE = {
            "viewer_user": {
                "user_id": "user_001",
                "password": hash_password("viewer123"),
                "role": UserRole.VIEWER
            },
            "analyst_user": {
                "user_id": "user_002",
                "password": hash_password("analyst123"),
                "role": UserRole.ANALYST
            },
            "admin_user": {
                "user_id": "user_003",
                "password": hash_password("admin123"),
                "role": UserRole.ADMIN
            }
        }
    return _DEMO_USERS_CACHE


def authenticate_user(username: str, password: str) -> Optional[tuple[str, UserRole]]:
    """Authenticate user by username/password (demo only).
    
    In production, this would query a user database.
    
    Returns:
        (user_id, role) if authenticated, None otherwise
    """
    demo_users = _get_demo_users()
    if username not in demo_users:
        return None
    
    user = demo_users[username]
    if not verify_password(password, user["password"]):
        return None
    
    return user["user_id"], user["role"]
