# Cross-Training Explainer: Agent B (Analysis & Safety Layer)

**Owner:** M3  
**Audience:** M1, M2, M4  

## What does Agent B do?
Agent B is the semantic reasoner and safety logic core of ChemSentry. Once Agent A retrieves raw storage thresholds from indexed SDS documents, Agent B takes over to reconcile any conflicts, evaluate the safety of the current physical environment, classify hazards, and generate explanations.

## The Architecture Flow
1. **Evidence Reconciler:** When multiple suppliers disagree on a chemical's properties (e.g., Supplier X says store below 25°C, Supplier Y says store below 30°C), the Reconciler evaluates the `authority_score` of each source. If sources of equal authority diverge beyond a 5% tolerance, or if their GHS Hazard Statements clash (detected using Jaccard Similarity), the Reconciler refuses to guess and flags a conflict.
2. **Deterministic Safety State Machine:** Takes the reconciled threshold and compares it to Agent C's live telemetry (e.g., temperature). The mathematical logic here is entirely deterministic and yields one of three strict states: `SAFE`, `WARNING`, or `UNKNOWN`. It explicitly handles unit conversions and directionality (is the limit a ceiling or a floor?).
3. **Hazard Severity Classifier:** Uses a Scikit-Learn `DecisionTreeClassifier` (Lab 08) trained on NFPA 704 and GHS features to assign a severity rating (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) to the chemical involved.
4. **Co-Storage Apriori Miner:** Uses the Apriori algorithm (Lab 09) to mine warehouse inventory data and discover common co-storage patterns. These are then checked against a CAMEO reactivity matrix to identify incompatible chemical pairings.
5. **Mistral AI Translation Layer:** The LLM is invoked *only at the very end*. It is strictly prohibited from participating in the safety decision path. It takes the deterministic `SAFE/WARNING/UNKNOWN` state as an immutable fact and provides a natural language summary, translating the alert into Sinhala and Tamil for floor workers.

## Key Takeaway for Viva Defense
If the panel asks about AI Hallucinations in safety: **"The LLM does not decide safety. The mathematical state machine does. The LLM only translates the output."**
