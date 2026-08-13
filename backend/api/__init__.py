"""FastAPI application package: REST layer over the Phase 1-4 pipeline/eval/DB.

Structure:
    main.py (backend/)   - FastAPI() app instance, CORS, router mounting
    api/deps.py           - shared DB-session dependency
    api/schemas.py        - Pydantic request/response models
    api/routes/*.py       - one router module per resource area
"""
