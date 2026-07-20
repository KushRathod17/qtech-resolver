# QTech Resolver — Project Deep Dive (Interview Prep)

## 1. What it is, in one breath

QTech Resolver is a multi-tenant, Jira-style ticketing and workflow application built for QTech Software, a B2B travel-tech company. It tracks bugs and tasks across a Kanban board, routes tickets through a cross-team handoff workflow (Support → Testing → Development → back to Testing → Done), enforces SLA response targets, tracks sprints with burndown/velocity charts, and produces management-facing reports with PDF export. It's built as a fully separate backend API and frontend single-page app, deployed for free with no credit card anywhere in the stack.

If asked "why build this instead of using Jira": the honest answer is it's a learning/ownership exercise that also happens to fit QTech's actual workflow (a cross-team support→dev→testing handoff chain with custody tracking) more precisely than a generic tool would, at zero licensing cost.

---

## 2. Architecture at a glance

Two independently deployed services talking over HTTPS:

- **Backend**: Python, FastAPI, REST JSON API, PostgreSQL via SQLAlchemy ORM, Alembic for migrations, JWT-based auth.
- **Frontend**: React 19 single-page app built with Vite, talking to the backend purely through `fetch`/axios — no server-side rendering, no coupling to the backend's language or process.

This split matters for the pitch: either half can be redeployed, rewritten, or scaled independently. The API has no knowledge of HTML/React; the frontend has no knowledge of SQL. The contract between them is the OpenAPI schema FastAPI generates automatically from the Pydantic models.

---

## 3. Backend: technology and why each piece was chosen

**FastAPI** — the web framework. Chosen over Flask/Django for three concrete reasons: it validates every request body and query parameter automatically against Pydantic schemas (so malformed input is rejected before any handler code runs), it generates interactive API docs for free (`/docs`), and its dependency-injection system (`Depends()`) is what makes the auth model clean — `current_user: User = Depends(get_current_user)` on a route signature is both documentation and enforcement in one line.

**SQLAlchemy (ORM) + PostgreSQL** — the data layer. Postgres was chosen over SQLite/MySQL for real foreign-key enforcement, proper enum types, and because it's what every free-tier host (Render, Neon, Railway) actually offers well. SQLAlchemy's ORM is used throughout rather than raw SQL so that query filters compose (see the Reports section below — one `get_tickets()` function underpins report queries, the board view, the Issues table, and search, all by passing different filter kwargs into the same query builder).

**Alembic** — schema migrations. Every model change goes through a generated migration script rather than `create_all()`, specifically because `create_all()` only adds missing tables — it silently no-ops on a changed column, which is exactly the kind of bug that looks fine in dev and corrupts prod.

**Pydantic** — the schema layer (`schemas.py`), separate from the ORM layer (`models.py`). This split is a real, intentional architectural decision: the ORM model is the source of truth for what's *stored*; the Pydantic schema is a contract for what's *exposed*. A `UserOut` schema, for instance, never includes the password hash, even though `User` the ORM model has that column — the leak is prevented structurally, not by remembering to strip a field in every handler.

**python-jose + passlib/bcrypt** — JWT issuing/verification and password hashing. Tokens carry `sub` (user id) and `role`, signed with a server secret, expiring after a configured window. Passwords are bcrypt-hashed with a per-password salt; the codebase deliberately pins `bcrypt==4.0.1` because newer bcrypt releases removed an attribute `passlib` 1.7.4 reads at import time — a real, previously-hit compatibility bug worth mentioning if asked about dependency pinning.

**A hand-rolled in-process rate limiter** (`ratelimit.py`) on the login endpoint — a fixed-window counter keyed by email/IP that only counts *failed* attempts (a correct password never locks out a legitimate busy user) and resets on success. Deliberately dependency-free rather than pulling in Redis, with the trade-off explicitly documented in the code: it's per-process (fine for a single-worker deployment, would need a shared store like Redis if scaled to multiple workers) and resets on restart (acceptable, since an attacker who can restart the server has already won). This is a good example to bring up if asked "tell me about a security decision you made and its trade-offs" — it shows awareness of the limitation rather than a false sense of completeness.

**boto3 + a storage abstraction** (`storage.py`) — file uploads (attachments, avatars) go through a small interface with two implementations: `LocalDiskStorage` (writes to disk, used in dev/tests) and `S3Storage` (writes to any S3-compatible bucket via boto3). Which one is active is decided once at import time based on whether `S3_BUCKET_NAME`/`S3_ENDPOINT_URL` are set — the rest of the app just calls `storage.put()`/`storage.get()`/`storage.delete()` and never knows which backend it's talking to. This is the classic "program to an interface" pattern, and it's what let the app move from local-disk storage to Backblaze B2 in production without touching a single route handler.

**reportlab** — pure-Python PDF generation (`pdf_report.py`, `pdf_ticket.py`), chosen specifically because it has no system-level dependency (unlike `wkhtmltopdf` or `weasyprint`, which need a browser engine installed on the host). That matters concretely: Render's free tier gives you a container you can't `apt-get install` into, so a PDF library that's "just pip install" was a hard requirement, not a preference.

---

## 4. The domain model — what's actually being tracked

Twenty-three ORM models, but the ones worth being able to explain individually:

- **Organization** — the tenant boundary. Every other table carries an `organization_id` foreign key, and every query in `crud.py` filters on it. This is what makes the app multi-tenant: QTech's data and a second company's data can never leak into each other's queries, because the query itself is incapable of returning cross-org rows.
- **User** — has a `role` (`admin` / `manager` / `developer`), belongs to one `Organization`, optionally belongs to a `Team`.
- **Ticket** — the core entity. Has `status` (backlog/todo/in_progress/code_review/done), `priority`, `ticket_type` (task/bug/subtask, collapsed down from an earlier 5-type model), a `task_category` sub-classification for tasks, and — specifically for bugs — `steps_to_reproduce`, `expected_behavior`, `actual_behavior`, `environment_stage`, `browser_version`. It supports sub-tasks (self-referential `parent_id`) and can be grouped under a `ParentTag`.
- **TicketHandoff** — the cross-team chain-of-custody log. One row per handoff: who sent it, who received it, when, and what action was taken (`raised`, and others keyed off `HandoffAction`, deliberately stored as a plain string rather than a Postgres enum type specifically so a new action can be added without a schema migration). Critically, *how long someone held a ticket is a derived value, not a stored column* — `crud.build_timeline()` computes it from the gap between consecutive `sent_at` timestamps. This avoids a classic bug where a stored duration and a stored timestamp silently drift apart.
- **Team** — has a `kind` (support / testing / development / other) that the workflow state machine keys off of, rather than keying off the team's *name* — so renaming "QA" to "Testing & QA" doesn't break routing logic.
- **SLAPolicy** — one row per (organization, priority), an optional response-time threshold in hours. Breach status is computed at read time by comparing elapsed time against the threshold, not stored and recalculated on a cron.
- **Sprint** — has a `state` (planned/active/completed), backs the burndown and velocity charts.
- **Label**, **ParentTag** — tagging and grouping. ParentTag is a deliberate generalization of what used to be a rigid Epic concept: it's "a lightweight label-of-labels" that can group any tickets together (a client project, a feature initiative) without forcing every grouping to look like a top-of-hierarchy Epic ticket.
- **Comment**, **ActivityLog**, **Notification** — the collaboration layer. ActivityLog is the audit trail (status changes, assignment changes, comments) and is specifically what the Reports feature's "staleness" calculation reads from, rather than the ticket's own `updated_at` column — because `updated_at` only reflects a direct column edit and would miss "someone commented three times but the status never changed," which is exactly the kind of ticket a manager wants flagged as needing attention.
- **Attachment** — file metadata; the actual bytes live in whichever storage backend is active.
- **SavedFilter** — a named, optionally-pinned filter query a user can save and re-apply with one click (e.g. "my open criticals").

---

## 5. Multi-tenancy and security

The whole app is designed so one deployment serves many organizations, each fully isolated:

- Every table that holds tenant data carries `organization_id`.
- Every `crud.py` query function takes `organization_id` as a required parameter and filters on it — there's no code path that queries "all tickets" without a tenant filter attached.
- Signup has two flows: **create a new organization** (always allowed — anyone can start a new tenant) or **join an existing one** (gated by an optional allowed-domain list, and always requiring a join code; the domain check is case-insensitive and rejects lookalike domains). An admin can still add anyone directly regardless of the domain rule, for the case of contractors or an email that doesn't match the company domain.
- A dedicated security audit pass (using a subagent to review the codebase specifically for tenant-isolation gaps) found and fixed a real cross-organization data leak: the avatar-serving endpoint checked ownership for ticket attachments but not for avatars, meaning a user from Org A could potentially fetch Org B's avatar image by guessing/enumerating the filename. Fixed by adding the same organization-ownership check that attachments already had. This is a strong story for "tell me about a bug you found and fixed" — it demonstrates both the audit methodology (systematically comparing parallel code paths for consistency) and the fix.
- Files are **never** served as static assets. Early in the project, `/uploads` was mounted as a static directory, meaning anyone with a URL — logged in or not — could fetch any attachment or avatar, with UUID filenames as the only protection (unguessable is not the same as protected). This was replaced with an authenticated route (`routers/files.py`) that checks the requester's organization and, for attachments, their access to the specific ticket, before streaming any bytes back.
- Passwords are bcrypt-hashed, JWTs are short-lived and carry the role so authorization checks don't need a database round-trip on every request, and login is rate-limited per the `ratelimit.py` design above.

---

## 6. The cross-team workflow engine

This is the most domain-specific piece of engineering in the app, and worth walking through end to end if asked "what's the most complex thing you built":

A ticket raised by Support can be routed into a workflow: it's handed to Testing to reproduce, handed to Development to fix, handed back to Testing to verify, and closed. Each handoff is a `TicketHandoff` row. At any point, the ticket knows:

- who currently holds it (`current_team`, `current_assignee` — denormalized onto the ticket for fast reads, since "what's on my desk right now" is the single most common query)
- what actions are legally available next, computed server-side from the current state (`available_actions` — the frontend never has to encode the state machine's rules itself; it just renders whatever buttons the server says are valid, which means the UI *cannot* offer an action the server would reject)
- how many teams have touched it, how many handoffs it's had, and total time open
- for each leg of the chain, how long that team/person held it

The Reports feature's "By employee" and per-ticket PDF export both build on this: the per-ticket PDF's "chain of custody" table is literally `crud.build_timeline()`'s output rendered into a document, so the same derivation that powers the live UI timeline powers the exported PDF — one source of truth, two presentations.

---

## 7. The Reports feature (the most recently built piece)

Built in four explicit phases after a planning pass, because it's the feature with the most moving parts:

**Backend queries** — four report functions in `crud.py`, all built on top of the same `get_tickets()` filter function everything else uses (status, assignee, label, product, team, date range), so a report and a board view can never disagree about what "matches these filters" means:
- `report_overview` — total tickets, breakdown by status, total/completed story points.
- `report_stale_tickets` — open tickets with no `ActivityLog` entry in N days (configurable threshold), sorted oldest-touched first.
- `report_by_employee` — per person: assigned/in-progress/done counts and completed points.
- `report_by_label` — per label: total/done counts and points, which is how a label named e.g. "payment issue" doubles as an ad-hoc "how's this problem area doing" report without the code needing any special knowledge of what the label means.

**Frontend** — a filter bar (date range, employee, label, product, team, and a stale-threshold selector) drives five sections: overview stats, an ongoing-tickets table, a not-touched table, a done table, a per-employee progress table, and a per-label bar chart rendered as hand-rolled SVG (see the charts note below) rather than a charting library.

**PDF export, two flavors**:
- A whole-report PDF (`pdf_report.py`) mirrors the in-app page section-for-section, generated fresh on every request (not cached) so it's never stale.
- A per-ticket PDF (`pdf_ticket.py`) is a full document for one ticket: dates, people, description, bug-report fields if applicable, every comment with author/timestamp, the full activity log, and the chain-of-custody table with hold durations — accessible via an "Export PDF" button on the ticket detail panel.

**Search** — the existing ticket search (title/description/client) was extended to also match the assignee's name via a SQLAlchemy `.has()` relationship filter, so typing an employee's name in the same search box finds what they're working on, and a quick-search box on the Reports page surfaces matching tickets by key, title, or employee name and jumps straight to the ticket's detail panel.

**Verification approach**: rather than mocking the database, each phase was verified against a real, throwaway PostgreSQL instance (`pgserver`, spun up fresh per test run) with a FastAPI `TestClient` driving actual HTTP requests through the real app — login, then hit the actual endpoints — including a deliberate cross-organization check (an org B user must get a 404, not someone else's ticket, when trying to export it) and a "bare ticket with no comments/handoffs" case to make sure the PDF's empty-state branches don't crash.

---

## 8. Frontend: technology and structure

**React 19 + Vite 8** — Vite for fast dev-server startup and a build step that's just `npm run build`, which matters for the deployment story (see below): the build-time environment variable (`VITE_API_URL`) gets baked directly into the JS bundle at build time, so the frontend doesn't need any runtime configuration once deployed as a static site.

**react-router-dom 7** — client-side routing between pages (Board, Backlog, Issues, Reports, Sprints, Workflow, People, Parent Tags, Profile, Settings).

**@dnd-kit** — drag-and-drop for the Kanban board columns, chosen over the older `react-beautiful-dnd` (unmaintained) for its accessibility support and active maintenance.

**axios** — the HTTP client, wrapped in a small `resources.js` module that exposes one object per resource (`ticketsApi`, `reportsApi`, `usersApi`, etc.) so every component calls e.g. `ticketsApi.list(filters)` instead of hand-building URLs and query strings inline.

**No charting library.** Every chart — burndown, velocity, per-team holding-time bars, per-label bars — is hand-rolled SVG built from a small shared toolkit (`chartUtils.js`: a validated colour pair for accessibility, "nice" axis-tick generation, a rounded-rect bar path helper). This was a deliberate choice: the charts are simple enough (a handful of bars or one line) that a full charting library would be a large dependency for very little benefit, and hand-rolled SVG means every chart also renders as a plain HTML table alongside it for accessibility — a WCAG-conscious pattern that's easy to explain and defend if asked "why not just use Chart.js."

**Authenticated file fetching.** Since `/uploads` requires a bearer token and a plain `<img src="...">` can't send one, avatars and attachments are fetched via `axios` as a blob and turned into an object URL (`useFileUrl` hook, with an in-memory cache so the same avatar isn't re-fetched for every card it appears on). This is a real, slightly non-obvious frontend problem worth mentioning: "how do you show an authenticated image" doesn't have an `<img>`-tag-only answer.

---

## 9. Deployment: the constraint that shaped every choice

The explicit requirement was: deployed, always-on, reachable by teammates, **zero cost, no credit card anywhere** — including on services that normally ask for one "just to verify you're not a bot," even for their free tier.

The stack that satisfies that:

- **Render** — hosts both the backend (a Python web service) and the frontend (a static site), deployed together from one `render.yaml` Blueprint file so both services are defined, versioned, and redeployed together from a single push.
- **Neon** — managed Postgres. Chosen specifically over Render's own free Postgres, which auto-deletes after 30 days — Neon's free tier doesn't expire.
- **Backblaze B2** — S3-compatible object storage for attachments/avatars, chosen over Cloudflare R2 after R2 turned out to require a card even for its free tier; a private B2 bucket needs no card at all, and since the app always proxies files through the authenticated backend (never serves a public bucket URL directly), a private bucket is exactly what's needed anyway.

**Two real free-tier constraints hit and worked around**, worth mentioning as "debugging a deployment platform's undocumented rules":
- Render's free tier doesn't support `preDeployCommand` (a paid-plan-only feature), so database migrations (`alembic upgrade head`) run as the tail end of the *build* command instead.
- A static site service in `render.yaml` has no `plan` field at all (only compute services do) — including one caused a Blueprint validation error that isn't obvious from the docs.

**Render's free-tier sleep behavior** (web services spin down after 15 minutes idle, then take 30–60 seconds to wake on the next request) was confirmed *not* to cause data loss — a real "the data is gone!" scare during testing turned out to be a UI/filter misunderstanding, not the database resetting, which is worth knowing cold if asked "what happens on the free tier when nobody's used it in a while."

---

## 10. Engineering practices worth naming explicitly

If asked "how do you approach a change like this," these are the actual patterns used throughout, not just claimed:

- **Plan, then execute, phase by phase**, especially for multi-part features (the Reports feature: backend queries → frontend → PDF export → verification, each phase confirmed working before the next starts).
- **One source of truth, multiple presentations** — the same `get_tickets()` filter function backs the board, Issues table, search, and every report; the same handoff-timeline derivation backs the live UI and the exported PDF. This avoids the class of bug where "the report says something different from the board" because they're independently reimplemented.
- **Program to an interface for anything environment-dependent** — the storage abstraction (`LocalDiskStorage` vs `S3Storage`) means local development and production never need different application code, only different configuration.
- **Real functional tests over mocked ones** where practical — spinning up an actual throwaway Postgres and driving actual HTTP requests through the real FastAPI app catches integration bugs (wrong parameter names, a missing import, a serialization mismatch) that a pure unit test with everything mocked would miss entirely.
- **Security review as an explicit, separate pass**, not just something hoped to fall out of normal development — the cross-org avatar leak was found precisely because tenant isolation got its own dedicated audit rather than being assumed correct because "the other endpoints do it right."

---

## Quick reference: if asked to summarize in 30 seconds

"It's a multi-tenant ticketing system with a FastAPI/Postgres backend and a React frontend, deployed on a completely free stack (Render, Neon, Backblaze). The interesting engineering is in three places: tenant isolation (every query scoped to an organization, verified by a dedicated security audit that caught a real leak), a cross-team handoff workflow that tracks chain-of-custody with derived — not stored — hold durations, and a reports layer that reuses the exact same filtering and workflow logic as the live UI so the PDF exports can never drift from what's on screen."
