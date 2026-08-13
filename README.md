# Claims Denial Triage + Appeal Drafting Demo

A demo AI claims-denial-triage system, built to showcase production-grade
AI engineering practices: structured extraction with forced tool use,
an eval harness with regression detection, a full immutable audit trail,
and a multi-tenant company-profile architecture.

**Status: Phase 1-10 done, plus manual denial creation, reprocess-from-detail-view,
and a unified immutable audit-event log covering corrections, appeal-review
decisions, AND the AI pipeline's own extraction/classification/appeal-drafting
actions (see "Audit history — a unified, immutable event log" and "AI-action
audit events" below).** This repo holds a
pipeline that ingests insurance claim-denial letters, extracts structured
fields, classifies the denial reason, and drafts an appeal letter, with a
Postgres-backed audit trail and a deterministic eval/regression harness. The
pipeline is profile-driven and currently drives two client companies'
claim types (eye-care and DME) off one shared codebase, is exposed over a
FastAPI REST layer, and is reviewable through a React/TypeScript queue +
detail UI with a monitoring dashboard, a live, side-by-side multi-company
demo, and a "New Denial" flow for pasting in a real denial letter live (see
"Manual denial creation" below).

- **Phase 1** — the Postgres schema (`denials`, `extractions`,
  `classifications`, `appeals`, `corrections`, `eval_runs`, `token_usage`; the
  `corrections` table was later extended into a unified, immutable
  audit-event log covering both corrections and appeal-review decisions —
  see "Audit history" below),
  defined as SQLAlchemy models with an Alembic migration; a 48-record
  synthetic dataset of realistic ophthalmology claim-denial letters for a
  fictional company, "Meridian Eye Care Partners," plus a 24-record
  labeled subset for regression-testing the eval harness; a seed script to
  load the synthetic dataset into Postgres.
- **Phase 2** — `backend/pipeline/` (`extract.py`, `classify.py`,
  `draft_appeal.py`, `run.py`, `common.py`): a real Anthropic-API pipeline
  that takes a denial from `status="new"` through extraction, classification,
  and (confidence permitting) appeal drafting, with per-call token/cost
  accounting (`token_usage`) and a confidence-gated `needs_review` routing
  path. Runnable as `python -m pipeline.run --all` from `backend/`.
- **Phase 3** — `backend/eval/` (`score.py`, `run_eval.py`): a deterministic
  eval harness that scores the pipeline's persisted results against
  `eval_labeled.json`'s ground truth and writes a regression-checked
  `eval_runs` row. See "Phase 3 — Evaluation" below.
- **Phase 4** — `backend/profiles/`: refactored the Phase 2 pipeline to be
  driven by a `CompanyProfile` (extraction schema, prompts, appeal guidance)
  resolved from `denials.source_company`, instead of hardcoded
  Meridian-Eye-Care-Partners text, and added a second company profile,
  "Summit DME Providers" (a fictional national DME/CRT provider), with its own
  synthetic dataset. Proves the architecture generalizes to a genuinely
  different claim type on the same pipeline code. See "Phase 4 —
  Multi-Company Profiles" below.
- **Phase 5** — `backend/api/`: a FastAPI REST layer over the pipeline, eval
  harness, profiles, and usage data (denial worklist/detail, on-demand
  processing, appeal review actions, corrections audit trail, eval-run
  history, token/cost usage reporting). See "Phase 5 — API" below.
- **Phase 6** — `frontend/`: a React + TypeScript + Vite review UI (queue
  view + detail/review view) consuming the Phase 5 API, with React Query for
  data fetching and Tailwind CSS for a small, consistent design system. See
  "Phase 6 — Frontend (Queue + Review)" below.
- **Phase 7** — `frontend/src/pages/DashboardView.tsx` (`/dashboard`): a
  monitoring dashboard over the eval harness, live classification-confidence
  distribution, and token/cost usage, plus a new
  `GET /api/analytics/confidence-distribution` endpoint. See "Phase 7 —
  Monitoring Dashboard" below.
- **Phase 8** — `frontend/src/pages/ProfilesView.tsx` (`/profiles`): a
  side-by-side company-profile comparison and a live, on-demand two-company
  processing demo (real Anthropic API calls triggered from the browser),
  backed by a new `GET /api/profiles/{key}` detail endpoint and an explicitly
  demo-scoped `POST /api/demo/reset-sample` endpoint. See "Phase 8 —
  Multi-Company Live Demo" below.
- **Phase 10** — dark mode: a manual light/dark toggle in the top nav
  (`frontend/src/App.tsx`), defaulting to OS `prefers-color-scheme` on first
  load and persisted to `localStorage` once explicitly chosen, applied via a
  `.dark` class on `<html>` with real per-token dark values (not an
  invert filter) for every color in `index.css`'s `@theme` block, including
  the dashboard's charts. See "Phase 10 — Dark Mode" below.
- **Phase 9** — full-stack cold-start rehearsal: killed every running
  process, brought Postgres/backend/frontend back up strictly by following
  this README's own steps, and clicked through the entire application in a
  real browser exactly as a real user would (queue filters/pagination, both
  companies' detail views, a real correction, the dashboard, the profiles
  comparison, and the live demo-reset-and-process flow for both companies)
  with the console checked clean at 1920x1080 and 1440x900. Caught and fixed
  one real bug this way -- see "Phase 9 — Cold-Start Verification" below.

## Repo layout

```
app/
  backend/
    db/
      models.py          # SQLAlchemy models (the schema)
      session.py          # engine/session, reads DATABASE_URL
      seed.py              # loads a denials JSON file into Postgres (any company)
    data/
      denials_synthetic.json                    # 48 synthetic MEC denial letters
      eval_labeled.json                         # 24-record labeled subset (MEC, ground truth + required appeal elements)
      generate_synthetic_data.py                # re-runnable, seeded generator that produces the two files above
      denials_summit_dme_providers.json              # 14 synthetic Summit DME Providers (DME) denial letters
      generate_synthetic_data_summit_dme_providers.py # re-runnable, seeded generator for the DME dataset
    profiles/                     # Phase 4: CompanyProfile abstraction (see below)
      base.py
      meridian_eyecare_partners.py
      summit_dme_providers.py
    alembic/                      # migrations (one initial migration, matches models.py)
    requirements.txt
    .env.example
  frontend/                       # Phase 6: React + TypeScript + Vite review UI
    src/
      api/
        types.ts                    # TypeScript interfaces mirroring api/schemas.py
        client.ts                    # typed fetch wrapper (api.listDenials, api.processDenial, ...)
      components/                   # StatusPill, ConfidenceBadge, KeyValueGrid, CorrectionForm, Modal, loading/error/empty states
      pages/
        QueueView.tsx                # denial worklist: filters, table, pagination
        DetailView.tsx                 # the reviewer workspace (see below)
        DashboardView.tsx              # Phase 7: eval/confidence/usage monitoring dashboard
        ProfilesView.tsx                # Phase 8: multi-company profile comparison + live demo
        NewDenialView.tsx                # manual "New Denial" create form (/denials/new)
      App.tsx                       # routing + top nav
      index.css                     # design system (Tailwind v4 @theme block)
    .env.example
  docker-compose.yml              # Postgres only
  README.md
```

## Setup

### 1. Start Postgres

```bash
docker compose up -d
```

(`docker-compose`, the standalone hyphenated binary, works too if you have
it installed, but the `docker compose` subcommand form is the one bundled
with current Docker installs and is what these instructions were verified
against.)

This brings up a single `postgres:16-alpine` container on **host port
5555** (not the Postgres default 5432 — picked to avoid colliding with any
Postgres already running on the dev machine), with a named volume
(`denial_appeal_pgdata`) for persistence and a healthcheck. Database:
`claims_triage`, user: `appuser`. See `docker-compose.yml` for credentials
(dev-only, not for anything resembling production use).

### 2. Python environment

```bash
cd backend
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # adjust DATABASE_URL if you changed docker-compose.yml
```

`requirements.txt` uses `>=` floors rather than hard pins — `psycopg2-binary`
does not currently ship prebuilt wheels for very new CPython releases, so
this repo depends on `psycopg[binary]` (psycopg 3) instead, and pins are
left loose enough for `pip` to resolve versions with available wheels for
whatever interpreter you're on.

### 3. Run the migration

```bash
cd backend
alembic upgrade head
```

`alembic/env.py` reads `DATABASE_URL` from the environment (via
`db/session.py`, which loads `.env`), so make sure step 2's `.env` is in
place, or export `DATABASE_URL` directly:

```bash
DATABASE_URL="postgresql+psycopg://appuser:app_dev_password@localhost:5555/claims_triage" alembic upgrade head
```

### 4. Seed the synthetic dataset

```bash
python backend/db/seed.py
```

Loads all 48 denials from `backend/data/denials_synthetic.json` into the
`denials` table (`source_company = "meridian_eyecare_partners"`,
`status = "new"`). Idempotent — re-running skips rows whose `claim_ref`
already exists rather than duplicating them. Pass a different path to seed
another company's dataset, e.g.
`python backend/db/seed.py backend/data/denials_summit_dme_providers.json`.

### Regenerating the synthetic dataset

```bash
python backend/data/generate_synthetic_data.py
```

Deterministic (fixed random seed) — re-running produces byte-identical
output. Regenerate after editing the payer/procedure/diagnosis pools or
sentence templates in that script. This only rewrites the two JSON files;
it does not touch the database — run `seed.py` again afterward if you want
the new data loaded (note the current idempotency key is `claim_ref`, so if
you change the generator's random seed you'll get a new set of claim refs
and end up with both old and new rows in the database unless you truncate
`denials` first).

## Synthetic data notes

- 48 denial letters, evenly split (8 each) across the six classification
  categories: `coding_error`, `missing_information`, `medical_necessity`,
  `timely_filing`, `eligibility`, `duplicate_claim`.
- Every letter uses real, currently-active CARC (Claim Adjustment Reason
  Code) and RARC (Remittance Advice Remark Code) values, verified against
  the X12 code lists at x12.org/codes — see the comments above
  `CATEGORIES` in `generate_synthetic_data.py` for the specific codes used
  and their source.
- Two writing styles per letter (terse EOB-style vs. longer narrative
  manual-review letter), randomly assigned, to avoid the dataset looking
  like one brittle format.
- All patient references, claim numbers, NPIs, payer names, and dollar
  amounts are synthetic. No real names, no real PHI.
- `eval_labeled.json` is a 24-record subset (evenly spread across
  categories) with ground-truth `category`/CARC/RARC and a
  `required_appeal_elements` list per record, built from that record's
  actual generated values (claim number, CPT code, physician NPI, etc.) —
  not generic boilerplate.

## Phase 3 — Evaluation

`backend/eval/` is a deterministic regression harness for the Phase 2
pipeline. It makes **no LLM calls** — it only reads what the pipeline already
wrote to Postgres and compares it to `backend/data/eval_labeled.json`'s
hand-labeled ground truth, so it's cheap and safe to re-run on every change.

### Running it

```bash
cd backend
python -m eval.run_eval
```

This scores the 24 labeled denials against their existing DB rows
(`extractions`, `classifications`, `appeals` — it does **not** re-run the
pipeline; if a labeled denial's rows are genuinely missing, that's reported
as a data issue, not silently re-processed), prints the score breakdown,
writes a new `eval_runs` row, and compares against the most recent prior
`eval_runs` row to flag a regression. `python -m eval.score` runs just the
scoring step and dumps the full JSON breakdown to stdout, without touching
the database.

### The three scoring dimensions

1. **Classification accuracy** — binary, per denial: does
   `classifications.category` exactly match `eval_labeled.json`'s
   `ground_truth_category`?
2. **Extraction accuracy** — binary, per denial: does
   `extractions.extracted_fields['carc_code']` exactly match
   `ground_truth_carc_code`? RARC match, and claim_ref/patient_ref sanity
   checks against values regexed directly out of the denial's own
   `raw_text` (independent of anything the pipeline produced), are also
   computed and reported, but only the CARC match feeds the weighted score
   — see `eval/score.py` for why RARC is reported separately (the synthetic
   letters never state a RARC code in their `raw_text`, so
   `ground_truth_rarc_code` isn't something a letter-grounded extractor
   could ever legitimately recover; scoring it into the same number as CARC
   would make a correctly-behaving extractor look broken).
3. **Appeal completeness** — for each denial's `required_appeal_elements`,
   the harness extracts the literal facts embedded in that requirement's own
   text (claim/patient/prior-auth refs, CPT/ICD-10/CARC codes, dates, NPIs)
   and checks each is a substring of the drafted appeal letter. A
   requirement with no extractable literal (e.g. "must address the timely
   filing gap directly") is reported separately as "unverifiable" rather
   than scored pass/fail — the harness deliberately does not use an LLM
   judge to assess free-form argument quality; that would defeat the point
   of a cheap, deterministic regression gate. Only denials that reached
   `appeal_drafted` are scored on this dimension; denials routed to
   `needs_review` (low classification confidence) have no appeal to check
   and are reported as a separate count, not folded in as an implicit zero.

The overall score is `0.4 * classification_accuracy + 0.3 * extraction_accuracy
+ 0.3 * appeal_completeness` — classification is weighted highest because a
wrong category drives the `needs_review` routing decision and the
category-specific appeal-drafting guidance, so it tends to cascade into
downstream errors even when extraction and drafting both work correctly. See
the comment above `WEIGHT_CLASSIFICATION` in `eval/score.py` for the full
reasoning.

### The `eval_runs` row

Each run inserts one row: `accuracy_score` (the overall weighted score),
`details` (the full JSON breakdown — per-dimension aggregates and a
per-denial list with predicted vs. ground truth, missing/unverifiable appeal
elements, etc.), `git_commit` (`git rev-parse HEAD` at run time, so a score
is always traceable to the exact code that produced it), and `run_at`.

### Regression threshold

`run_eval.py` compares the new run's `accuracy_score` against the most
recent prior `eval_runs` row (skipped gracefully if there isn't one — e.g.
the very first run) and flags a regression if the score dropped by more than
**5 percentage points**. With only 24 labeled examples, a single denial
flipping from correct to incorrect on classification alone already moves the
weighted score by ~1.7pp, so the threshold needs to sit above that
single-flip noise floor while still catching a real regression (e.g. a
prompt change that breaks a whole category, typically a double-digit-pp
move). See the comment above `REGRESSION_THRESHOLD_PP` in `eval/run_eval.py`
for the full reasoning — this is a starting point tuned by judgment, not a
statistically derived value, and the right long-term fix if it proves noisy
is a larger labeled set, not just retuning the number.

## Phase 4 — Multi-Company Profiles

The Phase 2 pipeline (`extract.py`/`classify.py`/`draft_appeal.py`) was
originally built with Meridian Eye Care Partners' extraction schema and
prompt text hardcoded directly into those three files. Phase 4 pulls all of
that company-specific configuration out into `backend/profiles/`, so the
same pipeline code drives multiple client companies, and adds a second
profile — "Summit DME Providers," a fictional national complex rehab technology
(CRT) / durable medical equipment (DME) provider — to prove it's a real
abstraction and not just a plan for one.

### How the profile system works

`backend/profiles/base.py` defines `CompanyProfile`, a frozen dataclass
holding everything that varies per company:

- `key` / `display_name` — `key` must exactly match the `source_company`
  value on that company's `denials` rows; it's the lookup key.
- `extraction_tool` — the full Anthropic tool schema (name, description,
  `input_schema`) forced via `tool_choice` in stage 1. Different companies
  have genuinely different structured fields (e.g. `cpt_code` vs.
  `hcpcs_code`, and DME-only fields like `equipment_type` and
  `lmn_reference_number` for a Letter of Medical Necessity reference — a
  real DME-specific document requirement eye-care claims have no equivalent
  of). `extraction_required_fields` is derived from the schema's
  `required` array, not duplicated by hand.
- `extraction_system_prompt` — company/domain framing for stage 1.
- `classification_system_prompt_intro` + `category_guide` — company framing
  and a CARC-code guide for stage 2, combined by
  `classification_system_prompt()`.
- `appeal_guidance` (per category) + `appeal_system_prompt_template` +
  `appeal_grounding_fields` — stage 3's per-category argument guidance, the
  system-prompt template (filled in via `appeal_system_prompt(category)`),
  and which extracted fields the drafted letter is checked against for
  grounding.

What deliberately does **not** vary per profile: the six
`CLASSIFICATION_CATEGORIES` in `db/models.py`
(`coding_error`/`missing_information`/`medical_necessity`/`timely_filing`/
`eligibility`/`duplicate_claim`) and the classification tool's JSON schema
(`classify.py`'s `CLASSIFICATION_TOOL`) are shared across every profile —
they're genuine root-cause buckets for any healthcare claim denial, not
eye-care- or DME-specific, so a new profile should adjust the CARC-code
guide and appeal guidance text, not invent new categories.

`backend/profiles/__init__.py` registers each company's `PROFILE` in a
`PROFILES` dict and exposes `get_profile(source_company)`. `pipeline/run.py`
resolves the profile once per denial (`get_profile(denial.source_company)`)
and passes it into `extract_denial()`, `classify_denial()`, and
`draft_appeal()`, which use it to build their tool schema/prompts instead of
referencing hardcoded module-level constants.

### Adding a third company profile

1. Create `backend/profiles/<new_company_key>.py`, using
   `meridian_eyecare_partners.py` or `summit_dme_providers.py` as a
   template: define `EXTRACTION_TOOL`, `EXTRACTION_SYSTEM_PROMPT`,
   `CLASSIFICATION_SYSTEM_PROMPT_INTRO` + `CATEGORY_GUIDE`, and
   `APPEAL_GUIDANCE` + `APPEAL_SYSTEM_PROMPT_TEMPLATE`, then build a
   module-level `PROFILE = CompanyProfile(...)`.
2. Register it in `PROFILES` in `backend/profiles/__init__.py`.
3. Add a synthetic denial dataset under `backend/data/` (a generator script
   following `generate_synthetic_data_summit_dme_providers.py`'s pattern is the
   easiest way to get varied, non-mail-merged letters), with
   `source_company` matching the new profile's `key` exactly.
4. Seed it: `python backend/db/seed.py backend/data/denials_<new_company>.json`.

Nothing in `pipeline/*.py` needs to change — extraction/classification/
appeal-drafting all resolve their behavior from the `CompanyProfile` at
runtime.

### Running the pipeline against a specific profile

```bash
cd backend
python -m pipeline.run --all --source-company summit_dme_providers
python -m pipeline.run --all --source-company meridian_eyecare_partners
python -m pipeline.run --all   # every source_company's status="new" denials
python -m pipeline.run --denial-id <uuid>   # single denial; profile is
                                             # resolved automatically from
                                             # that denial's source_company
```

### Summit DME Providers (DME) dataset

`backend/data/denials_summit_dme_providers.json` — 14 synthetic denial letters
(`source_company = "summit_dme_providers"`), generated by
`generate_synthetic_data_summit_dme_providers.py` (deterministic, fixed seed,
same varied-prose approach as the MEC generator: terse EOB-style vs.
narrative manual-review letters, randomly assigned). Category distribution:
`coding_error` (3), `missing_information` (3), `medical_necessity` (2),
`timely_filing` (2), `eligibility` (2), `duplicate_claim` (2). Equipment
types are varied across the set: manual and power wheelchairs, CPAP/BiPAP
devices, a semi-electric hospital bed, a custom ankle-foot orthosis, and a
microprocessor-knee lower-limb prosthesis. CARC codes are the same
verified, X12-maintained codes used in the MEC dataset (CARCs are generic
across specialties, not eye-care- or DME-specific) — re-verified against
x12.org/codes for this phase. HCPCS Level II equipment codes (K0823, E1130,
E0601, E0470, E0260, L1960, L5856) were verified against
AAPC/CMS-coding-reference sources.

### Verification

Ran the refactored pipeline for real against the Anthropic API for both
profiles: all 14 Summit DME Providers denials (12 reached `appeal_drafted`, 2
correctly routed to `needs_review` on low classification confidence — the
existing 0.7 threshold behavior, unchanged), and a 3-denial MEC spot-check
(re-run through the refactored code) confirmed extraction/classification/
appeal output is unchanged in character from before the refactor — eye-care
CPT/diagnosis language, no DME terms. The DME outputs were checked for the
reverse: `extracted_fields` show `hcpcs_code`/`equipment_type`/
`lmn_reference_number` (never `cpt_code`), and drafted appeals cite HCPCS
codes, equipment type, and LMN/CMN documentation rather than eye-care
language — confirming the profile switch actually changes model behavior
rather than the DME data just flowing through MEC-flavored prompts.

## Phase 5 — API

`backend/api/` + `backend/main.py`: a FastAPI app exposing the Phase 1-4
pipeline, eval harness, company profiles, and token-usage accounting over
REST. This is the layer the (not-yet-built) React frontend consumes.

### Running it

```bash
cd backend
source ../.venv/bin/activate   # or wherever you created the venv
uvicorn main:app --reload
```

Serves on `http://127.0.0.1:8000` by default. Interactive docs at
`/docs` (Swagger UI) and `/openapi.json`. CORS allows any `localhost`/
`127.0.0.1` port via regex (see the comment above `CORSMiddleware` in
`main.py`), not just Vite's default `5173` -- Vite silently picks the next
free port (`5174`, `5175`, ...) if `5173` is already in use by something
else on the machine, so a hardcoded single-port allowlist would break
intermittently depending on what else is running.

### Structure

```
backend/
  main.py               # FastAPI() app instance, CORS, router mounting
  api/
    deps.py              # get_db() -- per-request SQLAlchemy session
    schemas.py            # Pydantic request/response models
    routes/
      health.py            # GET /api/health
      denials.py            # denial list/detail, process, review actions
      eval.py                # eval-run history + trigger
      profiles.py             # company profile listing
      usage.py                  # token/cost usage reporting
```

Pydantic models in `api/schemas.py` are deliberately separate from the
SQLAlchemy models in `db/models.py` — they describe the wire contract with
the frontend (e.g. list-view booleans like `has_classification`/`has_appeal`
that don't exist as DB columns), not the DB schema.

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness + DB connectivity check. |
| GET | `/api/denials` | Paginated denial worklist; filter by `source_company`, `status`. |
| GET | `/api/denials/{id}` | Full detail: raw_text, extraction, classification, appeal, `audit_events` — one call, not four. See "Audit history — a unified, immutable event log" below for what `audit_events` is. |
| POST | `/api/denials/{id}/process` | Runs the real extract→classify→draft_appeal pipeline for this one denial on-demand (real Anthropic API cost). |
| POST | `/api/denials/{id}/appeal/draft` | Runs *only* the appeal-drafting stage against the denial's current extraction + classification — no re-extraction, no re-classification. See "Draft Appeal Letter (detail view)" below for why this exists and how it picks up a human classification correction. |
| POST | `/api/denials/{id}/appeal/status` | Human review action: updates the appeal row's `status`/`reviewer`/`reviewed_at` in place (current-state display) **and** appends a permanent `appeal_review` audit event recording the decision — see "Audit history" below. |
| POST | `/api/denials/{id}/corrections` | Logs a human correction to an AI-produced field — the compliance audit-trail feature; appends an `event_type="correction"` row to the same unified audit-event log, does not mutate the original AI output (with one deliberate exception — see "Draft Appeal Letter (detail view)" below). |
| GET | `/api/eval/runs` | Eval-run history, newest first (for the regression-tracking chart). |
| POST | `/api/eval/run` | Triggers a new eval run against current DB contents (no LLM calls — see Phase 3) and writes a new `eval_runs` row. |
| GET | `/api/profiles` | Lists registered company profiles (`key`, `display_name`) — backs the frontend's profile switcher. |
| GET | `/api/usage` | Token/cost summary, optional `source_company` filter: totals, breakdown by pipeline stage, and a by-day time series. |

### Verification

Started the server for real (`uvicorn main:app`) against the live Postgres
instance with existing seeded/processed data (48 MEC + 14 DME denials, one
prior `eval_runs` row) and exercised every endpoint with `curl`:

- `GET /api/health` → `{"status":"ok","database":"ok"}`.
- `GET /api/denials?source_company=meridian_eyecare_partners` → real
  denials with correct `has_classification`/`has_appeal` flags.
- `GET /api/denials/{id}` → full detail with populated extraction (all
  extracted fields + model/prompt version), classification (category +
  confidence), and appeal (full draft text) for a real denial.
- `POST /api/denials/{id}/corrections` → 201 with the new row, then
  independently re-queried via a direct DB script (not just the HTTP
  response) to confirm the row was actually persisted.
- `POST /api/denials/{id}/appeal/status` → updated `status`/`reviewer`/
  `reviewed_at`, confirmed via the same direct DB re-query.
- `POST /api/denials/{id}/process` → real pipeline run against the
  Anthropic API, returned `appeal_drafted`; a bogus id correctly 404s.
- `POST /api/eval/run` → wrote a new `eval_runs` row (`id=2`,
  `accuracy_score=0.95`, tied to the current git commit); `GET
  /api/eval/runs` showed both rows, newest first.
- `GET /api/profiles` → both `meridian_eyecare_partners` and
  `summit_dme_providers`.
- `GET /api/usage` and the `source_company`-filtered variants → totals
  cross-checked exactly against a direct DB aggregate query run beforehand:
  MEC `$2.234616`, DME `$0.682545` (matches known prior-phase totals).
- `GET /docs` and `/openapi.json` both return 200.

## Phase 6 — Frontend (Queue + Review)

A React + TypeScript + Vite app in `frontend/` that consumes the Phase 5
API: a denial queue (worklist) view and a detail/review view, which is the
"reviewer's workspace" the whole project builds up to — original letter,
AI extraction, AI classification with a confidence indicator, the drafted
appeal, and a real correction/audit-trail workflow, side by side.

### Stack

- **React 19 + TypeScript + Vite**, scaffolded with `npm create vite@latest
  -- --template react-ts`.
- **Tailwind CSS v4** (`@tailwindcss/vite` plugin) for styling. Tailwind v4
  is CSS-first — there is no `tailwind.config.ts`; the design system lives
  in a single `@theme` block at the top of `src/index.css` instead, which is
  the v4-idiomatic equivalent of a config-file theme extension (colors,
  radii, shadows defined once as CSS custom properties, consumed everywhere
  as ordinary Tailwind utility classes like `bg-brand-600` or
  `text-status-needs_review-fg`).
- **React Router** (`react-router-dom`) for the two top-level views
  (`/denials`, `/denials/:id`) — deliberately simple, no nested router.
- **TanStack React Query** for all data fetching: loading/error/retry states
  come from the library instead of hand-rolled `useEffect`/`useState`, and
  mutations (process, appeal status, corrections) invalidate the relevant
  query keys so the UI reflects the server state after every action without
  manual refetch plumbing.

### Design system

Defined once in `src/index.css`'s `@theme` block, not redefined per
component:

- **Color** — a restrained slate-blue brand/accent (`brand-50`…`900`), a
  cool-gray neutral/ink scale for text and surfaces (`ink-50`…`900`), and a
  dedicated **semantic status palette**: one background/foreground pair per
  `denials.status` value (`new`, `processing`, `classified`,
  `appeal_drafted`, `needs_review`, `closed`) plus the separate
  `appeals.status` values (`draft`, `approved`, `rejected`, `sent`), each
  legible as a pill. A separate 3-step `confidence-low/mid/high` scale (red
  / amber / green) drives the classification confidence bar independently
  of the status palette.
- **Typography** — Inter (Google Fonts, loaded in `index.html`), system-ui
  fallback stack.
- **Spacing/shape** — one `--radius-card` (cards) and `--radius-pill`
  (status pills) token, one card shadow token, reused via a small set of
  `@layer components` classes (`.card`, `.btn-primary/secondary/danger/
  success`, `.input`, `.label`) instead of ad hoc utility strings scattered
  across components.

### Views

- **Queue (`/denials`)** — table of denials from `GET /api/denials`, with
  company (`GET /api/profiles`) and status filter dropdowns, a colored
  status pill per row, and real pagination driven by the API's
  `total`/`page`/`page_size` response fields (not a client-side slice of a
  single fetched page). Skeleton loading state, an explicit empty state
  ("no denials match these filters"), and an error state that surfaces the
  actual failure reason instead of a blank screen.
- **Detail (`/denials/:id`)** — `GET /api/denials/{id}` rendered as: the raw
  denial letter (evidence panel), extracted fields as a labeled key-value
  grid (not raw JSON), classification category + a color-coded confidence
  bar (low confidence reads visually as "needs attention"), and the drafted
  appeal letter directly below the extraction/classification, so a reviewer
  can compare the original letter against the AI's output at a glance.
  Actions: **Approve/Reject appeal** (`POST
  /api/denials/{id}/appeal/status`); **Process with AI** for `status="new"`
  denials (`POST /api/denials/{id}/process`), with a persistent in-progress
  banner + disabled/spinner button state, since real Anthropic calls can
  take 10-30+ seconds; and **Log a Correction** — a modal form (`POST
  /api/denials/{id}/corrections`) that lets a reviewer re-pick the
  classification category (or edit the appeal text, or correct an arbitrary
  extracted field), pre-filled with the AI's current value, plus a required
  reviewer name and free-text reason, matching the backend's actual
  behavior of appending an audit row rather than mutating the original
  AI output. Existing `corrections` for the denial are listed underneath
  with an old-value → new-value diff and the reason.

### Running it

Backend (from repo root, Postgres already up via `docker compose up -d`):

```bash
cd backend
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local   # VITE_API_BASE_URL=http://localhost:8000/api
npm run dev
```

Serves on `http://localhost:5173` normally, or the next free port (`5174`,
`5175`, ...) if something else on the machine is already using `5173` --
`backend/main.py`'s CORS config allows any `localhost`/`127.0.0.1` port, so
this doesn't require any manual config change either way; just use whatever
port the `npm run dev` output actually prints.

### Verification

Ran both servers live against the real seeded database (62 denials: 48 MEC
+ 14 DME, all previously processed by Phases 2/4) and exercised the app in
an actual browser (Playwright), not just `npm run build`:

- **Queue** loaded all 62 real denials with correct status pills, payer,
  claim ref, and received date; company filter (`Meridian Eye Care
  Partners` / `Summit DME Providers`) and status filter both re-queried the API
  and changed the result set correctly (confirmed `status=new` correctly
  returned 0 results — every seeded denial has already been processed by an
  earlier phase — and `status=needs_review` correctly returned 11).
  Pagination showed "Page 1 of 4" at `page_size=20` and matched the API's
  `total=62`.
- **Empty state** — filtering to `status=new` (0 matches) rendered the
  intentional "No denials match these filters" empty state, not a blank
  table.
- **Detail view** — opened a `needs_review` denial (CLM-9427497, 55%
  confidence) and confirmed the extraction key-value grid, classification
  pill + red low-confidence bar, and "No appeal drafted yet" all matched the
  real API response exactly.
- **Correction flow** — submitted a real correction
  (`classification.category`: `coding_error` → `medical_necessity`, with
  reviewer + notes) through the modal; confirmed via direct `curl` against
  `GET /api/denials/{id}` that the `corrections` array actually persisted
  the new row server-side, and that the UI's correction-history list
  updated automatically (React Query cache invalidation) without a manual
  page refresh.
- **Appeal approve** — approved a drafted appeal (CLM-1263973) through the
  UI; confirmed via direct API call that `appeal.status`, `appeal.reviewer`,
  and `appeal.reviewed_at` were all updated server-side, and the pill
  flipped to green "Approved" in the UI.
- **Process with AI** — reset one denial to `status="new"` directly in
  Postgres to exercise this path (all 62 seeded denials had already been
  processed by earlier phases), clicked "Process with AI," confirmed the
  button disabled, the spinner + "Processing (this can take 10-30s)…"
  banner appeared immediately, and — after a real ~15s Anthropic API round
  trip — the page updated automatically to the new pipeline result
  (re-landed on `needs_review` at the same 55% confidence, consistent with
  the deterministic-ish behavior of the same input/prompt) with no manual
  refresh needed.
- **Error state** — pointed `VITE_API_BASE_URL` at an unreachable port
  (`:9999`), reloaded the queue, and confirmed a clean "Something went
  wrong / Could not reach the API… Is the backend running?" card with a
  Retry button — not a blank page or an unhandled exception. Restored the
  correct URL afterward and reconfirmed the queue loaded real data again.
- No console errors during any of the above.

No backend code was modified for this phase — the Phase 5 API's shapes
matched what the frontend needed exactly as documented in
`api/schemas.py`.

## Phase 7 — Monitoring Dashboard

`frontend/src/pages/DashboardView.tsx` (route `/dashboard`, "Monitoring" in
the top nav): the answer to "how would you know if this stopped working or
regressed" — a single monitoring surface over the eval harness, the live
denial population's classification confidence, and token/cost usage. Reuses
Phase 6's design system and API client patterns; no chart library was
added — every chart is plain inline SVG/HTML built against the dataviz
method (form before color, a validated palette, hover tooltips, a legend
for every multi-series chart), in `frontend/src/components/charts.tsx`.

### What's on it

- **Regression status banner** — green "No regression" / red "Regression
  detected" / neutral "No prior baseline" (first run), computed client-side
  from the two most recent `GET /api/eval/runs` rows using the *same* 5
  percentage-point threshold Phase 3's `run_eval.py` uses
  (`REGRESSION_THRESHOLD_PP`) — the banner shows the real delta in
  percentage points, not a re-derived number.
- **Eval accuracy over time** — line chart of `accuracy_score` across all
  eval runs. Handles the sparse-data case deliberately: a single run
  renders as one large annotated dot ("first eval run recorded... becomes
  the baseline"), not a fake flat line; 2+ runs render a real line with a
  hover tooltip (exact score + timestamp) and gridlines. Three real eval
  runs exist as of this phase (all scoring 0.95 — deterministic scoring
  against unchanged DB contents, so a flat line here is the *correct*
  result, not a placeholder).
- **Per-dimension breakdown** — the latest run's `details.
  classification_accuracy` / `extraction_accuracy` / `appeal_completeness`
  as three labeled magnitude bars (87.5% / 100% / 100% for the current
  data), pulled straight from the `eval_runs.details` jsonb, not
  recomputed.
- **Classification confidence distribution** — a new backend endpoint (see
  below) bucketed into a 4-step histogram, with a dashed reference line at
  the pipeline's real 0.7 `needs_review` routing threshold (README "Phase
  4") rather than an invented cutoff.
- **Token/cost panel** — stat tiles (total tokens, total cost, cost per
  denial processed = total cost / total denials), a cost-by-pipeline-stage
  bar chart, a cost-by-company bar chart (Meridian Eye Care Partners vs.
  Summit DME Providers — the same pipeline code driving both, Phase 4's point),
  and a by-day usage chart. All from the existing `GET /api/usage`
  endpoint, no new usage plumbing needed.

### New backend endpoint

`GET /api/analytics/confidence-distribution` (optional `?source_company=`),
in `backend/api/routes/analytics.py` — the one genuinely missing piece:
neither `/api/usage` nor `/api/denials` exposes classification-confidence
aggregates. Buckets the live population's `classifications.confidence`
(most recent classification per denial, via a per-denial
`max(created_at)` subquery, so a denial reprocessed more than once isn't
double-counted) into `0.00-0.50` / `0.50-0.70` / `0.70-0.85` / `0.85-1.00`
— edges chosen from the real observed spread (0.45-0.98 across the 62-denial
population) and aligned to the pipeline's real 0.7 routing threshold.
Response shape (`ConfidenceDistributionResponse` /
`ConfidenceBucket` in `api/schemas.py`) follows the existing API's
conventions (Pydantic response models, same query-param pattern as
`/api/usage?source_company=`). No pipeline/eval/profile logic was touched.

### Palette

Extends `index.css`'s `@theme` block rather than hardcoding chart colors:
added `--color-viz-amber` / `--color-viz-teal` as a fixed 3-slot categorical
order (`brand-500` blue, amber, teal) for the two small-N identity charts
(pipeline stage, company). The confidence histogram reuses the existing
brand ramp (`brand-400/500/700/900`) as a validated ordinal (light→dark)
scale instead of inventing a 4-color traffic-light ramp — an initial
red→amber→lime→green candidate for that histogram **failed** the dataviz
skill's CVD validator (adjacent-pair ΔE as low as 3.1, normal-vision floor
5.7, both well under the required floors) and was dropped in favor of the
single-hue ordinal ramp plus a labeled 0.7 threshold line, which validates
clean. See `node scripts/validate_palette.js` output in the Phase 7
verification notes below and the comment above the new theme tokens in
`index.css`.

### Verification

Brought up the full stack for real (Postgres already running via
`docker-compose`, `uvicorn main:app --reload` from `backend/` using its own
`.venv`, `npm run dev` from `frontend/`) and loaded `/dashboard` in an
actual browser via Playwright, not just a build check:

- Confirmed real data end-to-end: `GET /api/analytics/confidence-distribution`
  returned `total_classified: 62` with bucket counts `2 / 9 / 10 / 41`
  (matches a direct DB query used during development); `GET /api/usage`
  totals ($2.99, 506.9K tokens, 189 calls) and the by-stage/by-company
  breakdowns rendered on the page exactly matched the raw API response.
  Triggered one additional real eval run via `POST /api/eval/run` (no LLM
  calls — confirmed via `grep -i anthropic backend/eval/*.py`, which only
  matches a docstring saying it deliberately makes none) to get a 3-point
  trend line instead of shipping something that only looks right with a
  single data point.
  - Dataviz palette validator output (categorical, 3-slot, white card
    surface):
    ```
    node scripts/validate_palette.js "#2f7fc4,#b5730c,#0f9488" --mode light --surface "#ffffff"
      [PASS] Lightness band         all 3 inside L 0.43–0.77
      [PASS] Chroma floor           all 3 >= 0.1
      [PASS] CVD separation         worst adjacent #0f9488↔#b5730c ΔE 13.1 (protan) · tritan 23.0
      [PASS] Normal-vision floor    worst adjacent #0f9488↔#b5730c ΔE 19.8 (normal)
      [PASS] Contrast vs surface    all 3 >= 3:1
      → ALL CHECKS PASS
    ```
    and the confidence-histogram ordinal ramp:
    ```
    node scripts/validate_palette.js "#559fdc,#2f7fc4,#1c4f82,#17365a" --mode light --ordinal --surface "#ffffff"
      [PASS] Lightness monotone / Adjacent ΔL / Light-end contrast (2.85:1) / Single hue
      → ALL CHECKS PASS
    ```
- Console checked clean on both `/dashboard` and `/denials` (Playwright
  `browser_console_messages`, 0 errors / 0 warnings on each) — Phase 6's
  README notes a real hardcoded-CORS-port bug was caught this way, so this
  wasn't skipped.
- Hover-tested the accuracy-trend tooltip (screenshot confirms exact value
  + timestamp readout) and took a full-page screenshot of the assembled
  dashboard to check for label collisions/overflow (the company-comparison
  bar chart's label column was widened after the first pass truncated
  "Meridian Eye Care Partners" too aggressively; fixed and
  re-screenshotted).
- `npx tsc -b --noEmit` clean (no new TypeScript errors).

## Phase 8 — Multi-Company Live Demo

`frontend/src/pages/ProfilesView.tsx` (route `/profiles`, "Profiles" in the
top nav): the visual answer to a natural extension question for this kind
of pipeline, "how would you adapt this for a second company with a
similar problem" — a live, clickable demo instead of something only
explained after the fact. Everything on this page is real: real API
data, and a real Anthropic API call triggered from the browser.

### What's on it

- **Shared category taxonomy** — the six `CLASSIFICATION_CATEGORIES` from
  `db/models.py`, rendered once and labeled "reused, not duplicated" — both
  companies classify into the exact same six root causes; there is nothing
  company-specific to show here, which is itself part of the story.
- **Side-by-side profile columns** — one card per company, each showing its
  full extraction field list (name, type, required/optional, description)
  and a readable excerpt of its appeal guidance per category. This is the
  most visually convincing part: Meridian Eye Care Partners' column
  lists `cpt_code`, `cpt_description`, `physician_npi`, ... right next to
  Summit DME Providers's `hcpcs_code`, `equipment_type`,
  `lmn_reference_number`, ... — same layout, same component, genuinely
  different config.
- **Live processing demo** — a "Demo Tools" reset action (see below) plus a
  per-company card that reuses `DetailView.tsx`'s exact "Process with AI"
  pattern (same mutation shape, same loading copy, same
  extraction/classification/appeal display components —
  `KeyValueGrid`/`ConfidenceBadge`/`StatusPill`) so clicking "Process with
  AI" for each company in turn makes two real Anthropic API calls and shows
  the MEC and DME extractions populate with visibly different fields.

### New backend endpoints

- `GET /api/profiles/{key}` (`ProfileDetailOut` in `api/schemas.py`) —
  extends the existing lean `GET /api/profiles` (still returns
  `key`/`display_name` only, unchanged, since `QueueView`'s filter dropdown
  only needs that) with a second, richer per-profile endpoint: extraction
  fields shaped from `extraction_tool`'s Anthropic tool-use JSON schema into
  a clean `[{name, type, description, required}]` list (not the raw schema
  dump), the shared `category_taxonomy`, and a short excerpt (~220 chars,
  whitespace-collapsed) of `appeal_guidance` per category rather than the
  full appeal system prompt text. Pure read, no `profiles/` or `pipeline/`
  code touched.
- `POST /api/demo/reset-sample?source_company=...`
  (`backend/api/routes/demo.py`, `DemoResetOut` schema) — the demo-reset
  mechanism, see below.

### The demo-reset mechanism, and why it's clearly demo-only

All 62 denials in the dataset were already batch-processed in earlier
phases (39 MEC + 12 DME at `appeal_drafted`, 9 MEC + 2 DME at
`needs_review`; verified via a direct DB query before building this) — so
there was nothing sitting at `status="new"` to demo live processing
against. Rather than fake it, `POST /api/demo/reset-sample` picks one
already-processed denial for the given company (lowest `claim_ref`, so
repeat clicks cycle deterministically to a different record instead of
colliding), hard-deletes that one denial's `extractions`/
`classifications`/`appeals`/`corrections` rows, and sets its `status` back
to `"new"`. The delete is necessary, not cosmetic: `pipeline/extract.py`,
`classify.py`, and `draft_appeal.py` always `INSERT` a new row per stage
(see Phase 4/5) rather than upserting, so without clearing the prior rows a
"reprocessed" denial's detail view would still show the old run's output
underneath/alongside the new one.

This is deliberately not a general data-management feature:
- it only ever touches one denial at a time, chosen deterministically by
  the endpoint, never by caller-supplied id;
- it refuses (404) on any denial not already fully processed, so it can
  never touch something still mid-review;
- it lives in its own `api/routes/demo.py`, tagged separately from the real
  `denials.py` review endpoints in the OpenAPI schema;
- in the UI it's confined to a visually distinct, dashed-border "Demo
  Tools" callout labeled "case-study only, not production" directly above
  the live-demo cards — not a bare button sitting in the main denial
  worklist or detail view.

### Verification

Brought up the full stack for real (Postgres via `docker-compose`,
`uvicorn main:app` from `backend/`'s `.venv`, `vite` dev server from
`frontend/`) and drove `/profiles` in an actual browser via Playwright:

- `GET /api/profiles/meridian_eyecare_partners` and
  `.../summit_dme_providers` both returned the full `ProfileDetailOut` shape
  (16 and 18 extraction fields respectively, identical 6-category
  taxonomy, readable appeal-guidance excerpts) — confirmed via direct
  `curl`, not just the rendered page.
- Clicked "Reset a sample Meridian Eye Care Partners denial for live
  demo" → API reset `CLM-1199775` to `status="new"`; clicked "Process with
  AI" → a real ~15-30s Anthropic call ran end-to-end and the card populated
  with extracted fields (`cpt_code=V2785`, ...), classification
  (`eligibility`, 95% confidence), and a drafted appeal letter.
- Did the same for Summit DME Providers → reset `CLM-2191089`, processed live,
  and the card populated with genuinely different fields
  (`hcpcs_code=E0470`, `equipment_type=BiPAP device`,
  `lmn_reference_number=LMN-2026-3934`), classification (`coding_error`,
  90% confidence), and its own drafted appeal — the two companies' cards
  side by side after both runs is the intended "20 seconds" moment for a
  demo walkthrough.
- Confirmed both denials persisted to `status="appeal_drafted"` in Postgres
  directly (`psql` query), not just in the UI's local state.
- Console checked clean on `/profiles` before and after both live runs
  (Playwright `browser_console_messages`, 0 errors / 0 warnings).
- `npx tsc -b` and `oxlint` both clean; `vite build` production build
  succeeds.

## Phase 9 — Cold-Start Verification

The whole point of this phase: every prior phase was verified individually
by whichever agent built it, but never as one continuous cold-start run of
the full stack, the way a real user (or a demo walkthrough) would actually
experience it.

### What was done

Killed every `uvicorn`/`vite`/`node` process rooted in this project and ran
`docker compose down` (not `-v` -- the named volume, and with it the real
62-denial dataset, was left untouched and confirmed intact by direct query
afterward). Brought everything back up strictly by following this README's
own documented steps (Postgres via `docker compose up -d`, backend via
`alembic upgrade head` + `uvicorn main:app --reload --port 8000`, frontend
via `npm run dev`), then drove the entire user journey in a real browser via
Playwright: queue load/company-filter/status-filter/pagination, a
Meridian Eye Care Partners detail view (CPT/physician-NPI fields) and a
Summit DME Providers detail view (HCPCS/equipment-type/LMN fields), a real
correction submitted through the UI and independently re-verified with a
direct DB query (not just the UI's post-submit state), the monitoring
dashboard, the profiles comparison page, and the Demo Tools live
reset-and-process flow for both companies (real Anthropic API calls). The
browser console was checked after every page load and every action, at both
1920x1080 and 1440x900 (two common screen-recording resolutions).

### Bug found and fixed

The Demo Tools live-process run for Meridian Eye Care Partners produced
a drafted appeal letter whose opening line was: *"April 21, 2025 — wait, let
me use the correct date reasoning."* -- the model's own self-correction
scratchwork, leaked verbatim into a document meant to be reviewed and sent
to a real payer. This is exactly the kind of thing that would have been
embarrassing live on camera, and it slipped through Phase 8's verification
because that phase's spot-check runs happened not to trigger it.

Fixed two ways in `backend/pipeline/draft_appeal.py` and both
`backend/profiles/*.py` appeal system prompts:

1. Added an explicit prompt instruction (both company profiles) to compute
   any date silently and never surface hesitation, self-correction, or
   "show your work" language in the letter body.
2. Added a defensive check in `draft_appeal.py._run_once()` -- the same
   pattern the existing grounding check already uses -- that scans the
   drafted text for a set of known leak markers (`"wait, let me"`, `"let me
   reconsider"`, etc.) and raises `PipelineStageError` to trigger the
   existing one-retry-then-fail path if one is found, so this failure mode
   is now caught automatically rather than relying on a human noticing it.

Re-ran the same denial live after the fix (both via a direct API call and
again through the browser UI for a second, DME-side run) and confirmed a
clean letter with no leaked reasoning either time, with zero retries fired
on either run (the fix worked on the model's first response, not by
papering over a flaky one via the retry path).

### Real timing, for pacing a demo walkthrough

- **Queue/detail page loads**: near-instant (<100ms server response; no
  visible loading state in practice).
- **Correction submit**: ~1-2s round trip (form submit to updated
  correction-history list, no manual refresh needed).
- **Demo Tools reset**: ~2-4s (delete of prior stage rows + status update).
- **Process with AI / live pipeline run** (extract → classify → draft, real
  Anthropic API, 3 sequential calls): **~20-30s** per denial, both companies
  landed in this range during verification. This is the one spot in a live walkthrough
  that needs either narration to fill the wait or a cut -- don't stand
  in silence for it.

### Verification

Full click-through above, plus: `npx tsc -b --noEmit` clean, `npx oxlint`
clean, `npm run build` production build succeeds. Backend log reviewed for
the whole session -- no unhandled exceptions, and the one `PipelineStageError`
retry path that exists for this exact failure mode did not fire on the
post-fix runs (i.e. the fix worked on the first attempt, not by masking a
flaky one).

## Phase 10 — Dark Mode

A manual light/dark toggle — the sun/moon icon button in `TopNav`
(`frontend/src/App.tsx`), next to the mobile hamburger button, always
visible at every breakpoint.

### How it works

- **State/persistence** — `useTheme()` in `App.tsx`: on first load, reads
  `localStorage["theme"]`; if nothing is stored, falls back to
  `window.matchMedia("(prefers-color-scheme: dark)")`. Clicking the toggle
  writes the explicit choice to `localStorage` and stops following OS
  preference changes from that point on (an OS `change` listener is only
  acted on while `localStorage["theme"]` is still unset).
- **Applying the theme** — a `dark` class on `<html>`. Tailwind v4 defaults
  `dark:` to a `prefers-color-scheme` media query with no way to override it
  manually; `index.css` opts into class-based dark mode instead via
  `@custom-variant dark (&:where(.dark, .dark *));` (the v4-idiomatic
  equivalent of v3's `darkMode: 'class'`, since there's no
  `tailwind.config.ts` to put that in).
- **No flash of the wrong theme** — a small inline `<script>` in
  `frontend/index.html`'s `<head>` reads `localStorage`/`matchMedia` and
  adds the `dark` class before the stylesheet or React ever run, so a hard
  reload with dark stored/preferred never shows a light flash. Kept
  logically in sync with `useTheme()`'s light/dark resolution by hand (it's
  plain JS, not a shared import, since it has to run before the bundle
  loads).

### Color tokens — real dark values, not an invert

Per the dataviz skill's rule that dark mode gets its own validated steps
from each ramp rather than an automatic flip, every color in `index.css`'s
`@theme` block gets a real dark-mode value, defined under a `.dark { ... }`
block that redefines the same CSS custom properties `@theme` already
generates. Because every Tailwind utility (`bg-ink-50`, `text-status-
approved-fg`, etc.) compiles to `var(--color-ink-50)` and friends rather
than an inlined hex, redefining these variables re-themes the entire app
with almost no `dark:`-prefixed utilities needed — only literal colors
(`bg-white`, `stroke="white"`) needed hand conversion, to a new `--color-
surface` token (`#ffffff` light / `#141b2b` dark) used for cards, inputs,
the header, the modal, and chart tooltips.

Key dark values:

- **Ink (neutral) scale** — role-inverted per step, not a literal reversed
  copy: page canvas `#0b1220`, primary text `#e4e9f2`, headings `#f7f9fc`.
- **Surface** — `#141b2b`, deliberately *lighter* than the page canvas
  (dark UIs raise elevation by adding light), matching how `white` sits
  above `ink-50` in light mode.
- **Status pills** (`new`/`processing`/`classified`/`appeal_drafted`/
  `needs_review`/`approved`/`rejected`/`sent`) — own low-lightness
  bg / light-saturated-fg pairs per status, not inverted light-mode hexes.
- **Confidence badge** (`ConfidenceBadge`) — `#e0555a` / `#c08600` /
  `#3f9d68`, validated as a categorical triple against the dark surface
  (see below); legal in the CVD 6-8 WARN band because every use already
  ships a mandatory text label alongside the color.
- **Confidence histogram ordinal ramp** (dashboard) — `#3a6ea8` →
  `#4f8ac2` → `#6aa3d6` → `#8fc2ec`, its own dark-surface-validated steps
  (the light-mode brand-400/500/700/900 ramp's dark end is too dark to
  read on a dark card).
- **Cost-by-stage / cost-by-company categorical palette** — slot 1 keeps
  `--color-brand-500` (`#2f7fc4`, already load-bearing, reads fine on
  dark), slots 2-3 become `#b3860c` (amber) / `#17a591` (teal).

### Palette validator output (dataviz skill, `scripts/validate_palette.js`)

```
node scripts/validate_palette.js "#2f7fc4,#b3860c,#17a591" --mode dark --surface "#141b2b"
  [PASS] Lightness band         all 3 inside L 0.48–0.67
  [PASS] Chroma floor           all 3 >= 0.1
  [PASS] CVD separation         worst adjacent #17a591↔#b3860c ΔE 13.2 (protan) · tritan 20.5
  [PASS] Normal-vision floor    worst adjacent #17a591↔#b3860c ΔE 18.1 (normal)
  [PASS] Contrast vs surface    all 3 >= 3:1
  → ALL CHECKS PASS

node scripts/validate_palette.js "#3a6ea8,#4f8ac2,#6aa3d6,#8fc2ec" --mode dark --surface "#141b2b" --ordinal
  [PASS] Lightness monotone / Adjacent ΔL >= 0.06 / Light-end contrast (3.26:1) / Single hue
  → ALL CHECKS PASS

node scripts/validate_palette.js "#e0555a,#c08600,#3f9d68" --mode dark --surface "#141b2b"
  [PASS] Lightness band, Chroma floor, Contrast vs surface
  [WARN] CVD separation (worst adjacent ΔE 6.4, legal 6-8 floor band — mandatory
         secondary encoding present: ConfidenceBadge always pairs the color
         with a text label)
  [PASS] Normal-vision floor    ΔE 15.3
  → ALL CHECKS PASS
```

### Verification

Killed the stale `uvicorn`/`vite` processes from a prior session and
brought both back up clean per this README's own steps, then drove all
four routes (`/denials`, `/denials/:id`, `/dashboard`, `/profiles`) in an
actual browser via Playwright at 390px and 1920px, in both themes:

- Toggle switches instantly and the choice survives a full page reload
  (`localStorage["theme"]` checked directly, not just visually).
- Checked every card, status pill, table row (including hover — the row
  hover tint is visibly distinct from the surrounding card in dark mode),
  button, input, modal, and chart for legibility; none found illegible.
- Dashboard charts (accuracy trend line, confidence histogram, cost-by-
  stage/company bars) all render with the dark-validated palettes above.
- Hard-reloaded with dark stored and confirmed `document.documentElement`
  already has the `dark` class immediately after navigation (no light
  flash).
- Light mode re-screenshotted on `/denials` and `/dashboard` at 1920px and
  confirmed pixel-equivalent to the pre-dark-mode design (no regression).
- Browser console clean (0 errors, 0 warnings) on every page load and
  toggle, in both themes.
- `npx tsc -b --noEmit`, `npx oxlint`, and `npm run build` all clean.

No backend code was touched for this phase.

## Manual denial creation ("New Denial")

Before this, the only denials in the system were the 62 pre-seeded synthetic
ones, plus a "Demo Tools" reset on `/profiles` (Phase 8) that resets an
already-processed denial back to `status="new"` so there's something to run
"Process with AI" against live. That's still there and still useful, but it
means a live demo (e.g. a recorded walkthrough) could only reprocess canned
data, never a genuinely new example typed or pasted in on the spot.

- **Backend** — `POST /api/denials` (`backend/api/routes/denials.py`),
  request body `DenialCreateRequest` (`backend/api/schemas.py`):
  `source_company` (required, must be a key registered in
  `backend/profiles/__init__.py`'s `PROFILES`, else `400`) and `raw_text`
  (required, non-empty). `payer` and `claim_ref` are `NOT NULL` columns on
  `denials` but optional in the request — omitted `payer` becomes `"Unknown
  (manual entry)"`, omitted `claim_ref` becomes `MANUAL-{8 hex chars}` (a
  fresh UUID prefix), both obviously placeholder values, never
  fabricated-looking real ones. `received_at` defaults to now if omitted.
  `status` is not settable by the caller — every manually-created denial
  starts at `"new"`, so the existing "Process with AI" button on the detail
  view (Phase 6) has something to do. Returns the same `DenialListItem`
  shape the queue list endpoint uses.
- **Frontend** — a "New Denial" button on the Queue view header
  (`frontend/src/pages/QueueView.tsx`) opens a dedicated route,
  `/denials/new` (`frontend/src/pages/NewDenialView.tsx`) — a form page
  rather than a modal, since the primary field (raw denial text) needs a
  large textarea that a modal would cramp. Fields: company (dropdown,
  `GET /api/profiles`, same source as the Queue's company filter), denial
  letter text (large, prominent `textarea`, the primary/required field),
  and optional payer / claim ref inputs with placeholder text that makes
  the auto-generated-default behavior explicit. Submit calls the new
  `api.createDenial()` (`frontend/src/api/client.ts`); on success, navigates
  straight to `/denials/{new_id}` — the existing detail view and its
  "Process with AI" button, untouched. Submit-in-flight and error states
  follow the same pattern as `CorrectionForm`/`ProfilesView`'s demo-reset
  button (disabled button + "Creating…" label; error text rendered inline,
  not swallowed).

### Verification

Killed a stale `uvicorn`/`vite` pair left running from a prior session,
started exactly one of each fresh, then drove the full flow in an actual
browser via Playwright: opened `/denials`, clicked "New Denial", picked
"Meridian Eye Care Partners," pasted in a realistic fake denial letter
(medical-necessity denial for CPT 92134 posterior-segment OCT imaging,
CARC CO-50, no physician name/NPI/diagnosis code included on purpose),
left payer/claim ref blank, and submitted. Landed on `/denials/{id}` with
claim ref auto-generated as `MANUAL-3187decf` and payer
`"Unknown (manual entry)"`, status `New`. Clicked "Process with AI" and
confirmed a real ~20s Anthropic API round trip: extraction correctly pulled
`cpt_code: "92134"`, `carc_code: "50"`, `payer_name`, `billed_amount`, etc.
(leaving `physician_npi`/`diagnosis_code`/`physician_name` as `<UNKNOWN>`,
correctly, since the test letter never stated them), classification landed
on `medical_necessity` at 97% confidence, and the denial correctly routed
to `needs_review` rather than drafting an appeal (missing required
grounding fields) — genuine pipeline behavior, not a bug in the new
create flow. Confirmed the new record shows up in the Queue (`total` went
from 62 to 63, sorted to the top by `received_at`). Checked the new
`/denials/new` form in both light and dark theme (computed background/text
colors sampled directly, not just eyeballed) and at 390px mobile width (no
horizontal overflow, mobile hamburger nav intact). Browser console clean
(0 errors, 0 warnings) throughout.

## Reprocess with AI (detail view)

Before this, the detail view's "Process with AI" button (Phase 6) only
rendered when a denial's `status === "new"` — once a denial had gone
through extraction/classification/appeal drafting, the only way to run the
pipeline against it again was the `/profiles` "Demo Tools" reset hack
(Phase 8), which hard-deletes the prior run's rows first and is scoped to
one deterministic denial per company, not any denial a user is looking at.

Investigated `POST /api/denials/{id}/process`
(`backend/pipeline/run.py`'s `process_denial_by_id` /`process_denial`)
before changing anything: it never checks or requires `status="new"` —
it just sets `status="processing"` and re-runs extract → classify →
draft_appeal, and each stage (`pipeline/extract.py`, `classify.py`,
`draft_appeal.py`) always `INSERT`s a fresh row rather than upserting.
`GET /api/denials/{id}` (`backend/api/routes/denials.py`) already selects
the extraction/classification/appeal by `ORDER BY created_at DESC LIMIT 1`,
so a second pipeline run on an already-processed denial "just works" today
— older rows are left in the table (same as the demo-reset flow's
non-deleting sibling path) but the API and detail view only ever surface
the latest. **No backend changes were needed or made.**

- **Frontend only** — `frontend/src/pages/DetailView.tsx`: the process
  button now always renders, regardless of `denial.status`. Label and style
  switch on whether the denial already has results
  (`status !== "new"`): first run keeps the original `btn-primary` "Process
  with AI"; reprocessing an already-processed denial shows a distinct
  `btn-secondary` "Reprocess with AI" (with a refresh icon) so it doesn't
  read as identical to a first-time action. Reprocessing also goes through
  a `window.confirm()` first, spelling out concretely what will change
  (new extraction/classification/appeal, and — since `draft_appeal.py`
  always inserts a fresh `Appeal` row with `status="draft"` — any existing
  human approval/rejection on the current appeal gets superseded rather
  than carried over) before firing the mutation. Cancelling the confirm
  fires nothing. The existing "Processing…" banner, disabled-button
  spinner state, and React Query cache invalidation
  (`["denial", id]` + `["denials"]`) on the mutation used by the original
  button are unchanged and unconditionally cover the reprocess path too —
  no new loading UX or cache logic needed.

### Verification

Confirmed exactly one `uvicorn` (port 8000) and one `vite` (port 5173)
already running from a prior session (no stale duplicates). Picked an
already-`appeal_drafted` denial from seed data, `CLM-1263973`
(`62c8a4f9-93f6-4e66-8d3a-800013a51b01`, Meridian Eye Care Partners),
noted its state via the API first: classification `missing_information`
at 75% confidence, appeal `status="approved"`. Clicked "Reprocess with AI"
in a real browser via Playwright, confirmed the `window.confirm()` dialog
text, accepted it, confirmed the "Processing (this can take 10-30s)…"
button/banner state matched the original flow exactly, and waited for a
real ~40s Anthropic API round trip. After completion: classification came
back the same (`missing_information`, 75% — a genuine re-run landing on
the same answer, not a fluke; both extraction and classification got new
DB row ids), but the appeal text changed (different letter date, reworded
opening) and — most importantly — `appeal.status` reset to `"draft"`,
proving a brand-new `Appeal` row was inserted rather than the old
`"approved"` one being reused or displayed stale. Re-clicked "Reprocess
with AI" and confirmed cancelling the dialog fires no mutation (button
stays idle, no network call). Checked dark mode (`.dark` class + real
per-token colors, not a filter) and 390px mobile width — button renders
legibly in both, wraps to its own row under the header on mobile, no
overflow. Also created and deleted a throwaway `status="new"` denial via
`POST /api/denials` to confirm the original first-run "Process with AI"
button (primary style, no confirm dialog) is unchanged. Browser console
clean (0 errors, 0 warnings) throughout.

## Draft Appeal Letter (detail view)

### The problem

`POST /api/denials/{id}/process` (Reprocess with AI, above) always reruns
the *full* pipeline: extract → classify → draft_appeal. That's fine for
"regenerate everything," but it's actively wrong for the most common
`needs_review` recovery path: a denial whose classification confidence
came back below `CONFIDENCE_THRESHOLD` (0.7, `pipeline/run.py`), so
`process_denial` routed it to `needs_review` *before* ever reaching
`draft_appeal`. A human reviewer looks at it, decides the AI's category was
wrong, and logs a correction via the existing `POST /corrections` audit
trail. There was previously no way to get an appeal drafted off that
corrected category without hitting "Reprocess," which reruns extraction
and classification too — a second, real LLM call that could easily land on
a *different* wrong category (or the same original one), overwriting the
context of the correction the human just made. Reprocessing to fix this
defeats the point of having made the correction.

### Audit history — a unified, immutable event log

The detail view's "Audit History" section (renamed from "Correction
History") shows a single chronological timeline mixing two kinds of
permanent, human-attributed compliance events:

- **corrections** — a human edit to an AI-produced field (unchanged from
  the original Phase-6 feature).
- **appeal_review** — an appeal approve/reject/sent decision.

**Schema decision: extended the existing `corrections` table in place,
rather than adding a second table.** `Appeal.status`/`reviewer`/
`reviewed_at` already existed as *mutable* "current state" columns on the
`appeals` row — `update_appeal_status` used to just overwrite them, so if
an appeal was approved, later reprocessed (a new `Appeal` row, per the
Reprocess feature), and re-reviewed, the prior reviewer/timestamp was
gone with no trace. That's the gap this closes. Rather than build a
parallel `appeal_review_events` table, the fix reuses `corrections`
because the two event shapes turned out to share the same four columns
cleanly: a correction's `field_corrected`/`old_value`/`new_value` map
directly onto an appeal review's "what changed" (`field_corrected` is
always the literal string `"appeal.status"`, `old_value`/`new_value` are
the previous/new appeal status), and `corrected_by`/`corrected_at` map
onto "who reviewed it and when." Two new columns were added:
`event_type` (`"correction"` | `"appeal_review"`, defaults to
`"correction"`) to distinguish the two shapes for the frontend, and a
nullable `appeal_id` FK (`SET NULL` on delete) so an `appeal_review` event
records *which* `Appeal` row it was about — useful once a denial has more
than one, post-reprocess. The SQLAlchemy model class was renamed
`Correction` → `AuditEvent` (`backend/db/models.py`) to reflect what it
now holds, though the underlying table is still named `corrections` (kept
the migration a pure `ADD COLUMN`, not a rename) — a `Correction =
AuditEvent` alias is kept for anything that still imports the old name.
Migration: `backend/alembic/versions/c96f0c026d93_audit_events.py`.

**What actually changed at the row level:** `update_appeal_status`
(`backend/api/routes/denials.py`) still updates `appeal.status`/
`reviewer`/`reviewed_at` in place — the detail view's "Last reviewed by…"
line under the appeal panel still needs that "current state" — but now
*also* inserts a new `AuditEvent(event_type="appeal_review", ...)` row.
That insert is never updated or deleted by a later action; re-reviewing
the same appeal (or reprocessing then re-reviewing) overwrites the
`appeals` row but always appends, never touches, prior `corrections`
rows. Verified directly: approving an appeal, then hitting
`POST /appeal/status` again with a different `status`/`reviewer`, leaves
**both** `appeal_review` rows in `corrections` — only the mutable
`appeals` row shows the latest decision.

**Backfill:** the migration backfills `appeal_review` events for any
`appeals` rows that already had `reviewer`/`reviewed_at` set from testing
before this feature existed (`old_value` is assumed `"draft"`, since prior
per-decision history was never recorded). This can only recover the
*current* state each `appeals` row happened to have at migration time — if
an appeal had been reviewed more than once before this migration, only the
most recent decision survived to backfill from; any earlier, overwritten
review is genuinely gone. Only audit events from this migration forward
are guaranteed complete and immutable.

**API shape:** `GET /api/denials/{id}` was extended (not a new endpoint —
it already embedded corrections, so extending the existing response kept
the API surface flat) to return `audit_events: AuditEventOut[]` instead of
`corrections: CorrectionOut[]`, ordered newest-first by `corrected_at`.
Each `AuditEventOut` carries `event_type`, `appeal_id`, and the shared
`field_corrected`/`old_value`/`new_value`/`corrected_by`/`corrected_at`/
`notes` columns — enough for the frontend to render either shape without a
second request. `POST /api/denials/{id}/corrections` is unchanged from the
caller's perspective; it now sets `event_type="correction"` under the
hood.

**Frontend:** `DetailView.tsx`'s "Correction History" card is now "Audit
History," rendering `denial.audit_events` as one list; `appeal_review`
entries get a cyan "Appeal review" badge and reuse `StatusPill` (the same
green/red/cyan `status-approved`/`status-rejected`/`status-sent` tokens
from `index.css` used elsewhere) to show `old_value → new_value` as real
status pills, while `correction` entries keep their prior look (a blue
"Correction" badge, strikethrough old value → highlighted new value).
Verified in both themes and at 390px mobile width.

### How corrections and the live classification row interact

Checked this before building anything, per the task brief, because it
determines whether a "draft from current classification" button can work
at all: `POST /api/denials/{id}/corrections`
(`backend/api/routes/denials.py::create_correction`) is, and remains,
**audit-log only** — it writes a `corrections` row and does **not** touch
the `classifications` table. The AI's original `category`/`confidence` row
is left exactly as produced, on purpose, so the audit trail always has
"what the AI said" preserved distinctly from "what a human corrected it
to."

Given that, a naive "draft appeal from the denial's current classification
row" would silently ignore the correction and draft off the *original*
(wrong) category — the exact failure mode the task called out to watch
for. Rather than start mutating `classifications` rows (option (a) from
the brief, which would blur the audit trail's "AI original vs. human
correction" distinction that Phase 6 built specifically to keep separate),
the new endpoint takes option (b): **`pipeline.run.draft_appeal_only`
looks up the most recent `corrections` row with
`field_corrected="classification.category"` for the denial, and if one
exists, uses its `new_value` as the category fed into `draft_appeal`'s
prompt — instead of the (still-unmutated) `classifications.category`
column.** The `classifications` row itself is never written to by this
endpoint or by corrections; only the *prompt-building* step prefers the
correction when one exists. This is now the one place a correction has any
effect beyond being an audit record — documented directly on both
`create_correction`'s and `draft_appeal_only`'s docstrings so it isn't a
surprise to anyone reading the audit-trail design later.

`Classification.category` is a Postgres enum, but `corrections.new_value`
is free text (correctable fields on other rows, like `appeal.draft_text`,
are prose) — `draft_appeal_only` validates the correction's `new_value` is
one of the six real `CLASSIFICATION_CATEGORIES` before using it as a
category, raising a 400 if not, rather than passing an invalid value into
`profile.appeal_system_prompt()` (which would `KeyError` on
`appeal_guidance[category]`). In practice the frontend's `CorrectionForm`
already constrains `new_value` to a `<select>` of the six valid categories
when correcting `classification.category`, so this is a defense-in-depth
check against a correction filed some other way (e.g. directly via the
API), not a path reachable through the UI.

One more wrinkle: `classify.py`'s `reasoning` field is never persisted to
the `classifications` table (only `category`/`confidence`/`model_version`
are columns) — it only exists transiently in-process during a full
pipeline run, for `draft_appeal`'s prompt. Standalone drafting has no
persisted reasoning to read back, so `draft_appeal_only` synthesizes a
short one: either `"Automated classification (model confidence X.XX)."`
when no correction exists, or a sentence naming who corrected it, from
what, to what, and any notes, when one does — which also has the nice
side effect of giving the LLM explicit context that this is a
human-confirmed category, not just handing it a bare label.

### New backend

- `backend/pipeline/run.py::draft_appeal_only(denial_id)` — fetches the
  denial's most recent `Extraction` and `Classification` rows (404s via
  `ValueError` if either is missing — this endpoint requires both to
  already exist, unlike `/process`), resolves the effective category as
  described above, calls the existing `draft_appeal()` function unchanged
  (no new pipeline logic — it was already standalone-callable given
  extraction + classification + a profile), and on success advances
  `denial.status` to `"appeal_drafted"` (a `needs_review` denial that gets
  a manually-drafted appeal is no longer missing an appeal, so it leaves
  `needs_review` the same way a full pipeline run would).
- `POST /api/denials/{id}/appeal/draft` (`backend/api/routes/denials.py`)
  — thin wrapper, mirrors `/process`'s shape (`ProcessResponse`:
  `{denial_id, status}`), 400s on the `ValueError` cases above, 404s on an
  unknown denial.

### Frontend

`frontend/src/pages/DetailView.tsx`: a new `btn-primary` "Draft Appeal
Letter" button, visually and behaviorally distinct from "Process with
AI"/"Reprocess with AI" (`btn-secondary`, unchanged). Visibility rule:
`hasClassification && !hasAppeal` — shown once a classification exists
(there's something to draft from) and hidden once an appeal exists
(regenerating an existing appeal is what "Reprocess with AI" is for, so
showing both would be two overlapping ways to do the same thing). This
covers the primary `needs_review`-after-correction case without a status
check, and also naturally covers a `classified` denial whose appeal draft
failed and never got a row. When shown, it renders alongside "Reprocess
with AI" in the header (both buttons available: draft a targeted appeal,
or nuke-and-repave everything), each disabling the other while either
mutation is in flight. Reuses the same loading-banner/spinner/error-banner
pattern and React Query cache invalidation (`["denial", id]` +
`["denials"]`) as the existing process/reprocess mutation — no new UX
pattern introduced.

### Verification

Started backend (`uvicorn`, port 8000) and frontend (`vite`, port 5174)
against the live seeded Postgres DB. Queried directly for `needs_review`
denials with a classification but no appeal — several exist in seed data,
confirming the button-visibility case is real, not hypothetical.

**The one thing that had to actually work — correction changes the drafted
category:** Picked `CLM-9427497`
(`eb26a343-d30d-4ba3-b6f8-e9cdf5495cb8`), `needs_review`, classification
`category="coding_error"`, `confidence=0.55`, no appeal. Submitted `POST
/corrections` changing `classification.category` from `coding_error` to
`medical_necessity` via the real API (not the UI, for this first pass, to
isolate the backend logic before testing the UI path). Called `POST
/denials/{id}/appeal/draft` → `{"status": "appeal_drafted"}`. Then, via a
**direct DB script** (not the API, per the task instruction):
`classifications.category` was still `coding_error` (0.55) — confirming
corrections really are still audit-only and the AI's original output is
untouched. The new `appeals` row's `draft_text` opens: *"...denied under
CARC 97... We respectfully disagree with this determination and,
**consistent with the internal review classifying this denial as a
medical-necessity matter**, request that Vantage Point Insurance
reconsider the claim on that basis..."* followed by a `"Clinical Basis for
Medical Necessity"` section — the string `"coding error"` does not appear
anywhere in the letter; `"medical necessity"` does. The correction
concretely changed what the drafted appeal argues.

Ran the same flow a second time through the **real browser UI** (not just
curl) on a second denial, `CLM-2370834`
(`21b4998b-ea1c-472b-8168-3e2f962727b8`, no correction filed this time —
confirming the no-correction/original-category path also still works):
loaded the detail page, confirmed both "Draft Appeal Letter" (primary) and
"Reprocess with AI" (secondary) render side by side with distinct labels;
clicked "Draft Appeal Letter"; confirmed the button/other-button disabled
state, spinner, and info banner (distinct copy from the reprocess banner —
explicitly says extraction/classification are not rerun) during the ~40s
real Anthropic call; after completion, `status` pill changed to "Appeal
Drafted", the "Draft Appeal Letter" button correctly disappeared (appeal
now exists), and only "Reprocess with AI" remained — verifying the
visibility rule updates live via the existing cache invalidation, not just
on reload. Checked dark mode (`.dark` token palette) and 390px mobile
width in the browser — both buttons render legibly, wrap cleanly under the
header on mobile, no overflow, no layout shift. Browser console clean (0
errors, 0 warnings) across the whole flow — the only console errors seen
in this session were pre-existing 404s for an unrelated denial id from a
prior test session, unrelated to this feature.

## AI-action audit events (detail view)

### The problem

The unified Audit History timeline (see "Audit history — a unified,
immutable event log" above) logged the human half of a denial's story —
corrections and appeal-review decisions — but not the AI half. A reviewer
looking at a denial's history saw "human corrected classification.category"
and "human approved the appeal," with no record that extraction,
classification, and appeal drafting ever ran, or when. The timeline told
half a story.

### What changed

`AuditEvent`/`corrections` (`backend/db/models.py`) gained a third
`event_type`: **`"ai_action"`**. `AUDIT_EVENT_TYPES` is now
`("correction", "appeal_review", "ai_action")`. Postgres enum extended via
`backend/alembic/versions/b8830a7ff9c5_ai_action_audit_events.py`
(`ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'ai_action'` — no new
columns needed, since `ai_action` events reuse the same four columns the
other two shapes already share):

- `field_corrected` — the pipeline stage key: `"extraction"` |
  `"classification"` | `"appeal_drafting"`.
- `old_value` — always `""`. There's no "previous value" for a stage
  running for the first time; this is a creation event, not an edit.
- `new_value` — a short human-readable summary of what the AI produced,
  e.g. `"Processed denial letter"`, `"Classified as medical_necessity"`,
  `"Drafted appeal"`.
- `corrected_by` — always the literal string `"AI"`, never a person's name.
  This is what the frontend keys off of to badge the event as
  system-originated rather than human-originated.
- `notes` — extra detail: field count for extraction, confidence score for
  classification, draft length for appeal drafting.

**Where they're inserted:** `backend/pipeline/run.py` gained a
`_log_ai_action(db, denial, stage=..., summary=..., notes=...)` helper
(does not commit — same transaction-boundary convention as the rest of the
module) called right after each stage succeeds:

- `process_denial` — after `extract_denial` succeeds (before the
  extraction/token-usage commit), after `classify_denial` succeeds (before
  the classification/status commit — logged regardless of whether the
  confidence check that follows routes the denial to `needs_review`, since
  classification genuinely did succeed), and after `draft_appeal` succeeds
  (before the `appeal_drafted` status commit).
- `draft_appeal_only` (the standalone "Draft Appeal Letter" endpoint) —
  after `draft_appeal` succeeds, same as the full pipeline's appeal-drafting
  event.

Failures are not logged as `ai_action` events — each stage's failure path
already routes the denial to `needs_review` and records the error on the
stage's own row (`Extraction.extracted_fields`, etc.), so a failed stage
still leaves a trace; this feature is additive on top of that, focused on
the success-path story per the task brief.

**API/frontend:** no new endpoint or type needed — `ai_action` rows flow
through the existing `GET /api/denials/{id}` → `audit_events` list exactly
like `correction`/`appeal_review` rows (`AuditEventOut`,
`backend/api/schemas.py`; `AuditEventType`, `frontend/src/api/types.ts`).
`DetailView.tsx` adds a third rendering branch: a gray "AI action" pill
(`bg-status-new-bg`/`text-status-new-fg` — the same neutral/dark-mode-aware
tokens the "new" denial-status pill uses, reused here rather than adding a
new color, consistent with how "Correction" already reuses
`status-classified` blue and "Appeal review" reuses `status-sent` cyan) with
a small sparkles icon, `new_value` as the headline, and `notes` underneath —
visually distinct from both existing badges, reading as "the system did
this automatically" rather than a human decision.

### Verification

Ran the real pipeline end to end via the UI: `POST /api/demo/reset-sample`
gave a clean-slate `status="new"` denial (`CLM-1199775`,
`7ea8e789-85b1-46be-b386-09e9778b4261`) with zero audit events. Clicked
"Process with AI" in the browser and polled the API until it reached
`appeal_drafted`. Resulting Audit History, newest first:

1. `ai_action` — "Drafted appeal" (`Draft length 2927 character(s).`)
2. `ai_action` — "Classified as eligibility" (`Confidence 0.95.`)
3. `ai_action` — "Processed denial letter" (`Extracted 14 field(s)...`)

— i.e. chronologically extraction → classification → appeal drafting, each
correctly badged "AI action" in gray with the sparkles icon, distinct from
the blue "Correction" and cyan "Appeal review" badges. Then logged a real
correction (`classification.category`: `eligibility` → `medical_necessity`)
and approved the appeal through the UI on the same denial, producing a
five-event mixed timeline — `appeal_review` → `correction` → `ai_action` ×3
— confirming AI and human events interleave correctly in one chronological
list: AI extracted → AI classified → AI drafted → human corrected → human
approved, exactly the story this feature set out to tell. Checked both
light and dark theme and 390px mobile width — badge, icon, and layout all
render legibly with no wrapping or overflow issues in any combination.
Browser console clean (0 errors, 0 warnings) throughout.

## What's next (not built yet)

Nothing explicitly deferred remains from the original phase plan as of
Phase 9.
