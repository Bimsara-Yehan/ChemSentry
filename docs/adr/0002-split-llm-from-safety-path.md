# ADR 0002: Isolation of LLM from the Safety Decision Path

**Date:** 2026-08-18  
**Status:** Accepted  
**Owner:** M3 (Agent B)  

## Context
ChemSentry's core value proposition is evidence-grounded, deterministic safety alerting. A key architectural question arose during the design of Agent B (Analysis): *Should the Language Model (LLM) be responsible for reading the extracted rules and deciding if the current sensor readings indicate a SAFE, WARNING, or UNKNOWN state?* 

LLMs excel at semantic parsing and zero-shot reasoning. Using the LLM to output the safety verdict would significantly reduce the complexity of writing mathematical reconciliation rules and handling unit conversions.

## Decision
**We explicitly forbid the LLM from participating in the safety decision path.** 

The safety evaluation is handled strictly by the `DeterministicSafetyEvaluator` (`safety/state_machine.py`), which uses rigid mathematical thresholds and returns one of three states (`SAFE`, `WARNING`, `UNKNOWN`).

The LLM (`SafetyCardNarrator`) is invoked **only after** the state machine reaches a verdict. It is provided with the final deterministic state as an immutable fact, and its role is strictly limited to explaining the reasoning naturally and translating it into Sinhala/Tamil.

## Alternatives Rejected
* **LLM-as-Judge:** Passing the raw telemetry and extracted text to the LLM and asking "Is this dangerous?" 
  * *Reason for rejection:* LLMs are non-deterministic and prone to hallucinations. In a safety-critical industrial environment, a hallucinated "SAFE" verdict when temperature limits are breached is catastrophic.
* **LLM parsing numeric values dynamically:** Using the LLM to convert units (e.g., Fahrenheit to Celsius) before comparison.
  * *Reason for rejection:* Hallucinating a math error. If a conversion is needed, it must be handled deterministically or flagged as `UNKNOWN` for human review.

## Consequences
* **Positive:** Complete audibility and safety guarantees. The pipeline is mathematically provable. 
* **Positive:** Enforces the "Preservation of Uncertainty" principle. The state machine easily defaults to `UNKNOWN` when it lacks data.
* **Negative:** Increased development overhead (writing strict Jaccard-based evidence reconciliation and unit-matching code). 
