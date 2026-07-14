# Prompt trail

This file is updated while the project is built; prompts are recorded at the time they shape the implementation rather than reconstructed after the fact.

## 2026-07-14 — Initial assignment

> 8:00 to 8:30. Setup. Create the repo, paste the Figma frames into Claude Code, drop the seed JSON into the project. First commit: "scaffold." Stack: Python plus FastAPI plus SQLite for the backend, Vue for the frontend since they gave Figma and prefer Vue. If Vue fights you, fall back to plain HTML and JS and write one line in the README saying why. Tell Claude Code your choice up front.
>
> 8:30 to 9:30. Backend core. Schema, a seed loader, auth, and endpoints to list hardware and users. The loader is where points live: it must reject or flag the bad records, not swallow them. Commit per piece.
>
> 9:30 to 10:30. Business logic. Rent and return with guards that block renting anything In Use, in Repair, or flagged damaged. Admin add, delete, toggle repair. Commit.
>
> 10:30 to 11:30. Frontend. Wire the Figma screens: login, dashboard with sort and filter, admin panel, rent and return buttons. Commit.
>
> 12:00 to 1:00. The AI Inventory Auditor. Feed the inventory to the LLM and have it flag the contradictions: duplicate id 4, the 2027 future date, the "Appel" typo and odd date format, the Unknown-status record, the Dell and MacBook marked Available despite damage notes. This is the highest-scoring feature. Commit.
>
> 1:00 to 1:45. Three tests. Cannot rent broken hardware. Cannot rent something already In Use. Duplicate id is rejected on load. Commit.
>
> 1:45 to 2:30. README and AI log. This is weighted heavily, so don't rush it. Fully implemented, shortcuts with why and future, partial or missing, the 24-hour roadmap, tooling, data strategy listing every trap you caught, prompt trail, and the one "correction" moment.
>
> 2:30 to 3:00. Deploy to Railway or Fly. A live link is an explicit plus.
>
> 3:00 to 3:30. Final pass, then submit by replying to the email.
>
> Three things that decide your score, so keep them running all day, not at the end. Commit small and often with real messages, because they read the history. Paste every prompt into a prompts.md as you go, never reconstruct it later. And write down one real moment the AI got something wrong, for the required "correction." Your best candidate is already in the plan: Claude Code will likely load the seed blind and silently overwrite id 4, you catch it, you add a duplicate-key guard. That's honest and it's exactly the audit skill they're testing.
>
> look pdf, create github repo and push, public

## 2026-07-14 — Tool and stack choice stated up front

> Use Codex as the AI engineering partner. Build the preferred stack: Python 3.12 + FastAPI + SQLite for the API and Vue 3 + Vite for the UI. Preserve every malformed seed record in an import report, reject invalid rows from the operational database, and make duplicate IDs a hard, observable error. Follow the supplied Figma wireframe's restrained gray sidebar/card/table visual language. Do not commit the confidential assessment PDF.

## 2026-07-14 — Data boundary prompt

> Design the seed loader before the CRUD routes. Validate IDs, required fields, allowed statuses, ISO dates, future dates, likely brand typos, and damage language. Reject structurally unsafe rows, retain accepted-but-suspicious rows with explicit safety flags, and persist every issue with the original raw JSON so the audit is explainable. Never use an ID-keyed dictionary that could silently overwrite duplicate id 4.

## 2026-07-14 — Auth and query prompt

> Add a small but real authentication boundary: PBKDF2 password hashes, expiring signed bearer tokens, an admin role guard, and server-side account creation. Keep list sorting safe by mapping accepted sort keys to SQL columns rather than interpolating arbitrary client input. Seed reviewer-friendly demo accounts without exposing a production credential pattern.

## 2026-07-14 — Rental state-machine prompt

> Implement rent and return as guarded state transitions under an immediate SQLite transaction. Renting must atomically require Available and not damaged; returning must require In Use and ownership (or admin). Admin repair toggles must not bypass an active rental, and deleting an In Use item must be blocked. Return repaired items to availability only through an explicit repair-complete toggle.

## 2026-07-14 — Correction prompt (recorded when it happened)

> The API import failed because the generated delete endpoint combined status 204 with FastAPI's default JSON response behavior. Correct it by using an explicit empty `Response`, then rerun the complete rental smoke flow before continuing. Document this actual framework-contract mistake instead of claiming the anticipated duplicate-overwrite scenario happened.

## 2026-07-14 — AI Inventory Auditor prompt

> Build an explainable auditor that sends accepted inventory plus the persisted rejected-row evidence to the OpenAI Responses API when an API key is present. Require JSON findings grounded in evidence. Keep a deterministic rules audit as an offline and failure fallback so a reviewer can always see the duplicate ID, 2027 date, Appel/odd-date row, Unknown-status row, and both damage/status contradictions. Clearly label which mode produced the result; never pretend the fallback was an LLM response.

## 2026-07-14 — Frontend prompt

> Translate the supplied Figma prototype into Vue 3: quiet gray surfaces, fixed sidebar, compact data table, card-based metrics, and a focused split-screen login. Implement responsive login, inventory search/filter/sort, rent/return actions, personal rentals, admin account/hardware forms, repair/delete controls, visible errors, and a first-class AI audit screen. Favor accessible native controls and clear safety-disabled states over decorative animation.

## 2026-07-14 — Critical tests prompt

> Add API-level tests for the three scored invariants: damage language creates a safety hold that blocks rent; an In Use item cannot be rented; and a duplicate seed ID is rejected without replacing the first record. Add one happy-path rent/return test to prove the guards do not prevent valid transitions. Assert response semantics and persisted state, not implementation details.

## 2026-07-14 — Deployment prompt

> Package the Vue production build and FastAPI API as one portable Docker service. Serve built assets only when present so Vite development still works, persist SQLite at a configurable DATABASE_PATH, expose a health check, and add Railway configuration. Keep the confidential assessment PDF out of both Git and Docker contexts.

## 2026-07-14 — Documentation prompt

> Write the README as an engineering handoff and decision record, not a feature checklist. Include reproducible setup, demo access, architecture, API surface, exact seed outcomes and every caught trap, rental invariants, tests, deployment, fully implemented work, shortcuts with why/future, partial work, a prioritized 24-hour roadmap, tooling, Figma justification, prompt trail, and the real FastAPI 204 correction. Be explicit that Codex—not Claude Code—was used and that OpenAI mode is optional and labeled.

## 2026-07-14 — Auditor hardening review

> Rework the AI Inventory Auditor. Deterministic findings must always run and remain the safety floor; the LLM may only add findings. Merge by `(hardware_id, code)`, label sources, and let rules win duplicates. Parse model output through Pydantic, discard an invalid model layer with an explicit status, reject IDs absent from the source seed, and surface hallucination-drop counts. Move the optional provider to OpenRouter with a small primary model and cross-vendor fallback, zero temperature, JSON output, updated environment variables, documentation, and regression tests. Also remove application-side `MAX(id) + 1` allocation and require a deliberate service-note workflow before repair completion clears damage.

## 2026-07-14 — Verification correction

> Verify the reviewer-proposed provider call against OpenRouter's official documentation before coding it. The docs establish that `model` is attempted first and `extra_body.models` supplies later fallbacks, so do not repeat the primary in that array. Use JSON mode plus strict application validation because the chosen primary is not listed among the models guaranteed to support strict JSON Schema outputs.

## 2026-07-14 — Live capability correction

> Recheck the exact primary and fallback records in OpenRouter's live Models API. Both currently advertise `response_format` and `structured_outputs`, which is stronger evidence than the general guide's incomplete example list. Upgrade the request to strict JSON Schema, require providers that support the requested parameters, and keep Pydantic validation as defense in depth.
