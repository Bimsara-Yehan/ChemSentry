"""ChemSentry API Gateway — FastAPI entrypoint (M4).

Provides authentication (JWT login/token), health checks, safety evaluations,
and integration points for Agent A (retrieval), Agent B (safety analysis), and Agent C (environment).

Auth flow:
  1. Client POSTs /auth/login with username/password
  2. API returns JWT token
  3. Client includes token in Authorization: Bearer <token> header
  4. Protected routes verify token via get_current_user dependency
  5. RBAC enforces role-based access (viewer < analyst < admin)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# Import Agent B & Safety State Machine components
from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    SafetyEvaluationResult,
    SafetyState,
    ThresholdDirection,
)
from api.database import check_db_health, get_db, get_db_schema_info, init_db
from api.models import (
    HealthCheck,
    QueryRequest,
    QueryResponse,
    TokenResponse,
    UserInfo,
    UserLogin,
    UserRole,
)
from api.security import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_role,
)
from safety.state_machine import DeterministicSafetyEvaluator

# Create FastAPI app
app = FastAPI(
    title="ChemSentry API",
    description="Chemical safety retrieval, reconciliation, and deterministic evaluation gateway",
    version="0.1.0",
)

# Add CORS middleware (allow frontend to call from different origin during dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize engines
evaluator = DeterministicSafetyEvaluator()

# STOPGAP: Agent A's retrieval pipeline (corpus, index, TF-IDF ranking) does not exist
# yet, so there is nothing real to query here. These are hand-entered placeholder
# values, not thresholds retrieved from a versioned SDS document -- they exist only to
# unblock API/frontend integration and MUST be replaced by real Agent A retrieval
# before this project can claim "no hardcoded thresholds" (see CLAUDE.md).
MOCK_SDS_DATABASE_PENDING_AGENT_A_RETRIEVAL = {
    "toluene": [
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=25.0,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id="SDS_TOL_001",
            supplier_name="ABC Chemicals",
            section_number="Section 7",
            authority_score=1.0,
            citation="ABC Chemicals SDS Rev 2026-02 §7, p.5",
        ),
        ProvenancedThreshold(
            metric_name="flash_point",
            value=4.4,
            unit="C",
            direction=ThresholdDirection.MIN,
            sds_id="SDS_TOL_001",
            supplier_name="ABC Chemicals",
            section_number="Section 9",
            authority_score=1.0,
            citation="ABC Chemicals SDS Rev 2026-02 §9, p.7",
        ),
    ],
    "ethanol": [
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=30.0,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id="SDS_ETH_002",
            supplier_name="Sigma Aldrich",
            section_number="Section 7",
            authority_score=1.0,
            citation="Sigma Aldrich SDS Rev 2025-10 §7",
        )
    ],
    "acetone": [
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=20.0,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id="SDS_ACE_003",
            supplier_name="Merck",
            section_number="Section 7",
            authority_score=1.0,
            citation="Merck SDS Rev 2026-01 §7",
        )
    ],
}

# In-memory alerts registry for Supervisor Dashboard & Sign-Off workflow
ALERTS_REGISTRY = []


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
    """
    result = authenticate_user(credentials.username, credentials.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    user_id, role = result
    token, expires_in = create_access_token(user_id, credentials.username, role)

    return TokenResponse(access_token=token, expires_in=expires_in)


# ============================================================================
# Health & Status Routes
# ============================================================================


@app.get("/health", response_model=HealthCheck)
async def health_check(db: Session = Depends(get_db)):
    """Health check — verify API, database, and MQTT broker status."""
    db_status = check_db_health()
    mqtt_status = "ok"
    overall_status = "ok" if db_status == "ok" else "degraded"

    return HealthCheck(
        status=overall_status,
        database=db_status,
        mqtt_broker=mqtt_status,
        version="0.1.0",
    )


@app.get("/debug/schema")
async def debug_schema(user: UserInfo = Depends(get_current_user)):
    """Debug endpoint — show database schema (admin only)."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return get_db_schema_info()


# ============================================================================
# Protected Core Domain Routes (require authentication)
# ============================================================================


@app.get("/me")
async def get_current_user_info(user: UserInfo = Depends(get_current_user)):
    """Get current user info from JWT token."""
    return user


@app.post("/safety/evaluate", response_model=SafetyEvaluationResult)
async def evaluate_safety_endpoint(
    req: SafetyEvaluationRequest, user: UserInfo = Depends(get_current_user)
):
    """Execute deterministic safety evaluation for a chemical reading.

    Retrieves versioned SDS thresholds and evaluates current value strictly
    against source-backed limits (No hardcoding, No LLM decision).

    Requires: ANALYST or ADMIN role.
    """
    if user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst or Admin role required for safety evaluation",
        )

    chem_key = req.chemical_name.lower().strip()
    retrieved_thresholds = [
        t
        for t in MOCK_SDS_DATABASE_PENDING_AGENT_A_RETRIEVAL.get(chem_key, [])
        if t.metric_name == req.metric_name
    ]

    result = evaluator.evaluate(req, retrieved_thresholds)

    # If WARNING state, automatically record in ALERTS_REGISTRY for Supervisor Dashboard
    if result.state == SafetyState.WARNING:
        alert_record = {
            "alert_id": f"ALT_{len(ALERTS_REGISTRY) + 1:04d}",
            "zone_id": req.zone_id,
            "chemical_name": req.chemical_name,
            "current_value": req.current_value,
            "unit": req.unit,
            "threshold_value": result.threshold_value,
            "reasoning": result.reasoning,
            "status": "pending_review",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.username,
        }
        ALERTS_REGISTRY.append(alert_record)

    return result


@app.post("/query", response_model=QueryResponse)
async def query_chemical(
    request: QueryRequest, user: UserInfo = Depends(get_current_user)
):
    """Query a chemical for safety info, fast-path rule answers, and thresholds.

    Requires: ANALYST or ADMIN role.
    """
    if user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst role required for queries",
        )

    chem_key = request.chemical_name.lower().strip()
    thresholds_list = MOCK_SDS_DATABASE_PENDING_AGENT_A_RETRIEVAL.get(chem_key, [])

    threshold_dicts = [
        {
            "parameter": t.metric_name,
            "value": t.value,
            "unit": t.unit,
            "source_doc_id": t.sds_id,
            "version": t.citation,
        }
        for t in thresholds_list
    ]

    # NOTE: This endpoint only retrieves threshold data -- it never receives a current
    # sensor reading, so it cannot run DeterministicSafetyEvaluator and must never
    # assert SAFE or WARNING. Having threshold data on file is not a safety verdict.
    # Use /safety/evaluate for an actual deterministic evaluation.
    #
    # The Lab 06B fast-path engine is not wired in here: ChatFastPath.match_fast_path()
    # expects a full natural-language question ("what is the flash point of X"), but
    # QueryRequest only carries a bare chemical name -- there is no free-text field to
    # match against yet. Re-enable once QueryRequest gains a real query-text field.
    return QueryResponse(
        query_id=f"QRY_{hash(request.chemical_name) % 10000:04d}",
        query=request,
        evidence={
            "query_chemical": request.chemical_name,
            "retrieved_docs": [],
            "thresholds": threshold_dicts,
            "conflicts": [],
            "final_safety_state": "UNKNOWN",
        },
    )


@app.get("/alerts")
async def list_alerts(user: UserInfo = Depends(get_current_user)):
    """List all safety alerts in review queue (for Supervisor Dashboard)."""
    return {"alerts": ALERTS_REGISTRY}


@app.post("/admin/sign-off")
async def sign_off_alert(
    alert_id: str,
    approved: bool,
    notes: Optional[str] = "",
    user: UserInfo = Depends(require_role(UserRole.ADMIN)),
):
    """Sign off on an alert (Supervisor/Admin only).

    Requires: ADMIN role.
    """
    found_alert = None
    for alert in ALERTS_REGISTRY:
        if alert["alert_id"] == alert_id:
            alert["status"] = "approved" if approved else "rejected"
            alert["signed_by"] = user.username
            alert["notes"] = notes
            alert["signed_at"] = datetime.now(timezone.utc).isoformat()
            found_alert = alert
            break

    if not found_alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found in the review queue",
        )

    return {"status": "sign_off_recorded", "alert": found_alert}


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom error response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
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
        "openapi": "/openapi.json",
    }
