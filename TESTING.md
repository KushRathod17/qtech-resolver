# Running the tests

## Backend (pytest) — 79 tests

**TERMINAL (backend):**

```powershell
cd "C:\Users\Kanishk\OneDrive - Qtech\Desktop\project\qtech-resolver\qtech-resolver\backend"
venv\Scripts\activate
python -m pytest
```

Postgres must be running first (`.\scripts\start-db.ps1`).

Tests run against a **separate `qtech_resolver_test` database**, created on first
run and rebuilt from the models before every test. **Your dev data is never
touched** — a suite that can destroy your working data is a suite you stop
running.

Useful flags:

```powershell
python -m pytest tests/test_sla.py     # one file
python -m pytest -k breach             # tests matching a name
python -m pytest -x                    # stop at the first failure
python -m pytest -v                    # show every test name
```

## Frontend (vitest) — 17 tests

**TERMINAL (frontend):**

```powershell
cd "C:\Users\Kanishk\OneDrive - Qtech\Desktop\project\qtech-resolver\qtech-resolver\frontend"
npm test           # run once
npm run test:watch # re-run on save
```

No database or backend needed — these cover pure logic only.

---

# What's covered, and why

The tests exist to pin down behaviour whose **failure mode is silent** — where a
regression still returns `200`, still renders, and is simply wrong.

**Security** (`test_security.py`) — the cases where a regression is a
vulnerability, not a bug:

- An attachment named `../../../../pwned.txt` must not escape the upload directory.
- Registration and profile-edit must not grant a role.
- The last admin must not be able to demote themselves and lock everyone out.
- A saved filter must strip unknown keys — it's replayed into the board query.
- Saved filters are private (404, not 403 — their existence isn't your business).
- You can't delete someone else's attachment.

**SLA** (`test_sla.py`) — the subtlest logic in the app:

- A ticket raised 10 days ago but **resolved within its window MET its SLA**,
  even though 10 days have since passed. If the clock measured to `now` instead
  of `resolved_at`, every closed ticket would eventually read as breached.
- …but freezing the clock must not turn a genuine miss into a pass.
- All three routes to Done (edit form, drag-and-drop, bulk) stop the clock. The
  result must not depend on *how* you closed the ticket.

**Hierarchy** (`test_hierarchy.py`):

- Converting a ticket to an epic **promotes** its sub-tasks rather than letting
  the `ON DELETE CASCADE` silently destroy them.
- Sub-tasks are hidden from the board, or the work is double-counted.
- Epic progress prefers story points over ticket count.

**Frontend** — two pure functions that shipped real bugs:

- `niceTicks` once returned a top tick **below** the max value, so the tallest
  bar rendered outside the plot. It was broken for **282 of the first 500
  integers**; the property test walks all of them.
- The command palette's fuzzy matcher ranked `QTR-19 — work item 4` above
  `QTR-4` for the query `qtr4`. Typing a key must find that ticket.

Both were verified to **fail against the original implementations** — a test
that has never failed hasn't proven anything.

## Known gaps

- **No component/interaction tests.** Drag-and-drop, the board, and the modals
  are unverified by machine; they've only been exercised by hand.
- **The Alembic migrations themselves aren't tested.** The schema under test is
  built by `create_all()` from the models, so a migration that drifts from the
  models would not be caught here. `alembic upgrade head` on a scratch database
  is the check that would catch it.
