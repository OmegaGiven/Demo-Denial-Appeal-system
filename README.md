# Claims Denial Triage + Appeal Drafting System

An AI system for healthcare insurance claim denials: it reads a denial
letter, pulls out the structured facts, figures out why the claim was
denied, and drafts an appeal letter arguing it should be paid — with a
human always reviewing before anything goes out, an evaluation harness
that detects when the AI's accuracy regresses, and a full audit trail of
every decision (AI or human) made along the way.

Built around production-grade AI engineering practices: forced
structured output (not hoping free text parses as JSON), a deterministic
eval/regression harness, an immutable audit log, and a multi-tenant
architecture where the same pipeline code serves multiple client
companies off configuration alone.

**This is a self-contained reference implementation, not a deployed
production system** — it runs against synthetic data with no
authentication layer and no connection to any real claims/billing
system. See [Path to production](#path-to-production) for exactly
what closing that gap would take.

## What it does

1. **A denial letter comes in** — either one of the pre-loaded synthetic
   examples, or pasted in live through the "New Denial" form.
2. **Extraction** — an LLM call (forced tool-use, not freeform text
   parsing) pulls structured fields out of the raw letter: claim
   reference, procedure code, dollar amount, the payer's stated denial
   reason, and so on. Fields vary by client — see [Company
   Profiles](#company-profiles) below.
3. **Classification** — a second LLM call assigns the denial to one of
   six root-cause categories (`coding_error`, `missing_information`,
   `medical_necessity`, `timely_filing`, `eligibility`,
   `duplicate_claim`) with a confidence score.
4. **Confidence gate** — below a 70% confidence threshold, the denial
   stops here and routes to `needs_review` instead of drafting an appeal
   off a guess. Above threshold, it proceeds.
5. **Appeal drafting** — a third LLM call writes an appeal letter,
   grounded in the actual extracted facts (claim number, procedure code,
   physician NPI, prior authorization number where relevant), arguing
   the denial should be overturned.
6. **Human review** — a reviewer reads the drafted appeal next to the
   original letter, can approve it, reject it, or log a correction to
   any AI-produced field (with a reason, permanently recorded). Nothing
   is auto-submitted anywhere.
7. **Everything is logged** — every AI action and every human decision
   lands in one chronological, immutable [audit trail](#audit-trail).

**Known scope boundary**: the system currently always attempts to draft
an appeal once classification confidence clears the threshold — it does
not attempt to judge whether the original denial was actually valid. The
confidence score measures certainty about *which category* a denial
falls into, not whether the appeal will succeed or whether the payer's
decision was correct. A production version would need a second judgment
layer for that; it's out of scope here.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend   │─────▶│   FastAPI     │─────▶│  Postgres    │
│ React + TS   │      │   backend     │      │  (schema     │
│ (queue,      │◀─────│  (REST API)   │◀─────│   below)     │
│  review UI,  │      └──────┬───────┘      └─────────────┘
│  dashboard)  │              │
└─────────────┘              ▼
                     ┌──────────────────┐
                     │  Pipeline          │
                     │  extract → classify │
                     │  → draft_appeal      │
                     │  (Anthropic API,     │
                     │   forced tool-use)   │
                     └──────────────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │  Company Profile   │
                     │  (extraction schema,│
                     │   prompts, appeal    │
                     │   guidance — per      │
                     │   client, config not  │
                     │   code)                │
                     └──────────────────┘
```

## Core concepts

### Company profiles

The pipeline (`backend/pipeline/extract.py`/`classify.py`/`draft_appeal.py`)
doesn't hardcode any one client's terminology or document structure — it's
driven at runtime by a `CompanyProfile` (`backend/profiles/base.py`), a
frozen dataclass holding everything that varies per client:

- **Extraction schema** — the structured fields to pull out (e.g. one
  profile extracts `cpt_code`, another extracts `hcpcs_code` +
  `equipment_type` + a Letter-of-Medical-Necessity reference — genuinely
  different document types need genuinely different fields).
- **Prompts** — extraction/classification/appeal-drafting system prompts
  with client-specific framing.
- **Appeal guidance** — per-category argument guidance for drafting.

What deliberately does **not** vary: the six classification categories
are shared across every profile — they're generic root causes for any
healthcare claim denial, not specific to one client's document type.

Two example profiles ship with this project — `meridian_eyecare_partners`
(an eye-care claims example) and `summit_dme_providers` (a durable
medical equipment / complex rehab technology example) — proving the same
pipeline code handles genuinely different claim types via configuration
alone, not a rewrite. See `/profiles` in the running app for a live
side-by-side comparison, including a button that reprocesses a real
denial from each client back-to-back.

**Adding a third profile**: create `backend/profiles/<key>.py` following
either existing profile as a template, register it in
`backend/profiles/__init__.py`'s `PROFILES` dict, add a synthetic dataset
under `backend/data/`, and seed it. Nothing in `pipeline/*.py` needs to
change.

### Audit trail

Every reviewable action on a denial — AI or human — is logged as an
**immutable, append-only** event, never overwritten. Three event types,
all sharing one table (`corrections`, SQLAlchemy model `AuditEvent`):

- **`ai_action`** — the pipeline's own actions: "Processed denial
  letter" (extraction), "Classified as `<category>`", "Drafted appeal" —
  each with `corrected_by = "AI"`.
- **`correction`** — a human editing an AI-produced field (e.g.
  re-picking the classification category), with who made the change,
  what it was before/after, and why. Does **not** mutate the original AI
  output — the AI's original answer and the human's correction both
  stay on the record, distinctly.
- **`appeal_review`** — an approve/reject/sent decision on a drafted
  appeal, with reviewer and timestamp. The `appeals` table also keeps a
  *mutable* "current state" column for quick display, but every review
  decision additionally gets a permanent audit row — so if an appeal is
  approved, later regenerated, and re-reviewed, both review decisions
  stay on record, not just the latest.

One correction has real downstream effect beyond the audit log: if a
human corrects `classification.category` and then uses "Draft Appeal
Letter" (which runs only the drafting stage, not a full reprocess), the
drafting prompt uses the corrected category — without ever mutating the
original AI classification row. The AI's original answer and the
human's override both remain visible in the trail.

### Evaluation & regression detection

`backend/eval/` is a deterministic scoring harness — **it makes no LLM
calls**, it only reads what the pipeline already wrote to Postgres and
compares it against a 24-record hand-labeled ground-truth set, so it's
cheap and safe to run after every change:

```bash
cd backend
python -m eval.run_eval
```

Three scoring dimensions, weighted `0.4 * classification + 0.3 *
extraction + 0.3 * appeal_completeness`:

1. **Classification accuracy** — does the predicted category exactly
   match ground truth?
2. **Extraction accuracy** — does the extracted CARC code match ground
   truth? (RARC and other fields are checked and reported separately,
   not folded into the score — see the comment above `WEIGHT_*` in
   `eval/score.py` for why.)
3. **Appeal completeness** — does the drafted letter actually reference
   the specific facts (claim ref, codes, dates, NPIs) the ground truth
   says it must, checked deterministically (substring matching against
   known values, not an LLM judge — a regression gate needs to be cheap
   and repeatable, not another paid API call).

Each run writes an `eval_runs` row (score, full breakdown, the exact git
commit that produced it) and compares against the previous run, flagging
a regression if accuracy dropped more than 5 percentage points. The
`/dashboard` view in the frontend shows this as a live status banner
plus a trend chart, not just a number in a log.

### Token & cost tracking

Every LLM call captures its real token usage (from the Anthropic API
response) and an estimated dollar cost, written to a `token_usage` table
keyed by pipeline stage and denial. `GET /api/usage` exposes totals, a
per-stage breakdown, and a per-client comparison — visible live on the
`/dashboard` view. This is the app's own operating cost, tracked the
same way anything running in production would need to be.

## Repo layout

```
backend/
  db/
    models.py          # SQLAlchemy models — the schema (see below)
    session.py          # engine/session, reads DATABASE_URL
    seed.py              # loads a denials JSON file into Postgres
  data/
    denials_synthetic.json                          # 48 synthetic denial letters (Meridian Eye Care Partners)
    eval_labeled.json                               # 24-record labeled ground-truth subset
    generate_synthetic_data.py                       # re-runnable, deterministic generator
    denials_summit_dme_providers.json                # 14 synthetic denial letters (Summit DME Providers)
    generate_synthetic_data_summit_dme_providers.py  # re-runnable, deterministic generator
  profiles/               # CompanyProfile abstraction — see "Company profiles" above
    base.py
    meridian_eyecare_partners.py
    summit_dme_providers.py
  pipeline/               # extract.py, classify.py, draft_appeal.py, run.py, common.py
  eval/                   # score.py, run_eval.py — deterministic regression harness
  api/
    schemas.py             # Pydantic request/response models
    routes/                 # health, denials, eval, profiles, usage, analytics, demo
  main.py                 # FastAPI app instance, CORS, router mounting
  alembic/                # migrations
  requirements.txt
  .env.example
frontend/
  src/
    api/                   # types.ts, client.ts — typed API client
    components/             # StatusPill, ConfidenceBadge, KeyValueGrid, CorrectionForm, charts, loading/error/empty states
    pages/
      QueueView.tsx          # denial worklist — filters, table, pagination
      DetailView.tsx           # the reviewer workspace — see "Frontend" below
      NewDenialView.tsx         # manual "New Denial" create form
      DashboardView.tsx          # monitoring dashboard — eval trend, confidence distribution, cost
      ProfilesView.tsx            # multi-client profile comparison + live processing
    App.tsx                 # routing + top nav (incl. dark mode toggle)
    index.css                # design system (Tailwind v4 @theme block)
  .env.example
docker-compose.yml        # Postgres only
```

### Database schema

`denials` (one row per claim-denial letter) is the root table; everything
else references it by `denial_id`:

| Table | Holds |
|---|---|
| `denials` | The letter itself, which client it belongs to, current status |
| `extractions` | Structured fields pulled out per run, plus raw model output for audit |
| `classifications` | Category + confidence per run |
| `appeals` | Drafted letter text + current review status (mutable "latest state") |
| `corrections` | The unified audit-event log — see [Audit trail](#audit-trail) |
| `eval_runs` | Regression-harness results over time |
| `token_usage` | Per-call token/cost accounting |

## Setup

### 1. Start Postgres

```bash
docker compose up -d
```

Brings up `postgres:16-alpine` on host port **5555** (not the default
5432, to avoid colliding with anything else already running), database
`claims_triage`, user `appuser`. See `docker-compose.yml` for
credentials (dev-only).

### 2. Python environment

```bash
cd backend
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set ANTHROPIC_API_KEY; adjust DATABASE_URL if you changed docker-compose.yml
```

### 3. Run migrations

```bash
cd backend
alembic upgrade head
```

### 4. Seed synthetic data

```bash
python backend/db/seed.py
python backend/db/seed.py backend/data/denials_summit_dme_providers.json
```

Idempotent — safe to re-run, skips claim refs that already exist.

### 5. Start the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Serves on `http://127.0.0.1:8000`. Interactive API docs at `/docs`.

### 6. Start the frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # VITE_API_BASE_URL=http://localhost:8000/api
npm run dev
```

Serves on `http://localhost:5173` (or the next free port — CORS allows
any localhost port, so this doesn't require reconfiguration either way).

### Regenerating synthetic data

```bash
python backend/data/generate_synthetic_data.py
```

Deterministic (fixed seed) — produces byte-identical output on re-run.
Only rewrites the JSON files; run `seed.py` again to load the result.

## Synthetic data

- 48 denial letters (client A) + 14 (client B), evenly spread across all
  six classification categories.
- Every letter uses real, currently-active CARC/RARC codes (Claim
  Adjustment Reason Codes / Remittance Advice Remark Codes), verified
  against the official X12 code lists — not invented.
- Two writing styles per letter (terse EOB-style vs. longer narrative
  review letter), randomly assigned, so the dataset isn't one brittle
  format.
- All patient references, claim numbers, NPIs, payer names, and dollar
  amounts are synthetic. No real names, no real PHI, anywhere.

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness + DB connectivity check |
| GET | `/api/denials` | Paginated worklist, filter by `source_company`/`status` |
| GET | `/api/denials/{id}` | Full detail: raw text, extraction, classification, appeal, audit history |
| POST | `/api/denials` | Manually create a denial (paste-in-a-letter flow) |
| POST | `/api/denials/{id}/process` | Runs the full pipeline (real API cost); safe to re-run on an already-processed denial |
| POST | `/api/denials/{id}/appeal/draft` | Runs only the appeal-drafting stage, honoring any classification correction on record |
| POST | `/api/denials/{id}/appeal/status` | Approve/reject/mark-sent — updates current state and appends a permanent audit event |
| POST | `/api/denials/{id}/corrections` | Logs a human correction to any AI-produced field |
| GET | `/api/eval/runs` | Regression-harness history, newest first |
| POST | `/api/eval/run` | Triggers a new eval run (no LLM calls) |
| GET | `/api/profiles` | Lists registered company profiles |
| GET | `/api/profiles/{key}` | Full profile detail — extraction schema, category taxonomy, appeal guidance |
| GET | `/api/usage` | Token/cost totals, by-stage and by-client breakdowns |
| GET | `/api/analytics/confidence-distribution` | Live classification-confidence histogram |
| POST | `/api/demo/reset-sample` | Test-utility only, not for production use: resets one already-processed denial per client back to `new`, so the live pipeline can be re-triggered on demand |

## Frontend

- **Queue** (`/denials`) — worklist with company/status filters, real
  pagination, status pills.
- **Detail** (`/denials/:id`) — the reviewer's workspace: original
  letter, extracted fields, classification + confidence bar, drafted
  appeal, approve/reject actions, a correction form, and the full audit
  history — all in one view.
- **New Denial** (`/denials/new`) — paste in a letter, pick a client,
  create a record to process.
- **Dashboard** (`/dashboard`) — eval accuracy trend + regression
  status, confidence distribution, token/cost usage.
- **Profiles** (`/profiles`) — side-by-side client comparison, plus a
  live comparison that reprocesses a real denial from each client on
  demand, using a clearly-labeled test-utility endpoint (see [API
  reference](#api-reference)) rather than a general-purpose data-reset
  feature.

Built with React + TypeScript + Vite, Tailwind CSS v4 (a single `@theme`
block in `index.css` — no separate config file, colors/spacing defined
once as CSS custom properties), React Router, and TanStack React Query
for data fetching (loading/error/retry states and cache invalidation
handled by the library, not hand-rolled). Supports light/dark mode
(toggle in the top nav, defaults to OS preference, persisted after an
explicit choice) and is responsive from mobile widths up through
ultrawide monitors.

## Path to production

This system is architecturally ready for the pieces below — the audit
trail, eval/regression gate, and profile abstraction were built with
these in mind — but none of them are implemented. Being explicit about
the gap matters more than pretending it isn't there:

### Security & access control
- **No authentication or authorization exist.** Every API endpoint is
  open. A real deployment needs real identity (SSO/OIDC against the
  operating company's existing directory) and role-based access —
  reviewers, compliance staff, and admins are not the same role and
  shouldn't have the same permissions (e.g. only compliance should be
  able to see the full audit trail across all reviewers; only a
  reviewer assigned to a client should see that client's queue).
- **Secrets management.** The Anthropic API key and DB credentials live
  in a local `.env` file. Production needs a real secrets manager
  (e.g. AWS Secrets Manager, Vault) and rotation, not a file on disk.

### Integration
- **No connection to any real claims/billing/EHR system.** This reads a
  denial letter as pasted-in text and writes nothing back anywhere —
  there is no live integration with a practice management system,
  clearinghouse, or payer portal. That's a real, separate integration
  project per client, not an extension of this codebase.
- **Medical-necessity appeals need clinical documentation this system
  doesn't have.** It only ever reads the denial letter itself — a
  production version arguing medical necessity persuasively would need
  read access to the relevant chart notes from the practice's EHR.

### Compliance
- **PHI handling.** This system was built and tested entirely on
  synthetic data by design. Touching real patient data requires a
  signed BAA with the model provider and a real HIPAA compliance
  review before anything here processes a real record.
- **No data retention/deletion policy** implemented — a real deployment
  needs one, especially for an immutable audit log holding PHI.

### Reliability & scale
- **Synchronous processing.** `POST /.../process` blocks on a live
  ~20-30 second LLM call chain. Production needs this moved to a
  background job queue (e.g. Celery/RQ) with the frontend polling or
  subscribing for status, not holding an HTTP connection open.
- **No rate limiting or cost caps** on pipeline usage.
- **Single instance, no redundancy** — one Postgres, one API process.
  Production needs a managed, replicated database and horizontally
  scaled API instances behind a load balancer.
- **No CI/CD.** The eval harness exists and is cheap to run — the
  missing piece is wiring it into a pipeline that blocks a prompt or
  model change from merging if it regresses accuracy.
- **Observability.** No structured logging or error monitoring
  (e.g. Sentry) wired in — right now, debugging a production issue
  would mean reading raw process logs by hand.

### Known accuracy gap
- **RARC (remark code) extraction accuracy is weak** (~12% in eval,
  vs. 100% for CARC codes) — flagged, not hidden. CARC extraction is
  reliable; RARC needs targeted prompt work before it should be
  trusted on real cases.
- **No judgment on whether the original denial was valid.** See "What
  it does" above — the system always attempts an appeal once
  classification confidence clears the threshold; it does not assess
  whether the payer's denial was actually correct.

### A realistic rollout, not a flip of a switch
Even with the above built, going live wouldn't mean turning this on for
every denial at once: start in shadow mode (AI drafts, a human reviews
100% of output) on one denial category for a few weeks, track agreement
rate against what reviewers would have done manually, then reduce review
sampling and expand categories one at a time as accuracy holds — the
same phased-rollout logic the eval harness and confidence gate here are
already built to support.
