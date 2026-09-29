"""ChemSentry Security — JWT auth, RBAC, password hashing (M4).

Handles authentication (JWT token generation/validation) and authorization
(role-based access control for sign-off workflow).
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from api.models import UserInfo, UserRole

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration and Key Management
# ============================================================================

JWT_SECRET_KEY_ENV_VAR = "JWT_SECRET_KEY"
ENVIRONMENT_ENV_VAR = "CHEMSENTRY_ENV"
MIN_JWT_KEY_BYTES = 32

FORBIDDEN_PRODUCTION_KEYS = {
    "dev-key-change-in-production",
    "replace-with-a-random-string-per-environment",
}

_DEV_JWT_KEY_FILE = Path(__file__).resolve().parent.parent / ".chemsentry_jwt.key"
_CACHED_JWT_SECRET_KEY: Optional[str] = None


class JWTKeyError(RuntimeError):
    """Raised when the JWT secret key is missing, too short, or set to a placeholder."""


def _is_production() -> bool:
    """Check whether the application is running in production mode.

    Problem this solves: Determines whether strict cryptographic and security
    guarantees must be enforced instead of local development conveniences.
    Why this technique: Reuses the CHEMSENTRY_ENV convention established in ADR 0004
    (api/crypto.py) so operational environments share a single source of truth.
    """
    return os.getenv(ENVIRONMENT_ENV_VAR, "development").strip().lower() == "production"


def _load_or_create_dev_jwt_key() -> str:
    """Return the persisted per-machine dev JWT secret key, generating one on first use.

    Problem this solves: In development, omitting JWT_SECRET_KEY previously defaulted
    to a public static string, allowing anyone reading the repository to forge ADMIN
    tokens. A purely ephemeral in-memory random key would invalidate login sessions
    on every server reload.
    Why this technique: Persisting a cryptographically secure random 64-hex-char
    (32-byte) key to a local gitignored file mirrors api/crypto.py's .chemsentry_data.key
    pattern, preventing repository-wide token forgery while keeping developer logins stable.
    """
    if _DEV_JWT_KEY_FILE.exists():
        return _DEV_JWT_KEY_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    _DEV_JWT_KEY_FILE.write_text(key, encoding="utf-8")
    try:
        _DEV_JWT_KEY_FILE.chmod(0o600)
    except OSError:
        pass
    logger.warning(
        "%s is not set -- generated a random local dev key at %s (gitignored). "
        "Set %s explicitly (at least %d bytes) for any shared or deployed environment.",
        JWT_SECRET_KEY_ENV_VAR,
        _DEV_JWT_KEY_FILE,
        JWT_SECRET_KEY_ENV_VAR,
        MIN_JWT_KEY_BYTES,
    )
    return key


def resolve_jwt_secret_key() -> str:
    """Resolve and validate the JWT signing key according to environment policy.

    Problem this solves: Prevents deployment with default/placeholder/short secret keys
    that would compromise token authenticity (forged ADMIN tokens).
    Why this technique: Fails closed in production on missing, placeholder, or <32 byte keys;
    enforces 32-byte minimum in development to satisfy RFC 7518 HS256 requirements.
    """
    raw = os.getenv(JWT_SECRET_KEY_ENV_VAR, "").strip()
    if _is_production():
        if not raw:
            raise JWTKeyError(
                f"{JWT_SECRET_KEY_ENV_VAR} must be set when {ENVIRONMENT_ENV_VAR}=production."
            )
        if raw in FORBIDDEN_PRODUCTION_KEYS:
            raise JWTKeyError(
                f"{JWT_SECRET_KEY_ENV_VAR} cannot use placeholder value '{raw}' in production."
            )
        if len(raw.encode("utf-8")) < MIN_JWT_KEY_BYTES:
            raise JWTKeyError(
                f"{JWT_SECRET_KEY_ENV_VAR} must be at least {MIN_JWT_KEY_BYTES} bytes in production "
                f"(got {len(raw.encode('utf-8'))})."
            )
        return raw

    # Development mode
    if raw:
        if len(raw.encode("utf-8")) < MIN_JWT_KEY_BYTES:
            raise JWTKeyError(
                f"{JWT_SECRET_KEY_ENV_VAR} must be at least {MIN_JWT_KEY_BYTES} bytes "
                f"(got {len(raw.encode('utf-8'))})."
            )
        return raw

    return _load_or_create_dev_jwt_key()


def get_jwt_secret_key() -> str:
    """Retrieve the cached active JWT secret key, resolving it if uninitialized.

    Problem this solves: Provides consistent, fast key access without re-evaluating
    filesystem files on every request while supporting cache invalidation in tests.
    Why this technique: Memoizes key in module state with reset hook for test isolation.
    """
    global _CACHED_JWT_SECRET_KEY, JWT_SECRET_KEY
    if _CACHED_JWT_SECRET_KEY is None:
        _CACHED_JWT_SECRET_KEY = resolve_jwt_secret_key()
        JWT_SECRET_KEY = _CACHED_JWT_SECRET_KEY
    return _CACHED_JWT_SECRET_KEY


def reset_jwt_key_cache() -> None:
    """Reset cached JWT secret key so environment changes take effect (for tests).

    Problem this solves: Allows unit tests to verify behavior under different
    environment variables without subprocess overhead.
    Why this technique: Explicit cache clearing pattern identical to api.crypto.reset_key_cache().
    """
    global _CACHED_JWT_SECRET_KEY, JWT_SECRET_KEY
    _CACHED_JWT_SECRET_KEY = None
    JWT_SECRET_KEY = None


def validate_jwt_key_configuration() -> str:
    """Verify that the JWT key configuration satisfies security rules.

    Problem this solves: Enables startup-time validation to catch configuration errors
    immediately rather than upon first token generation or API request.
    Why this technique: Eager validation prevents operational surprises post-boot.
    """
    return resolve_jwt_secret_key()


JWT_SECRET_KEY = get_jwt_secret_key()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


# ============================================================================
# Token Management
# ============================================================================


def create_access_token(
    user_id: str,
    username: str,
    role: UserRole,
    expires_delta: Optional[timedelta] = None,
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
        "iat": now,
    }

    token = jwt.encode(payload, get_jwt_secret_key(), algorithm=JWT_ALGORITHM)
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
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        username = payload.get("username")
        role_str = payload.get("role")

        if not all([user_id, username, role_str]):
            raise ValueError("Missing required claims")

        role = UserRole(role_str)
        return UserInfo(user_id=user_id, username=username, role=role)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


# ============================================================================
# Dependency Injection for FastAPI Routes
# ============================================================================

security = HTTPBearer()


async def get_current_user(credentials=Depends(security)) -> UserInfo:
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
        role_hierarchy = {UserRole.VIEWER: 1, UserRole.ANALYST: 2, UserRole.ADMIN: 3}
        if role_hierarchy[user.role] < role_hierarchy[required_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role.value} role",
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
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hash.

    Note: Truncates input to 72 bytes to match bcrypt's limit.
    """
    plain_bytes = plain.encode("utf-8")[:72]
    return bcrypt.checkpw(plain_bytes, hashed.encode("utf-8"))


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
                "role": UserRole.VIEWER,
            },
            "analyst_user": {
                "user_id": "user_002",
                "password": hash_password("analyst123"),
                "role": UserRole.ANALYST,
            },
            "admin_user": {
                "user_id": "user_003",
                "password": hash_password("admin123"),
                "role": UserRole.ADMIN,
            },
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
