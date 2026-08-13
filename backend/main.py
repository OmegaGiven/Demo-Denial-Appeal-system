"""
Phase 5 FastAPI app: REST layer over the Phase 1-4 pipeline, eval harness,
company profiles, and token-usage accounting.

Run from backend/:
    uvicorn main:app --reload

See README.md's "Phase 5 -- API" section for the full endpoint list.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import analytics, demo, denials, eval as eval_routes, health, profiles, usage

app = FastAPI(
    title="Claims Denial Triage API",
    description=(
        "REST API over the claims-denial triage + appeal-drafting pipeline: "
        "denial worklist/detail, on-demand pipeline processing, human review "
        "actions (appeal status, corrections audit trail), eval-run history, "
        "company profiles, and token/cost usage reporting."
    ),
    version="0.8.0",
)

# Permissive local-dev CORS: a Vite React+TS dev server defaults to
# http://localhost:5173, but Vite silently picks the next free port
# (5174, 5175, ...) if 5173 is already taken by something else on the
# machine -- a hardcoded single-port allowlist breaks the moment that
# happens. Matching any localhost/127.0.0.1 port via regex is more
# robust for local dev than trying to guess/pin one port number.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(denials.router)
app.include_router(eval_routes.router)
app.include_router(profiles.router)
app.include_router(usage.router)
app.include_router(analytics.router)
app.include_router(demo.router)
