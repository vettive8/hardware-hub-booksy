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
