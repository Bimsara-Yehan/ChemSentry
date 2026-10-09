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
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# Import Agent A retrieval, Agent B & Safety State Machine components
from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from agents.agent_c_environment.monitor import EnvironmentalMonitor, ZoneEvaluation
from agents.agent_c_environment.zone_inventory import (
    load_zone_inventory,
    seed_default_zone_inventory,
)
from agents.protocols.schemas import (
    SafetyEvaluationRequest,
    SafetyEvaluationResult,
    SafetyState,
)
from api.database import (
    SessionLocal,
    check_db_health,
    get_db,
    get_db_schema_info,
    init_db,
)

# Importing these registers AlertRecord/AuditLogRecord/ZoneInventoryRecord on
# Base.metadata before init_db() runs at startup -- without this import
# having happened, Base.metadata.create_all() would silently create no
# tables for them. (ZoneInventoryRecord itself is unused by name here --
# defined in the same module as AlertRecord, so importing that already
# registers it -- but seed_default_zone_inventory() below is what actually
# populates it.)
from api.db_models import (
    AlertRecord,
    AuditLogRecord,
    UserRecord,
    next_alert_id,
    next_user_id,
)
from api.models import (
    AddChemicalRequest,
    AuditLogEntry,
    AuditLogResponse,
    ChemicalCheckOut,
    CreateUserRequest,
    CreateZoneRequest,
    HealthCheck,
    QueryRequest,
    QueryResponse,
    SensorReading,
    TokenResponse,
    UserInfo,
    UserLogin,
    UserResponse,
    UserRole,
    ZoneStatusResponse,
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

# Real corpus location -- gitignored (see .gitignore), populated by dropping
# local SDS PDFs in. A fresh clone or CI checkout has none, which is why
# _load_retriever() falls back to an empty CorpusRetriever rather than
# failing: an empty corpus correctly makes every query resolve to nothing,
# which /safety/evaluate turns into UNKNOWN (see
# safety/state_machine.py's "no thresholds retrieved" path) -- the honest
# behaviour per CLAUDE.md, not a fabricated verdict.
CORPUS_RAW_DIR = Path(__file__).resolve().parent.parent / "corpus" / "raw"


def _load_retriever() -> CorpusRetriever:
    """Build the real Agent A retriever from corpus/raw/ at startup.

    Tests override the module-level `retriever` directly with a small
    synthetic fixture corpus (see tests/test_api/test_api_gateway.py) rather
    than depending on real PDFs being present, since corpus/raw/ is
    gitignored and empty in CI.
    """
    if CORPUS_RAW_DIR.is_dir() and any(CORPUS_RAW_DIR.glob("*.pdf")):
        return CorpusRetriever.from_local_pdfs(CORPUS_RAW_DIR)
    return CorpusRetriever([])


retriever = _load_retriever()

# Called at import time, not only registered as a startup event: FastAPI's
# on_event("startup") does not fire for a plain `TestClient(app)` unless it's
# used as a context manager (`with TestClient(app) as client:`), which this
# project's test suite doesn't do. Relying on the event alone meant tables
# were only ever created if some earlier test run had already left them on
# disk -- true locally by accident, false on a fresh clone or in CI, where
# every /alerts, /admin/sign-off, and WARNING-path /safety/evaluate call
# failed with "no such table: alerts". create_all() is idempotent, so
# calling it here and again in the startup event below is harmless.
init_db()


def _seed_zone_inventory() -> None:
    """Populate Agent C's zone inventory on first run (idempotent, see
    seed_default_zone_inventory's docstring) -- same "call at import time,
    not only the startup event" reasoning as init_db() above: a plain
    TestClient(app) never fires on_event("startup"), so this must not be
    the only place it's called."""
    db = SessionLocal()
    try:
        seed_default_zone_inventory(db)
    finally:
        db.close()


_seed_zone_inventory()


def _load_zone_inventory() -> dict[str, list[str]]:
    db = SessionLocal()
    try:
        return load_zone_inventory(db)
    finally:
        db.close()


# Agent C (M4): the real EnvironmentalMonitor -- holds no chemical knowledge
# of its own, only which chemicals are in which zone (see
# agents/agent_c_environment/monitor.py's module docstring).
zone_inventory = _load_zone_inventory()


def _get_environmental_monitor() -> EnvironmentalMonitor:
    """Construct the monitor fresh from the current module-level `retriever`
    on every call, rather than capturing it once at import time.

    Mirrors how every other route already reads the module-level `retriever`
    global at call time, not at import time -- tests override `main.retriever`
    with a small fixture corpus after this module has already been imported
    (see tests/test_api/test_api_gateway.py); a `retriever` captured once in
    a module-level `EnvironmentalMonitor` would never see that override.
    Construction itself is cheap (no I/O, just storing references).
    """
    return EnvironmentalMonitor(retriever, evaluator, zone_inventory)


# Ephemeral instrument-state caches, deliberately NOT persisted to the DB --
# unlike AlertRecord/AuditLogRecord (audit-critical, append-only), "what did
# the sensor last read" is not a decision that needs a durable record; only
# the alerts an excursion produces are. Rebuilt from scratch on every
# process restart via _seed_initial_zone_readings() below.
_LATEST_ZONE_EVALUATIONS: dict[str, ZoneEvaluation] = {}
_LAST_ALERT_TIMESTAMP: dict[str, datetime] = {}


def _seed_initial_zone_readings() -> None:
    """Give every inventoried zone one evaluated ambient reading at startup,
    so GET /zones has real data (from the real retrieval + safety-evaluation
    pipeline) to show immediately -- rather than requiring the simulator to
    have already published something first."""
    monitor = _get_environmental_monitor()
    for zone_id in zone_inventory:
        reading = SensorReading(
            zone_id=zone_id,
            temperature_celsius=20.0,
            humidity_percent=45.0,
            timestamp=datetime.now(timezone.utc),
            device_id="startup-default",
        )
        _LATEST_ZONE_EVALUATIONS[zone_id] = monitor.handle_reading(reading)


_seed_initial_zone_readings()


def _zone_status_response(zone_id: str) -> ZoneStatusResponse:
    """Build the API-facing view of a zone from its latest evaluation."""
    evaluation = _LATEST_ZONE_EVALUATIONS[zone_id]
    return ZoneStatusResponse(
        zone_id=zone_id,
        last_reading=evaluation.reading,
        is_excursion=evaluation.is_excursion,
        safety_state=evaluation.aggregated_state.value,
        last_alert_timestamp=_LAST_ALERT_TIMESTAMP.get(zone_id),
        chemicals=zone_inventory.get(zone_id, []),
        checks=[
            ChemicalCheckOut(
                chemical_name=c.chemical_name,
                metric_name=c.metric_name,
                state=c.state.value,
                current_value=c.current_value,
                threshold_value=c.threshold_value,
                reasoning=c.reasoning,
                citation=c.provenance.citation if c.provenance else None,
            )
            for c in evaluation.checks
        ],
    )


# ============================================================================
# Lifecycle Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize database on app startup.

    Plain ASCII only in this log line -- a real `uvicorn api.main:app` run
    (unlike TestClient, which never fires this event at all) writes it to
    Windows' default cp1252 console encoding, which can't encode an emoji
    and crashes app startup outright.
    """
    init_db()
    _seed_zone_inventory()
    print("Database initialized")


# ============================================================================
# Authentication Routes
# ============================================================================


@app.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login with username/password, receive JWT token.

    Demo users (for testing):
    - viewer_user / viewer123 (VIEWER role)
    - analyst_user / analyst123 (ANALYST role)
    - admin_user / admin123 (ADMIN role)
    """
    result = authenticate_user(credentials.username, credentials.password, db=db)
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
    req: SafetyEvaluationRequest,
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
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

    retrieved_thresholds = [
        t
        for t in retriever.get_thresholds(req.chemical_name)
        if t.metric_name == req.metric_name
    ]

    result = evaluator.evaluate(req, retrieved_thresholds)

    # If WARNING state, persist the alert and an audit-log entry (plan §17:
    # "append-only audit log of every alert and sign-off"). Both survive a
    # process restart now -- neither did when this was an in-memory list.
    if result.state == SafetyState.WARNING:
        alert_id = next_alert_id(db)
        db.add(
            AlertRecord(
                alert_id=alert_id,
                zone_id=req.zone_id,
                chemical_name=req.chemical_name,
                current_value=req.current_value,
                unit=req.unit,
                threshold_value=result.threshold_value,
                reasoning=result.reasoning,
                status="pending_review",
                created_by=user.username,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            AuditLogRecord(
                action="alert_created",
                user_id=user.username,
                resource=alert_id,
                details={
                    "zone_id": req.zone_id,
                    "chemical_name": req.chemical_name,
                    "metric_name": req.metric_name,
                },
            )
        )
        db.commit()

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

    thresholds_list = retriever.get_thresholds(request.chemical_name)

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


# ============================================================================
# Agent C -- Environmental Monitoring Routes
# ============================================================================


@app.get("/zones")
async def list_zones(user: UserInfo = Depends(get_current_user)):
    """Current state of every monitored zone (Live Environment dashboard).

    Read-only -- available to VIEWER role, same as /alerts.
    """
    return {"zones": [_zone_status_response(zone_id) for zone_id in zone_inventory]}


@app.get("/zones/{zone_id}", response_model=ZoneStatusResponse)
async def get_zone(zone_id: str, user: UserInfo = Depends(get_current_user)):
    """Current state of a single zone."""
    if zone_id not in zone_inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Zone '{zone_id}' not found"
        )
    return _zone_status_response(zone_id)


@app.post("/zones/{zone_id}/telemetry", response_model=ZoneStatusResponse)
async def submit_zone_telemetry(
    zone_id: str,
    reading: SensorReading,
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Feed one sensor reading through Agent C for a zone.

    Stands in for what the MQTT subscriber (agents/agent_c_environment/
    mqtt_subscriber.py) does for a real/simulated broker message -- exposed
    over HTTP too so the UI's telemetry simulator controls and any future
    hardware bridge that prefers HTTP over MQTT have a real endpoint to call.

    Requires: ANALYST or ADMIN role (same as /safety/evaluate -- a VIEWER
    must not be able to inject sensor data).
    """
    if user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst or Admin role required to submit telemetry",
        )
    if zone_id not in zone_inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Zone '{zone_id}' not found"
        )
    if reading.zone_id != zone_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path zone_id '{zone_id}' does not match reading.zone_id '{reading.zone_id}'",
        )

    evaluation = _get_environmental_monitor().handle_reading(reading)
    _LATEST_ZONE_EVALUATIONS[zone_id] = evaluation

    if evaluation.is_excursion:
        _LAST_ALERT_TIMESTAMP[zone_id] = datetime.now(timezone.utc)
        # One alert per chemical genuinely in WARNING, not one per zone --
        # mirrors /safety/evaluate's per-evaluation persistence, just fanned
        # out across every chemical Agent C checked for this reading.
        for check in evaluation.checks:
            if check.state != SafetyState.WARNING:
                continue
            alert_id = next_alert_id(db)
            db.add(
                AlertRecord(
                    alert_id=alert_id,
                    zone_id=zone_id,
                    chemical_name=check.chemical_name,
                    current_value=check.current_value,
                    unit="C",
                    threshold_value=check.threshold_value,
                    reasoning=check.reasoning,
                    status="pending_review",
                    created_by=user.username,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                AuditLogRecord(
                    action="alert_created",
                    user_id=user.username,
                    resource=alert_id,
                    details={
                        "zone_id": zone_id,
                        "chemical_name": check.chemical_name,
                        "metric_name": check.metric_name,
                    },
                )
            )
        db.commit()

    return _zone_status_response(zone_id)


@app.get("/alerts")
async def list_alerts(
    user: UserInfo = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List all safety alerts in review queue (for Supervisor Dashboard)."""
    alerts = db.query(AlertRecord).order_by(AlertRecord.id).all()
    return {"alerts": [alert.to_dict() for alert in alerts]}


@app.post("/admin/sign-off")
async def sign_off_alert(
    alert_id: str,
    approved: bool,
    notes: Optional[str] = "",
    user: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Sign off on an alert (Supervisor/Admin only).

    Requires: ADMIN role.
    """
    alert = db.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found in the review queue",
        )

    alert.status = "approved" if approved else "rejected"
    alert.signed_by = user.username
    alert.notes = notes
    alert.signed_at = datetime.now(timezone.utc)
    db.add(
        AuditLogRecord(
            action="sign_off",
            user_id=user.username,
            resource=alert_id,
            details={"approved": approved, "notes": notes},
        )
    )
    db.commit()
    db.refresh(alert)

    return {"status": "sign_off_recorded", "alert": alert.to_dict()}


# ============================================================================
# User Management Routes (Item 1)
# ============================================================================


@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    admin: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Create a new real user account (ADMIN only).

    The three demo accounts (viewer_user, analyst_user, admin_user) continue to
    work as a fallback via api/security.py's _get_demo_users() even after real
    accounts exist -- the login route checks the DB first, then demo fallback.
    """
    existing = (
        db.query(UserRecord).filter(UserRecord.username == payload.username).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already taken.",
        )

    from api.security import (
        hash_password,  # already imported at module level via authenticate_user
    )

    user_id = next_user_id(db)
    new_user = UserRecord(
        user_id=user_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserResponse(**new_user.to_dict())


@app.get("/users", response_model=list[UserResponse])
async def list_users(
    admin: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """List all real user accounts (ADMIN only). Does not include demo fallback accounts."""
    users = db.query(UserRecord).order_by(UserRecord.id).all()
    return [UserResponse(**u.to_dict()) for u in users]


# ============================================================================
# Zone Management Routes (Item 2)
# ============================================================================


@app.post("/zones", status_code=status.HTTP_201_CREATED)
async def create_zone(
    payload: CreateZoneRequest,
    admin: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Create a new monitored zone and optionally seed its chemical inventory (ADMIN only).

    After creation:
    - The zone appears immediately in GET /zones (seeded with an ambient reading).
    - Chemical additions are reflected in Agent C's in-memory zone_inventory dict.
    """
    if payload.zone_id in zone_inventory:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Zone '{payload.zone_id}' already exists.",
        )

    # Persist to DB
    for chemical_name in payload.chemicals:
        from api.db_models import ZoneInventoryRecord  # noqa: PLC0415

        db.add(
            ZoneInventoryRecord(zone_id=payload.zone_id, chemical_name=chemical_name)
        )
    db.commit()

    # Update in-memory inventory so GET /zones sees the new zone immediately
    zone_inventory[payload.zone_id] = list(payload.chemicals)

    # Seed an ambient reading so _zone_status_response() doesn't KeyError
    monitor = _get_environmental_monitor()
    reading = SensorReading(
        zone_id=payload.zone_id,
        temperature_celsius=20.0,
        humidity_percent=45.0,
        timestamp=datetime.now(timezone.utc),
        device_id="zone-create-default",
    )
    _LATEST_ZONE_EVALUATIONS[payload.zone_id] = monitor.handle_reading(reading)

    return {
        "zone_id": payload.zone_id,
        "chemicals": zone_inventory[payload.zone_id],
        "status": "created",
    }


@app.post("/zones/{zone_id}/chemicals", status_code=status.HTTP_201_CREATED)
async def add_chemical_to_zone(
    zone_id: str,
    payload: AddChemicalRequest,
    admin: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Add a chemical to an existing zone's inventory (ADMIN only).

    Updates both the DB (ZoneInventoryRecord) and the live in-memory
    zone_inventory dict so the change is immediately visible to Agent C
    without a server restart.
    """
    if zone_id not in zone_inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found.",
        )
    if payload.chemical_name in zone_inventory[zone_id]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.chemical_name}' is already in zone '{zone_id}'.",
        )

    from api.db_models import ZoneInventoryRecord  # noqa: PLC0415

    db.add(ZoneInventoryRecord(zone_id=zone_id, chemical_name=payload.chemical_name))
    db.commit()

    zone_inventory[zone_id].append(payload.chemical_name)

    return {
        "zone_id": zone_id,
        "chemicals": zone_inventory[zone_id],
        "status": "chemical_added",
    }


@app.delete(
    "/zones/{zone_id}/chemicals/{chemical_name}", status_code=status.HTTP_200_OK
)
async def remove_chemical_from_zone(
    zone_id: str,
    chemical_name: str,
    admin: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Remove a chemical from a zone's inventory (ADMIN only).

    Deletes the matching ZoneInventoryRecord row and updates the in-memory
    zone_inventory dict immediately.
    """
    if zone_id not in zone_inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found.",
        )
    if chemical_name not in zone_inventory[zone_id]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{chemical_name}' is not in zone '{zone_id}'.",
        )

    from api.db_models import ZoneInventoryRecord  # noqa: PLC0415

    row = (
        db.query(ZoneInventoryRecord)
        .filter(
            ZoneInventoryRecord.zone_id == zone_id,
            ZoneInventoryRecord.chemical_name == chemical_name,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()

    zone_inventory[zone_id].remove(chemical_name)

    return {
        "zone_id": zone_id,
        "chemicals": zone_inventory[zone_id],
        "status": "chemical_removed",
    }


# ============================================================================
# Audit Log Route (Item 3)
# ============================================================================


@app.get("/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    limit: int = 100,
    offset: int = 0,
    admin: UserInfo = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Return the audit log, newest-first, paginated (ADMIN only).

    EncryptedText/EncryptedJSON columns (user_id, details) decrypt automatically
    when SQLAlchemy reads them -- no crypto.py calls needed here.
    `limit` and `offset` allow basic pagination from the UI.
    """
    total = db.query(AuditLogRecord).count()
    rows = (
        db.query(AuditLogRecord)
        .order_by(AuditLogRecord.id.desc())  # newest-first
        .offset(offset)
        .limit(limit)
        .all()
    )
    entries = [
        AuditLogEntry(
            id=row.id,
            action=row.action,
            user_id=row.user_id,
            resource=row.resource,
            details=row.details,
            timestamp=row.timestamp,
        )
        for row in rows
    ]
    return AuditLogResponse(entries=entries, total=total)


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
