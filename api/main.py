"""ChemSentry API gateway -- FastAPI entrypoint (M4).

Scaffolding only: exposes a health-check endpoint. Auth, RBAC, and domain routes
are added once the retrieval and safety layers exist.
"""

from fastapi import FastAPI

app = FastAPI(title="ChemSentry API")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
