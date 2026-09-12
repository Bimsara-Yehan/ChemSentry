# ADR 0003: Switch to Mistral AI for Translation and Orchestration

**Date:** 2026-08-18  
**Status:** Accepted  
**Owner:** M3 (Agent B)  

## Context
During Phase 3 development of Agent B, we required an LLM to power two specific features:
1. **SafetyCardNarrator:** Explaining deterministic safety states and translating them into Sinhala and Tamil for factory floor operators.
2. **OpenQueryOrchestrator:** Providing a tool-calling layer to orchestrate open-ended questions (e.g., "Why did Zone B flag a warning last Tuesday?").

The original tech stack placeholder suggested using Anthropic (Claude) or OpenAI for this layer.

## Decision
**We switched the default LLM provider to Mistral AI (`mistral-small-latest`).**

The transition involved changing the API client and modifying the prompt structures to align with Mistral's JSON mode and tool-calling interfaces.

## Alternatives Rejected
* **OpenAI (GPT-4o) / Anthropic (Claude 3.5 Sonnet):**
  * *Reason for rejection:* These models utilize paid per-token billing structures. As this is a zero-budget student project, hitting a rate limit or running out of credits right before the viva evaluation is a significant risk. 
  * *Reason for rejection (Capability):* Our LLM layer explicitly *does not* perform complex safety reasoning (per ADR 0002). It only translates and orchestrates predefined tools. A heavy-weight reasoning model is overkill for this constrained scope.
* **Local Offline Models (e.g., Llama 3 via Ollama):**
  * *Reason for rejection:* While local models are excellent for the "On-Premises" commercialization tier, running them during active development drains local hardware resources needed for running the React UI, FastAPI server, and IDE simultaneously.

## Consequences
* **Positive:** Cost-effective development within a student budget via Mistral's API tiers.
* **Positive:** Mistral Small demonstrates sufficient capability in tool-calling (function calling) and follows strict JSON formats well.
* **Negative:** Sinhala and Tamil translation quality may slightly lag behind GPT-4o's native proficiency, requiring robust fallback mechanisms (returning English text if the translation fails).
