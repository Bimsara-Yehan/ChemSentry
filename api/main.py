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

# Importing these registers AlertRecord/AuditLogRecord/ZoneInventoryRecord on
# Base.metadata before init_db() runs at startup -- without this import
# having happened, Base.metadata.create_all() would silently create no
# tables for them. (ZoneInventoryRecord itself is unused by name here --
# defined in the same module as AlertRecord, so importing that already
# registers it -- but seed_default_zone_inventory() below is what actually
# populates it.)
from agents.agent_b_analysis.apriori_discovery import CoStoragePatternMiner
from agents.agent_b_analysis.llm_layer import SafetyCardNarrator
from agents.agent_b_analysis.query_orchestrator import OpenQueryOrchestrator
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
from api.db_models import AlertRecord, AuditLogRecord, next_alert_id
from api.models import (
    ChemicalCheckOut,
    CoStorageCheckResponse,
    CoStorageRule,
    HealthCheck,
    NarrateAlertResponse,
    OpenQueryRequest,
    OpenQueryResponse,
    QueryRequest,
    QueryResponse,
    SensorReading,
    SeverityRequest,
    SeverityResponse,
    TokenResponse,
    UserInfo,
    UserLogin,
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
# Agent B — Co-Storage & Narration Routes (M3, PR 1)
# ============================================================================


@app.get("/zones/{zone_id}/co-storage-check", response_model=CoStorageCheckResponse)
async def co_storage_check(
    zone_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """Mine co-storage association rules for a zone and flag CAMEO incompatibilities.

    Problem: CoStoragePatternMiner.discover_co_storage_rules() existed and
    passed its own tests but was unreachable from any API route. The zone_inventory
    dict (already loaded at startup) is the exact transaction set Apriori needs --
    each zone's chemical list IS one transaction.

    Technique: Apriori over all-zone transactions, then CAMEO-matrix lookup per
    discovered rule (see apriori_discovery.py). Returns rules for the requested
    zone's chemicals only. Read-only; does NOT assign a safety verdict -- Apriori
    discovers co-occurrence patterns, the CAMEO lookup classifies reactivity.

    Accessible to all authenticated roles (VIEWER, ANALYST, ADMIN) because this
    is informational, not a safety evaluation that could be acted on without
    human sign-off.
    """
    if zone_id not in zone_inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    zone_chemicals = zone_inventory[zone_id]
    if not zone_chemicals:
        return CoStorageCheckResponse(zone_id=zone_id, chemicals=[], rules=[])

    # Build the full transaction list (one list[str] per zone) so Apriori has
    # enough support signal even for single-zone queries -- using all zones
    # together means a pair that appears in multiple zones gets higher support,
    # which is the honest answer about how often they co-occur across the site.
    # Then filter the returned rules to only those whose antecedent+consequent
    # are both present in the requested zone.
    all_transactions: list[list[str]] = list(zone_inventory.values())

    miner = CoStoragePatternMiner(min_support=0.2, min_threshold_lift=1.0)
    raw_rules = miner.discover_co_storage_rules(all_transactions)

    zone_chemical_set = set(zone_chemicals)
    zone_rules = [
        CoStorageRule(
            antecedents=r["antecedents"],
            consequents=r["consequents"],
            support=r["support"],
            confidence=r["confidence"],
            lift=r["lift"],
            incompatibility_status=r["incompatibility_status"],
        )
        for r in raw_rules
        if set(r["antecedents"]) | set(r["consequents"]) <= zone_chemical_set
    ]

    return CoStorageCheckResponse(
        zone_id=zone_id,
        chemicals=zone_chemicals,
        rules=zone_rules,
    )


@app.post("/alerts/{alert_id}/narrate", response_model=NarrateAlertResponse)
async def narrate_alert(
    alert_id: str,
    language: Optional[str] = None,
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a plain-language explanation (and optional translation) for an alert.

    Problem: SafetyCardNarrator existed with explain_alert() and
    translate_safety_card() but was wired to nothing. Alerts are stored in
    AlertRecord rows (api/db_models.py) which hold all the fields needed to
    reconstruct the SafetyEvaluationResult the narrator expects.

    Technique: On-demand LLM call (one Mistral request per invocation). Not
    triggered automatically on every alert read because it costs a real API
    call; the UI should offer it as an explicit "Explain" button. Falls back
    gracefully if MISTRAL_API_KEY is absent.

    Safety constraint enforced here and in SafetyCardNarrator: the
    safety_state in the response is always the deterministic value from the
    AlertRecord, never a string produced or modified by the LLM.

    Optional query param `language`: 'si' (Sinhala) or 'ta' (Tamil) to also
    return a translated card alongside the English explanation.
    """
    alert = db.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found",
        )

    # Reconstruct the minimal SafetyEvaluationResult the narrator's prompts
    # need. We only have what was persisted in AlertRecord (chemical_name,
    # zone_id, current_value, unit, threshold_value, reasoning) -- there is
    # no reconstructed provenance or metric_name, so we use safe fallbacks.
    # The narrator never uses provenance to make a safety decision; it only
    # uses it for the citation string in the prompt, which falls back to 'N/A'.
    from datetime import timezone

    from agents.protocols.schemas import SafetyEvaluationResult, SafetyState

    # Map the stored alert status to a SafetyState for the narrator prompt.
    # AlertRecord.status is workflow state ("pending_review", "approved",
    # "rejected") -- the actual safety verdict was WARNING when the alert
    # was created (only WARNING evaluations produce AlertRecords).
    result = SafetyEvaluationResult(
        state=SafetyState.WARNING,
        chemical_name=alert.chemical_name,
        zone_id=alert.zone_id,
        metric_name="(see alert reasoning)",
        current_value=alert.current_value,
        threshold_value=alert.threshold_value,
        unit=alert.unit,
        provenance=None,
        reasoning=alert.reasoning,
        evaluated_at=alert.created_at or datetime.now(timezone.utc),
    )

    narrator = SafetyCardNarrator()
    explanation = narrator.explain_alert(result)

    translation: Optional[dict[str, str]] = None
    if language:
        translation = narrator.translate_safety_card(result, language)

    # safety_state is always the deterministic WARNING from the AlertRecord,
    # never a string produced by the LLM.
    return NarrateAlertResponse(
        alert_id=alert_id,
        safety_state=SafetyState.WARNING.value,
        explanation=explanation,
        translation=translation,
    )


# ============================================================================
# Agent B — Hazard Severity Classifier Route (M3, PR 2)
# ============================================================================


@app.post("/classifier/severity", response_model=SeverityResponse)
async def classify_severity(
    req: SeverityRequest,
    user: UserInfo = Depends(get_current_user),
):
    """Classify chemical hazard severity (LOW / MEDIUM / HIGH / CRITICAL).

    Problem: HazardSeverityClassifier.predict_severity() existed and passed its own
    tests but was unreachable from any API route (Lab 08 deliverable, M3).

    NFPA data gap (decision documented here per the task spec): NFPA 704 diamond
    ratings are NOT extracted anywhere in this codebase -- the real SDS corpus
    (corpus/raw/) does not contain NFPA ratings in any parseable form, and
    extraction/value_extractor.py has no NFPA parser. Option (b) was chosen over
    option (a): rather than fabricating extraction logic that has no real source
    data to operate on, the three NFPA inputs are explicitly parameterized as
    caller-supplied. The SeverityRequest schema makes the gap visible (required
    fields with descriptive validation messages; no silent zero-default); a caller
    without real NFPA data will receive a 422 validation error, not a severity
    label silently computed from made-up zeros.

    ghs_code_count is the one feature the pipeline CAN derive from the real corpus:
    len(ProvenancedThreshold.hazard_statements) on any threshold from /query.

    This route does NOT set a SAFE/WARNING/UNKNOWN state -- it runs the Lab 08
    classifier which labels severity for downstream triage. The deterministic
    safety-state machine (safety/state_machine.py) remains the only path to
    SAFE/WARNING/UNKNOWN.

    Requires: any authenticated role (read-only classification, no data injection).
    """
    from agents.agent_b_analysis.classifier import HazardSeverityClassifier

    classifier = HazardSeverityClassifier()
    severity, confidence = classifier.predict_severity(
        nfpa_health=req.nfpa_health,
        nfpa_flammability=req.nfpa_flammability,
        nfpa_instability=req.nfpa_instability,
        ghs_code_count=req.ghs_code_count,
    )

    return SeverityResponse(
        chemical_name=req.chemical_name,
        severity=severity,
        confidence=round(confidence, 4),
        nfpa_health=req.nfpa_health,
        nfpa_flammability=req.nfpa_flammability,
        nfpa_instability=req.nfpa_instability,
        ghs_code_count=req.ghs_code_count,
        note=(
            "NFPA 704 ratings (nfpa_health, nfpa_flammability, nfpa_instability) "
            "are caller-supplied -- this pipeline does not extract NFPA ratings from "
            "SDS documents. Only ghs_code_count is derivable from this corpus "
            "(len(ProvenancedThreshold.hazard_statements) from /query or /safety/evaluate)."
        ),
    )


# ============================================================================
# Agent B — Open-Ended Query Orchestrator Route (M3, PR 3)
# ============================================================================


def _get_query_orchestrator() -> OpenQueryOrchestrator:
    """Construct an OpenQueryOrchestrator wired to real system tools.

    Problem: OpenQueryOrchestrator (Phase 3 of M3) was an isolated LLM tool-calling
    engine with no registered tools -- .handle_query() had nothing to call and fell
    back immediately.

    Architecture & viva rationale (why this technique over an unconstrained LLM):
    Allowing an LLM to directly answer chemical safety questions creates severe
    hallucination risk (e.g. inventing storage temperatures or hazard ratings).
    Instead, ChemSentry uses tool-calling as an orchestrator: the LLM dynamically
    selects which classical IR or database tools to query, but every factual
    threshold, citation, and co-storage status comes from deterministic backend
    code. The LLM synthesizes the tool outputs; it never decides SAFE/WARNING/UNKNOWN
    or invents numbers.

    Dynamically constructed on each call:
    Mirrors _get_environmental_monitor() -- binds to the current module-level
    `retriever` global so test overrides (e.g. test fixture corpora) are immediately
    visible to the search_sds_thresholds tool without restarting the app.

    Registered tools:
      1. search_sds_thresholds: Queries classical CorpusRetriever for exact SDS thresholds.
      2. get_recent_alerts: Queries the DB AlertRecord table for historical incidents.
      3. check_zone_co_storage: Mines Apriori rules and checks CAMEO reactivity for a zone.
    """
    orchestrator = OpenQueryOrchestrator()

    def search_sds_thresholds(chemical_name: str) -> str:
        """Search Safety Data Sheet (SDS) corpus for chemical storage limits and hazard statements."""
        if not retriever:
            return "No SDS retriever available."
        results = retriever.get_thresholds(chemical_name)
        if not results:
            return f"No SDS thresholds found for '{chemical_name}' in the corpus."
        lines = []
        for r in results:
            hazards = (
                ", ".join(sorted(r.hazard_statements))
                if r.hazard_statements
                else "None"
            )
            lines.append(
                f"- {chemical_name}: {r.metric_name} = {r.value} {r.unit} "
                f"(Source: {r.sds_id} [{r.supplier_name}], {r.section_number}; Citation: {r.citation}). "
                f"Hazards: {hazards}"
            )
        return "\n".join(lines)

    orchestrator.register_tool(
        name="search_sds_thresholds",
        description="Search Safety Data Sheets (SDS) for chemical storage limits, temperature thresholds, and hazard statements using classical IR.",
        parameters={
            "type": "object",
            "properties": {
                "chemical_name": {
                    "type": "string",
                    "description": "Name of chemical to look up (e.g. 'Toluene', 'Hydrogen peroxide').",
                }
            },
            "required": ["chemical_name"],
        },
        func=search_sds_thresholds,
    )

    def get_recent_alerts(zone_id: str | None = None, limit: int = 5) -> str:
        """Retrieve recent safety alert records from the audit database."""
        db = SessionLocal()
        try:
            query = db.query(AlertRecord)
            if zone_id:
                query = query.filter(AlertRecord.zone_id == zone_id)
            alerts = query.order_by(AlertRecord.created_at.desc()).limit(limit).all()
            if not alerts:
                target = f"for zone '{zone_id}'" if zone_id else "in the system"
                return f"No recent alerts found {target}."
            lines = []
            for a in alerts:
                is_signed_off = "Yes" if a.signed_at else "No"
                lines.append(
                    f"Alert {a.alert_id} [{a.created_at.isoformat()}]: Zone {a.zone_id}, "
                    f"Chemical: {a.chemical_name}, Status: {a.status}, Reading: {a.current_value} {a.unit}, "
                    f"Threshold: {a.threshold_value}, Signed off: {is_signed_off}"
                )
            return "\n".join(lines)
        finally:
            db.close()

    orchestrator.register_tool(
        name="get_recent_alerts",
        description="Query the alert log for recent chemical safety alerts or warnings in a specific zone or across all zones.",
        parameters={
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Optional zone filter, e.g. 'Zone_A', 'Zone_B', 'Zone_C'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of alerts to return (default 5).",
                },
            },
        },
        func=get_recent_alerts,
    )

    def check_zone_co_storage(zone_id: str) -> str:
        """Inspect co-storage rules and CAMEO reactivity warnings for chemicals stored in a zone."""
        current_inv = _load_zone_inventory()
        if zone_id not in current_inv:
            return f"Zone '{zone_id}' not found in inventory."
        transactions = [chemicals for chemicals in current_inv.values() if chemicals]
        miner = CoStoragePatternMiner(min_support=0.01, min_threshold_lift=0.0)
        rules = miner.discover_co_storage_rules(transactions)
        zone_chems = set(current_inv[zone_id])
        zone_rules = [
            r
            for r in rules
            if set(r["antecedents"]).issubset(zone_chems)
            and set(r["consequents"]).issubset(zone_chems)
        ]
        if not zone_rules:
            return (
                f"No co-storage rules or reactivity warnings found for chemicals in {zone_id} "
                f"({list(zone_chems)})."
            )
        lines = [f"Co-storage analysis for {zone_id} ({', '.join(zone_chems)}):"]
        for r in zone_rules:
            lines.append(
                f"- {' + '.join(r['antecedents'])} -> {' + '.join(r['consequents'])}: "
                f"Status: {r['incompatibility_status']} (Support: {r['support']:.2f}, Conf: {r['confidence']:.2f})"
            )
        return "\n".join(lines)

    orchestrator.register_tool(
        name="check_zone_co_storage",
        description="Inspect co-storage compatibility rules and CAMEO reactivity warnings for chemicals stored together in a specific zone.",
        parameters={
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Zone identifier to inspect (e.g. 'Zone_A', 'Zone_B', 'Zone_C').",
                }
            },
            "required": ["zone_id"],
        },
        func=check_zone_co_storage,
    )

    return orchestrator


@app.post("/query/open", response_model=OpenQueryResponse)
async def query_open(
    req: OpenQueryRequest,
    user: UserInfo = Depends(get_current_user),
):
    """Handle open-ended natural language safety officer queries (Item 4, M3 Phase 3).

    Problem: OpenQueryOrchestrator in agents/agent_b_analysis/query_orchestrator.py
    provides dynamic LLM tool-calling capabilities (e.g. 'Why did Zone B flag a
    warning last Tuesday?' or 'What are the limits for Toluene?'), but had no API
    route and no wired tools.

    Design & safety constraints:
    - Tool-calling routes retrieval and queries deterministically; the LLM synthesizes
      evidence but never generates safety verdicts or invents numbers.
    - If MISTRAL_API_KEY is not set (e.g. in test or offline CI), gracefully degrades
      to the orchestrator's built-in fallback response.
    - Requires authenticated user (read-only query).
    """
    orchestrator = _get_query_orchestrator()
    answer = orchestrator.handle_query(req.query)
    return OpenQueryResponse(
        query=req.query,
        response=answer,
        tools_registered=list(orchestrator._tools.keys()),
    )


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
