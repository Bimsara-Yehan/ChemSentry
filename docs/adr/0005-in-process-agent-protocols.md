# ADR 0005: In-Process Agent Communication via Typed Pydantic Schemas

**Date:** 2026-09-24  
**Status:** Accepted  
**Owner:** Architecture & Agents (M1/M2/M3/M4)  

## Context
Early architectural documentation and initial sprint planning referenced using the Model Context Protocol (MCP) Python SDK for inter-agent communication between Agent A (Retrieval), Agent B (Analysis), and Agent C (Environment Monitoring).

During implementation across Milestones M1 through M4, the agents were integrated within a monolithic FastAPI backend and local evaluation harnesses. We needed to formalize the communication contract across agent boundaries: whether to spawn separate out-of-process MCP server daemons communicating over stdio/HTTP/SSE, or to execute agents in-process using typed protocol schemas.

Constraints considered:
* **Latency & Determinism:** Telemetry evaluation and emergency threshold verification in industrial safety must execute deterministically with sub-millisecond overhead.
* **Deployment Simplicity:** The platform runs locally for laboratory testing, CI/CD pipelines, and university demonstration without requiring multi-process orchestration daemons.
* **Strong Type Safety:** Payloads must enforce strict schema validation (e.g., metric names, units, authority scores, threshold directions) to prevent silent data corruption or unprovenanced threshold comparisons.

## Decision
**We execute agents in-process and standardize inter-agent communication using typed Pydantic models defined in `agents/protocols/schemas.py`.**

Specifically:
* `agents/protocols/schemas.py` defines the canonical protocol data models (`SafetyEvaluationRequest`, `SafetyEvaluationResult`, `ProvenancedThreshold`, `ThresholdDirection`, `SafetyState`, etc.).
* Agent A (`CorpusRetriever`), Agent B (`DeterministicSafetyEvaluator`, `EvidenceReconciler`, `SafetyCardNarrator`), and Agent C (`MqttSubscriber`) communicate directly via Python method calls passing validated Pydantic models.
* The schemas are designed with explicit tool semantics (self-describing fields, strict typing, provenance metadata), ensuring that if out-of-process MCP tool exposure is required in future deployments, the Pydantic schemas map 1:1 to MCP tool definitions without altering agent business logic.

## Alternatives Rejected
* **Separate Out-of-Process MCP Server Daemons (stdio / SSE):**
  * *Reason for rejection:* Spawning and supervising three separate background daemon processes adds substantial IPC latency (JSON serialization/deserialization, process management, socket overhead) and introduces distributed failure modes (broken pipes, port conflicts in CI) without architectural benefit for a single-node deployment.
* **Untyped Dictionaries / Raw JSON:**
  * *Reason for rejection:* Passing raw dicts bypasses validation and allows unit mismatches or missing provenance citations to propagate silently through the safety pipeline.

## Consequences
* **Positive:** Sub-millisecond execution for safety evaluation; zero IPC network or serialization bottlenecks.
* **Positive:** Complete compile-time and runtime type safety with Pydantic v2 validation.
* **Positive:** Simplified testing and CI workflows with single-process pytest execution.
* **Positive:** Protocol contracts remain modular and isolated in `agents/protocols/`, maintaining a clean path for external MCP tool adapters if distributed agent deployment is introduced.
* **Negative:** Agents must run within the same Python process environment and share dependency versions.
