# Hardware Hub

An AI-native internal hardware rental system built for the Booksy Early Careers technical assessment. Hardware Hub combines guarded inventory workflows with an explainable auditor that catches unsafe or contradictory data before it reaches employees.

**Stack:** Python 3.12 · FastAPI · SQLite · Vue 3 · Vite · OpenRouter through the OpenAI-compatible SDK (optional)

## Technology reports

- [Interactive build dossier](build-report.html) — assignment coverage, architecture, seed strategy, guarded workflows, Gemini fact-check, API explorer, test evidence, Git history, and submission readiness.
- [OpenRouter engineering report](technology-report.html) — current integration, searchable live model catalog, capability roadmap, security boundaries, and official sources. Open it directly in a browser; the catalog request is public and never reads `.env`.
- [Pre-deployment code review council](code-review-report.html) — code findings, demo-account decision, platform matrix, and a local Codex–Claude approval workspace. It does not read `.env` or change the application.

## Product tour

- Account-only login with admin-created users, PBKDF2 password hashes, expiring bearer tokens, and role guards.
- Sortable, filterable hardware inventory with clear availability and safety-hold states.
- Atomic rent/return transitions that block damaged, repaired, or already-rented equipment.
- Admin command center for accounts, hardware, deletion, and repair lifecycle controls.
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

The API and Vue build ship as one Docker service. SQLite lives at `DATABASE_PATH`; Railway should attach a persistent volume at `/data`.

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

The required critical tests are in `tests/`:

1. Damaged hardware cannot be rented.
2. Hardware already In Use cannot be rented.
3. A duplicate seed ID is rejected without overwriting the original.
4. A valid rent/return flow records owner and state correctly.
5. Without an API key, all nine deterministic audit findings remain present.
6. Unknown model-generated hardware IDs are dropped and counted.
7. Rule/model duplicates resolve in favor of the deterministic finding.
8. Invalid model severity/schema output discards the entire model layer safely.
9. Damaged repair completion requires an explicit resolution note, and SQLite allocates new hardware IDs.
10. The provider wire schema excludes unsupported constraints and closes every object.
11. A live OpenRouter contract test validates the real response and source IDs only when explicitly requested and credentials are present.
12. A headed Playwright suite covers admin, member, responsive, auditor, and interactive-report workflows in Microsoft Edge.

Run everything used before handoff:

```bash
python scripts/run_repo_checks.py --mode full
```

This runs deterministic pytest coverage, a production Vue build, and `npm audit --audit-level=moderate`. It deliberately excludes the paid provider contract test even when `.env` contains a key. Run that proof gate explicitly with `python -m pytest -m integration -s`.

For visible browser QA, start the application with an isolated database and run `npm run test:e2e:headed` from `frontend/`. The Playwright configuration uses installed Microsoft Edge, one worker, traces, video, and screenshots; set `OPENROUTER_DISABLED=1` to guarantee a zero-cost deterministic audit.

## Deployment

The repository includes a multi-stage [Dockerfile](Dockerfile) and [Railway configuration](railway.toml).

```bash
docker build -t hardware-hub .
docker run --rm -p 8000:8000 -e SECRET_KEY=change-me hardware-hub
```

Open `http://localhost:8000`. For Railway, deploy the GitHub repository, attach a volume at `/data`, and set `SECRET_KEY`; `OPENROUTER_API_KEY` is optional.

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
- The Figma prototype included serial/category ideas not present in the required seed; the MVP keeps the assessment's canonical hardware fields to avoid invented migration data.

### 🔮 Next steps: the next 24 hours

1. **Production identity and storage:** move to PostgreSQL/Alembic and secure cookie sessions with admin bootstrap, password reset, rate limits, and audit logging.
2. **Close the safety loop:** persist auditor runs, add accept/resolve actions, require service notes before repair completion, and evaluate LLM findings against a labeled fixture set.
3. **Operational polish:** add Playwright accessibility/mobile flows, pagination, optimistic concurrency versions, richer rental history, and deployed observability/backups.

## AI development log

### Tooling

- **Codex (GPT-5)** drove repository inspection, architecture, implementation, debugging, testing, and the incremental commit trail. The assignment suggested Claude Code; Codex was the available equivalent, and that substitution is stated rather than disguised.
- **Figma published prototype** was inspected for layout vocabulary: gray navigation, cards, compact tables, centered login, and restrained status treatments. The UI remodel adds stronger Booksy-like editorial contrast and makes the auditor a first-class destination.
- **OpenRouter official routing and structured-output documentation** informed the primary/fallback model chain, JSON mode, and the explicit validation boundary.
- **pytest, FastAPI TestClient, Vite, npm audit, and Git** supplied deterministic verification and visible delivery history.

The complete, contemporaneous prompt history is in [prompts.md](prompts.md).

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
