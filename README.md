# Hardware Hub

An AI-native internal hardware rental system built for the Booksy Early Careers technical assessment. Hardware Hub combines guarded inventory workflows with an explainable auditor that catches unsafe or contradictory data before it reaches employees.

**Live demo:** <https://hardware-hub-booksy.onrender.com> — demo admin `admin@booksy.com` / `Admin123!` (prefilled). Hosted on Render's free tier, which spins down when idle: the first load may take a minute or two while the instance cold-starts, then it is fast. The database re-seeds from the supplied inventory file on every start, so each visitor gets the same known state, data traps included.

**Stack:** Python 3.12 · FastAPI · SQLite · Vue 3 · Vite · OpenRouter through the OpenAI-compatible SDK (optional)

## Engineering dossiers

- [Interactive build dossier](build-report.html) — assignment coverage, architecture, seed strategy, guarded workflows, API explorer, test evidence, Git history, and submission readiness.
- [Independent code review](fable-review.html) — the full pre-submission review by a second AI model, kept in the repository deliberately: it documents the defects found (including the one where the AI feature contributed nothing), how they were verified, and how they were fixed. Transparency is the point.

## Product tour

- Account-only login with admin-created users, PBKDF2 password hashes, expiring bearer tokens, and role guards.
- Sortable, filterable hardware inventory with clear availability and safety-hold states.
- Atomic rent/return transitions that block damaged, repaired, or already-rented equipment.
- Admin command center for accounts, hardware, deletion, and repair lifecycle controls, with the Figma form's serial number (unique when present) and category fields and a show/hide toggle on the new-account password.
- AI Inventory Auditor that analyzes accepted inventory and preserved rejected-row evidence.
- Responsive Vue interface based on the supplied Figma wireframe's quiet sidebar, cards, table, and split login layout.

### Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | `admin@booksy.com` | `Admin123!` |
| User | `member@booksy.com` | `Member123!` |

These deterministic credentials are for assessment review only. A production release would create the first admin through a one-time bootstrap secret and require a password change.

## Quick start

Requirements: Python 3.12+, Node 20+, and npm.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
npm ci
npm run dev
```

In a second terminal from the repository root:

```bash
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
uvicorn backend.app.main:app --reload
```

Open `http://localhost:5173`. FastAPI documentation is at `http://localhost:8000/docs`.

The database is created and seeded on first API startup. Delete `hardware_hub.db` to reset local data.

### Optional live LLM audit

The auditor is fully demonstrable without credentials using its deterministic safety engine. To additionally run an additive model review through OpenRouter:

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

Set `OPENROUTER_API_KEY`, a strong `SECRET_KEY`, and optionally override `OPENROUTER_MODEL` or `OPENROUTER_FALLBACK_MODELS`. FastAPI loads the root `.env` file at startup. The default primary is `anthropic/claude-haiku-4.5`, with `google/gemini-3.1-flash-lite` as a cross-vendor fallback. This is a small structured-extraction task, so a small, fast model is a better fit than an expensive long-horizon reasoning model.

### How the two passes work

The rule engine is the safety authority. It always runs, costs nothing, and nothing the model says can remove or downgrade one of its findings.

The model runs a **second, independent pass** over the same source data. It receives the accepted inventory and the raw source rows — including the rows the loader rejected, which never reach the `hardware` table — but never the loader's own codes, severities, or messages. It has the evidence; it does not have the answer key. Agreement between the two passes is therefore meaningful, and is recorded rather than discarded:

| Confidence | Meaning |
| --- | --- |
| `corroborated` | Both passes found it independently. Highest confidence. |
| `rules_only` | Provable, but the model missed it. Shows where the model is weak. |
| `model_only` | The model alone raised it. The signal we are paying for. |

Model output is untrusted input. Each finding is validated **individually** against a Pydantic model, and a malformed finding is quarantined on its own without discarding its valid siblings — the same policy the seed loader applies to a bad record. Findings referencing a `hardware_id` that does not exist in the source are dropped and counted. Every drop is exposed through `hallucination_guard`.

The provider is sent a deliberately small, portable wire schema (closed objects, every field required, no unsupported constraint keywords). The richer Pydantic model is the local trust boundary. Those are two different jobs and two different schemas.

**Live verification — `anthropic/claude-haiku-4.5`, run via `pytest -m integration -s`:**

```json
{
  "llm_status": "Independent model pass: 1 new findings, 7 corroborating the rule engine.",
  "hallucination_guard": {
    "corroborated": 7, "rules_only": 2, "model_only": 1,
    "dropped_unknown_ids": 0, "dropped_invalid_schema": 0
  }
}
```

The one `model_only` finding was on hardware id 3, the Razer Basilisk: it sits in `Repair` with no damage notes and no recorded reason for being there. The rule engine only catches the inverse case — damage language on an item *not* in repair — so this is a genuine gap in the deterministic layer, found by the model. That is the whole argument for the AI pass, and it is reproducible.

## Architecture

```text
Vue workspace ── bearer token ──> FastAPI routes
                                      │
                         guarded SQLite transactions
                                      │
              ┌───────────────────────┴───────────────────────┐
              │                                               │
       operational inventory                         import issue ledger
              └───────────────────────┬───────────────────────┘
                                      │
                           AI Inventory Auditor
                    permanent rules + optional OpenRouter review
```

The API and Vue build ship as one Docker service. SQLite lives at `DATABASE_PATH` and re-seeds itself from the source file on a fresh start, which is why the free-tier deployment needs no persistent disk: every cold start reproduces the same reviewable state.

## Data strategy: every seed trap

The loader treats the seed as untrusted input. It validates each array entry in order, inserts valid operational records, and writes every warning/error with the original JSON to `import_issues`. It does not first convert the list to an ID-keyed dictionary, so duplicates cannot disappear through overwrite.

| Seed issue | Detection | Operational action |
|---|---|---|
| Duplicate `id: 4` | Repeated identifier in the same import | Second row rejected; first row remains unchanged; raw duplicate retained in issue ledger |
| `2027-10-10` purchase date | Valid ISO date later than today's date | Row accepted with a future-date warning for audit visibility |
| Brand `Appel` | Known likely typo | Typo warning preserved; row rejected because its date is also structurally invalid |
| Date `22-05-2023` | Not ISO `YYYY-MM-DD` | Row rejected rather than guessed or silently reformatted |
| Blank brand and date | Required-field validation | Unknown Device row rejected with separate evidence for both fields |
| Status `Unknown` | Allowed-state validation | Row rejected; invalid state never enters the rental engine |
| Dell marked Available with battery swelling | Damage-language safety scan across notes | Row retained for traceability, marked damaged, rent blocked |
| MacBook marked Available after liquid damage | Damage-language scan across history | Row retained for traceability, marked damaged, rent blocked |
| Seeded In Use Sony assigned to an email | Assignment retained | Visible as In Use and impossible to double-rent |

The first load therefore inserts **8 records**, rejects **3**, and persists **9 findings**. The dashboard distinguishes a source record's status from its safety hold instead of rewriting the original evidence.

## Rental invariants

- `Available + not damaged → In Use` is the only rent transition.
- Rent uses `BEGIN IMMEDIATE` plus a conditional update, preventing two simultaneous requests from both winning.
- `In Use → Available` is the normal return transition; only the assigned user or an admin may return it.
- A damaged return moves to `Repair`, never back to the rentable pool.
- In Use hardware cannot be deleted or toggled into repair.
- Completing a damaged repair requires an explicit service note; only that resolution clears the damage hold and restores availability.

## API surface

| Method | Route | Access | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/login` | Public | Issue an expiring session token |
| `GET` | `/api/auth/me` | User | Restore current session |
| `GET` | `/api/hardware` | User | Search, filter, and safely sort inventory |
| `POST` | `/api/hardware/{id}/rent` | User | Atomically rent an eligible item |
| `POST` | `/api/hardware/{id}/return` | Owner/Admin | Return an active rental |
| `POST` | `/api/hardware` | Admin | Add hardware |
| `DELETE` | `/api/hardware/{id}` | Admin | Delete non-rented hardware |
| `PATCH` | `/api/hardware/{id}/repair` | Admin | Start/complete repair |
| `GET/POST` | `/api/users` | Admin | List/create authorized accounts |
| `POST` | `/api/audit` | User | Run the evidence-grounded inventory audit |

## Testing and checks

21 deterministic tests in `tests/`, grouped by what they protect:

**Rental safety** — damaged hardware cannot be rented; hardware already In Use cannot be rented; a valid rent/return flow records owner and state; completing a damaged repair requires an explicit resolution note.

**Data boundary** — a duplicate seed ID is rejected without overwriting the original; SQLite (not application code) allocates new hardware IDs; serial numbers round-trip and stay unique (409 on duplicate, 422 on invalid category).

**Authorization** — members receive 403 from every admin route (parametrized across all five); anonymous callers receive 401.

**AI trust boundary** — without a key, all nine deterministic findings remain; the model is never shown the rule engine's conclusions but does receive the raw rejected rows; agreement is classified as corroboration and novel findings survive; one malformed finding is quarantined alone (drop the row, keep the batch — the seed loader's policy applied to model output); hallucinated hardware IDs are dropped and counted; an unusable envelope falls back to rules; `evidence` is a single type across sources; the provider wire schema contains no strict-mode-incompatible keywords.

Plus: a **credential-gated live OpenRouter contract test** (runs only with a key, via `python -m pytest -m integration -s`) that validates the real response and prints a sanitized transcript, and a **5-scenario Playwright suite** in Microsoft Edge covering admin, member, mobile, auditor, and deletion workflows.

Run everything used before handoff:

```bash
python scripts/run_repo_checks.py --mode full
```

This runs deterministic pytest coverage, a production Vue build, and `npm audit --audit-level=moderate`. It deliberately excludes the paid provider contract test even when `.env` contains a key. Run that proof gate explicitly with `python -m pytest -m integration -s`.

For visible browser QA, start the application with an isolated database and run `npm run test:e2e:headed` from `frontend/`. The Playwright configuration uses installed Microsoft Edge, one worker, traces, video, and screenshots; set `OPENROUTER_DISABLED=1` to guarantee a zero-cost deterministic audit.

## Deployment

Deployed on **Render** (free tier, Docker runtime) from this repository's multi-stage [Dockerfile](Dockerfile). Environment: `APP_ENV=production` (which makes a real `SECRET_KEY` mandatory — the app refuses to boot on the development fallback), `DEMO_MODE=true` (seeds the reviewer accounts), and `OPENROUTER_API_KEY` for the live audit pass. No persistent volume: the database intentionally re-seeds on every cold start.

To run the same container locally:

```bash
docker build -t hardware-hub .
docker run --rm -p 8000:8000 -e SECRET_KEY=change-me hardware-hub
```

Open `http://localhost:8000`. Vercel/Netlify were ruled out because serverless filesystems are ephemeral per invocation, which is incompatible with a file-backed SQLite database serving one long-lived process.

## Assessment compliance

Every requirement from the brief, mapped to where it lives:

| Requirement | Status | Where |
|---|---|---|
| Admin: add / delete / toggle repair | ✅ | `POST/DELETE /api/hardware`, `PATCH /api/hardware/{id}/repair` with state guards |
| Admin: create accounts (only entry path) | ✅ | `POST /api/users`, admin-only; no self-registration exists |
| Login system, admin-created users only | ✅ | PBKDF2 hashes, expiring JWT, role guard, member-vs-admin 403s proven in tests |
| Dashboard: name, brand, purchase date, status | ✅ | Inventory table, plus serial/category/assignee/safety-hold |
| Sorting and filtering | ✅ | Status filter, text search, column sort in the UI; safe allow-listed sort on the API |
| Rent / return flow | ✅ | Atomic compare-and-swap transitions; owner-or-admin return rule |
| Guards against impossible states | ✅ | Damaged, In Use, and Repair are unrentable; In Use is undeletable; damaged repairs need a resolution note |
| AI-native layer (one of three) | ✅ | Inventory Auditor: deterministic rule floor + independent LLM pass with corroboration classification |
| Supplied seed as starting point | ✅ | [data/inventory.seed.json](data/inventory.seed.json) verbatim, all traps preserved |
| Dirty-data handling | ✅ | Per-record quarantine with raw-evidence ledger; 8 inserted, 3 rejected, 9 findings |
| Python backend / Vue frontend | ✅ | FastAPI + Vue 3, the preferred stack |
| File-based database | ✅ | SQLite |
| Wireframe as inspiration, justified changes | ✅ | Layout kept, editorial remodel; justification in Design section |
| ≥ 3 critical AI-guided tests | ✅ | 21 deterministic tests + 1 credential-gated live contract test + 5 browser scenarios |
| README: status, shortcuts, partial, 24h roadmap | ✅ | This file, sections below |
| AI log: tooling, data strategy, prompt trail, correction | ✅ | Below, plus [prompts.md](prompts.md) |
| Public repo, clean incremental history | ✅ | 25+ small commits, each a reviewable decision |
| Live demo | ✅ | <https://hardware-hub-booksy.onrender.com> |
| ~4–5 hours | ⚠️ | Honestly: the core took roughly that; the auditor hardening, live verification, and deployment took more, and the history shows exactly where |

## Implementation status and trade-offs

### ✅ Fully implemented

- Authentication, admin-issued accounts, roles, hardware/user listings.
- Seed validation with rejected-row evidence and duplicate protection.
- Rent, return, add, delete, and repair transitions with business guards.
- Vue login, dashboard, sorting/filtering, personal rentals, admin panel, and responsive layout.
- Permanent deterministic audit findings plus schema-validated, additive OpenRouter findings.
- Critical API tests, reproducible builds, dependency audit, and Docker packaging.

### ⚡ Shortcuts and “hacks”

| Shortcut | Why acceptable for this MVP | Production future |
|---|---|---|
| Bearer token in browser local storage | Keeps the two-process Vue/FastAPI demo small and inspectable | Secure, SameSite, HttpOnly session cookie; CSRF protection; rotation/revocation |
| SQLite and in-process seeding | Portable, zero-service review environment | PostgreSQL migrations, managed backups, connection pooling, multiple workers |
| Keyword damage classifier as guaranteed fallback | Deterministic demo catches all supplied safety traps without an API key | Evaluated classifier/policy engine, confidence thresholds, human resolution workflow |
| Synchronous OpenRouter audit request | Inventory is tiny and a reviewer expects immediate feedback | Background job, timeout/retry budget, persisted audit runs and cost/latency telemetry |
| Seeded demo passwords | Makes a public assessment immediately reviewable | One-time bootstrap flow, secret manager, reset/MFA, forced password rotation |

### ⚠️ Partial or missing

- The rental table tracks new activity, but the seed contains no full historical events for its pre-existing In Use item; only the supplied assignee can be preserved.
- No password reset, MFA, user disable/delete, pagination, or file attachments.
- Audit findings can be rerun but are not yet assigned, resolved, or retained as versioned audit runs.
- Serial number and category (from the Figma form) exist for newly created hardware but are deliberately absent on the seeded rows: the source file carries neither, and inventing serials would violate the same never-fabricate-data policy the loader enforces.
- The "Inventory live" indicator is cosmetic; refresh is manual. Real-time push (polling or WebSockets) is out of scope for this MVP, though every mutation already returns the updated row.

### 🔮 Next steps: the next 24 hours

1. **Production identity and storage:** move to PostgreSQL/Alembic and secure cookie sessions with admin bootstrap, password reset, rate limits, and audit logging.
2. **Close the safety loop:** persist auditor runs, add accept/resolve actions, require service notes before repair completion, and evaluate LLM findings against a labeled fixture set.
3. **Operational polish:** add Playwright accessibility/mobile flows, pagination, optimistic concurrency versions, richer rental history, and deployed observability/backups.

Two further directions, in the owner's own words:

- *additional ai features depending on the user & admin needs*
- *improved visibiity and access of ai inventory audit, potentially changing font/component size for ease of use*

## AI development log

### Tooling: the exact pipeline

The build ran as a relay between tools, each chosen for what it is best at, all inside **VS Code**:

1. **Claude (web chat)** — the initial hour-by-hour timeboxed plan: stack choice, commit discipline, the data-boundary rules, and what to cut if time ran out.
2. **Codex (GPT-5.6 Sol)** — the implementer: repository inspection, architecture, code, debugging, tests, and the incremental commit trail.
3. **Claude Opus 4.8 (Claude Code)** — the independent reviewer: read every line Codex produced, verified claims by running the code rather than trusting summaries, and prepared the corrective prompts fed back to Codex.
4. **Claude Fable 5 (Claude Code)** — finished the build (auditor redesign, security gates, Figma form alignment), ran the live verifications against OpenRouter and the Render deployment, and wrote the final review.

Using **different models for implementation and review** is deliberate: a model reviewing its own output tends to agree with itself. The reviewer caught what the implementer's green tests could not — including the finding that the AI feature contributed zero findings in production — and the implementer, in turn, rejected parts of the reviewer's proposed fixes with evidence (documented below). Both directions of pushback are in the prompt trail.

Supporting tools: the **Figma published prototype** for layout vocabulary, **OpenRouter's routing and structured-output documentation** (verified against the live models API, not memory), and **pytest, FastAPI TestClient, Playwright, Vite, npm audit, and Git** for verification.

### Prompt trail: full transparency

The complete, contemporaneous history is in [prompts.md](prompts.md) — **16 logged milestones capturing ~35 architecture-shaping prompts**, recorded when they were issued, never reconstructed. The ones that mattered most:

1. **The timeboxed build plan** (owner) — the hour-by-hour plan that fixed the stack, the commit discipline, and "the loader is where points live: it must reject or flag the bad records, not swallow them."
2. **The data-boundary prompt** (owner + reviewer) — "Never use an ID-keyed dictionary that could silently overwrite duplicate id 4." Written *before* the loader existed; the trap never fired because it was anticipated.
3. **The rule-first inversion** (reviewer) — LLM findings originally *replaced* deterministic findings; the prompt made rules the permanent safety floor and the model additive only.
4. **The wire/trust schema split** (reviewer) — the generated JSON schema would have been rejected by the live provider; every mocked test was green. The prompt separated a boring provider-compatible wire schema from the rich local validation schema.
5. **The independent-pass redesign** (reviewer, corrected by implementer) — after the live run revealed the model contributed nothing, the reviewer proposed removing `import_issues` from the payload entirely; the implementer correctly objected that rejected rows would become invisible, and the final design sends raw evidence without the loader's conclusions.
6. **The production/demo separation** (implementer, correcting the reviewer) — `APP_ENV` and `DEMO_MODE` as independent controls, because "a public demo is still production" and must never run on the development signing secret.

Prompts 5 and 6 are the ones to read if you read only two: each is one AI system catching the other's mistake, with the correction reasoned from evidence.

### The correction

The real correction was not the anticipated duplicate overwrite—the loader was designed to prevent that before its first implementation. Instead, the generated admin delete route declared HTTP `204 No Content` while still using FastAPI's default JSON response behavior. FastAPI refused to import the application because a 204 response cannot carry a body. I caught it in the rental API smoke test, changed the endpoint to return an explicit empty `Response`, reran the entire flow, and committed the correction separately as `fix empty hardware delete response`. This was a useful reminder that type/status contracts deserve runtime verification even when the business logic itself looks correct.

The later AI review found a more important design correction: live LLM findings replaced the deterministic audit rather than extending it. That made the least predictable component authoritative. The fix made rules permanent, treated model JSON as untrusted input, added schema/ID/deduplication guards, and exposed rejected model output in the response. I also verified the suggested OpenRouter fallback request against its official documentation and avoided repeating the primary model in the fallback array.

**The correction that matters most came last, and only from running the thing for real.** With the key finally in place, the live audit succeeded — schema accepted, response validated, every test green — and returned `accepted_findings: 0`, with all nine model findings dropped as duplicates of the rule engine's. The AI layer was contributing exactly nothing; the report was identical with it switched on or off.

The cause was mine, not the model's. The evidence payload included `import_issues` — the rule engine's own conclusions — so the model dutifully restated the nine findings it had just been shown, and the deduplication threw all nine away. I had handed it the answer key and then penalised it for copying.

The first proposed fix was to send only the accepted inventory, and that was wrong too: rejected records never reach the `hardware` table, so the model would have been blind to the duplicate ID, the unknown status, and the unparseable date — the assignment's central traps. The correct payload is the accepted inventory *plus the raw source rows*, minus the loader's conclusions. Evidence without the answer.

Reframing agreement as corroboration rather than duplication turned nine wasted calls into a real signal: seven corroborations, two findings the model missed, and one genuine discovery the rules cannot express. **Every one of these bugs passed a full suite of green tests, because the tests were mocked — they were testing my assumptions, not reality.**

A second review then caught the remaining gap between “the mocks pass” and “the provider accepts the request.” Generating the wire schema directly from the rich Pydantic model leaked unsupported constraints and an open-ended evidence object into the provider request. The correction separated concerns: a hand-written provider-compatible wire schema now requests simple strings and closed objects, while Pydantic retains the stronger length, pattern, enum, and result validation locally. A schema-contract test prevents those provider-incompatible keywords from returning, and a skipped-unless-credentialed integration test is the final proof gate. This is the strongest correction story in the project because it demonstrates verifying AI-generated integration code against the real external contract instead of trusting green mocks.

### Design justification

The supplied wireframe was treated as inspiration, as requested. I retained its information architecture—sidebar, inventory table, admin area, centered form language—but used a dark editorial login panel, serif display type, higher-contrast safety states, and a dedicated audit report. This keeps the review path familiar while giving the highest-scoring safety feature an obvious home.

## Repository notes

The source assessment PDF is intentionally ignored and excluded from Docker because it is marked confidential. The public repository contains the implementation and required seed fixture, not the assessment document itself.
