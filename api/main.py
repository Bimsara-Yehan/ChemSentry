"""ChemSentry API Gateway — FastAPI entrypoint (M4).

Provides authentication (JWT login/token), health checks, and integration points
for Agent A (retrieval), Agent B (safety analysis), and Agent C (environment).

Auth flow:
  1. Client POSTs /auth/login with username/password
  2. API returns JWT token
  3. Client includes token in Authorization: Bearer <token> header
  4. Protected routes verify token via get_current_user dependency
  5. RBAC enforces role-based access (viewer < analyst < admin)
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from api.models import (
    TokenResponse, UserLogin, UserInfo, HealthCheck,
    QueryRequest, QueryResponse, UserRole
)
from api.security import (
    create_access_token, get_current_user, authenticate_user, require_role
)
from api.database import get_db, init_db, check_db_health, get_db_schema_info
from sqlalchemy.orm import Session

# Create FastAPI app
app = FastAPI(
    title="ChemSentry API",
    description="Chemical safety retrieval and reconciliation",
    version="0.1.0"
)

# Add CORS middleware (allow frontend to call from different origin during dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on app startup."""
    init_db()
    print("✅ Database initialized")


# ============================================================================
# Authentication Routes
# ============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    """Login with username/password, receive JWT token.
    
    Demo users (for testing):
    - viewer_user / viewer123 (VIEWER role)
    - analyst_user / analyst123 (ANALYST role)
    - admin_user / admin123 (ADMIN role)
    
    Returns:
        JWT token valid for 24 hours
    
    Raises:
        401: Invalid credentials
    """
    result = authenticate_user(credentials.username, credentials.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    user_id, role = result
    token, expires_in = create_access_token(user_id, credentials.username, role)
    
    return TokenResponse(access_token=token, expires_in=expires_in)


# ============================================================================
# Health & Status Routes
# ============================================================================

@app.get("/health", response_model=HealthCheck)
async def health_check(db: Session = Depends(get_db)):
    """Health check — verify API, database, and MQTT broker status.
    
    Returns:
        status: "ok", "degraded", or "error"
        database: "ok" or error message
        mqtt_broker: "ok" or error message (placeholder)
    """
    db_status = check_db_health()
    
    # TODO: Add MQTT broker connectivity check
    mqtt_status = "ok"  # Placeholder
    
    overall_status = "ok" if db_status == "ok" else "degraded"
    
    return HealthCheck(
        status=overall_status,
        database=db_status,
        mqtt_broker=mqtt_status,
        version="0.1.0"
    )


@app.get("/debug/schema")
async def debug_schema(user: UserInfo = Depends(get_current_user)):
    """Debug endpoint — show database schema (admin only).
    
    Requires ADMIN role.
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return get_db_schema_info()


# ============================================================================
# Protected Routes (require authentication)
# ============================================================================

@app.get("/me")
async def get_current_user_info(user: UserInfo = Depends(get_current_user)):
    """Get current user info from JWT token.
    
    Returns:
        {user_id, username, role}
    """
    return user


@app.post("/query", response_model=QueryResponse)
async def query_chemical(
    request: QueryRequest,
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Query a chemical for safety info and thresholds.
    
    This is a placeholder — actual implementation will:
    1. Call Agent A (retrieval) to fetch SDS documents
    2. Call Agent B (safety analysis) to reconcile evidence
    3. Return thresholds and safety state
    
    Requires: ANALYST or ADMIN role
    """
    if user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst role required for queries"
        )
    
    # TODO: Implement actual query logic
    # This is scaffolding for the API contract
    
    return QueryResponse(
        query_id="query_placeholder_001",
        query=request,
        evidence={
            "query_chemical": request.chemical_name,
            "retrieved_docs": [],
            "thresholds": [],
            "conflicts": [],
            "final_safety_state": "UNKNOWN"
        }
    )


@app.post("/admin/sign-off")
async def sign_off_alert(
    alert_id: str,
    approved: bool,
    user: UserInfo = Depends(require_role(UserRole.ADMIN))
):
    """Sign off on an alert (admin only).
    
    Requires: ADMIN role
    
    Returns:
        Confirmation of sign-off
    """
    # TODO: Implement sign-off logic
    # This should record the decision in the database
    
    return {
        "status": "sign_off_recorded",
        "alert_id": alert_id,
        "decision": "approved" if approved else "rejected",
        "signed_by": user.user_id
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom error response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


# ============================================================================
# Root Route
# ============================================================================

@app.get("/")
async def root():
    """API documentation entrypoint."""
    return {
        "name": "ChemSentry API",
        "version": "0.1.0",
        "docs": "/docs",
        "openapi": "/openapi.json"
    }
