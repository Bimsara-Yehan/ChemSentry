# ChemSentry

ChemSentry is an evidence-grounded, retrieval-driven safety decision-support architecture
for chemical storage environments. It dynamically connects real-world sensor conditions with
authoritative, versioned Safety Data Sheet documentation: a retrieval agent finds the
applicable rule, an evidence reconciler resolves conflicting supplier sources, and a
deterministic safety layer -- never an LLM -- decides SAFE, WARNING, or UNKNOWN before a
human ever sees an alert. No safety threshold is hardcoded; every threshold is retrieved
from a versioned source document at query time and cited back to the user. Built for IT3041
(Information Retrieval and Web Analytics), domain: Chemical Engineering.

## Setup

See [setup.md](setup.md) for the full environment setup guide: repository structure,
software to install, hardware to procure, and the team Git workflow.

## Project context

See [CLAUDE.md](CLAUDE.md) for the architecture summary and hard constraints, and
[ChemSentry_Final_Plan.md](ChemSentry_Final_Plan.md) for the complete project plan.
