# Deploying QTech Resolver (free tier)

This walks through a real, working deployment at **$0/month, no credit card
anywhere**, using:

- **Render** — hosts the backend (FastAPI) and frontend (static React build).
  Free, no card.
- **Neon** — Postgres, free forever (unlike Render's own free Postgres, which
  auto-deletes after 30 days). Free, no card.
- **Backblaze B2** — object storage for ticket attachments and avatars, since
  a free Render web service has no persistent disk. Free for private buckets,
  no card (Backblaze only asks for a card on *public* buckets, which this app
  never uses — every file is served through the authenticated backend, never
  directly from the bucket).

Everything below is a dashboard/account step you do yourself — none of it
involves handing over credentials to anyone. Total time: 20-30 minutes.

**What you're trading for $0/month:** the backend goes to sleep after 15
minutes of no traffic and takes 30-60 seconds to wake up on the next request;
Neon's free database does the same for its compute (auto-resumes on the next
query, usually under a second); 0.5GB of database storage and 10GB of file
storage. All of this is upgradeable later — paid Render plan, Render's own
managed Postgres, a persistent disk — without touching any application code.
Only env vars and `render.yaml` would change.

---

## Running locally

Three terminals, each left running:

1. **Database** (once per reboot — this is a private, non-service Postgres
   cluster, not the system one):
   ```
   .\scripts\start-db.ps1
   ```
2. **Backend**:
   ```
   .\scripts\start-backend.ps1
   ```
   This runs `uvicorn` with `--host "::"` instead of the default
   `127.0.0.1`. Without it, Chrome's `localhost` can resolve to the IPv6
   address `::1` first, find nothing listening there, and get a connection
   refused — which shows up in devtools as a misleading
   "No 'Access-Control-Allow-Origin' header is present" error that looks
   like a CORS bug but is actually the server never being reached at all.
   `"::"` listens on both IPv4 and IPv6, so `localhost` resolves either way.
3. **Frontend**:
   ```
   cd frontend
   npm run dev
   ```
   Then open the URL it prints (usually `http://localhost:5173`).

## 1. Push the code to GitHub

Render deploys from a Git repo. If this project isn't already on GitHub, push
it there now (a private repo is fine — Render supports those).

## 2. Create the database (Neon)

1. Go to [neon.tech](https://neon.tech) and sign up (free, no card required).
2. Create a new project — name it something like `qtech-resolver`.
3. On the project dashboard, copy the **connection string**. It looks like:
   `postgresql://user:password@ep-something.region.aws.neon.tech/dbname?sslmode=require`
4. Keep this tab open — you'll paste this string into Render in step 5.

## 3. Create the file bucket (Backblaze B2)

1. Go to [backblaze.com/sign-up/cloud-storage](https://www.backblaze.com/sign-up/cloud-storage)
   and sign up — no card required.
2. In the dashboard, **Create a Bucket** — name it `qtech-resolver-uploads`,
   and set it to **Private** (this is also what keeps it free — public
   buckets are the one thing Backblaze asks a card for, and this app never
   needs the bucket to be public).
3. Once created, open the bucket's details page and note its **Endpoint** —
   it looks like `s3.us-west-004.backblazeb2.com` (the region-like code in the
   middle, e.g. `us-west-004`, is your `S3_REGION`).
4. Go to **Account → App Keys → Add a New Application Key**. Scope it to just
   this bucket, with **Read and Write** access. Backblaze shows you two values
   **once** — copy them somewhere safe:
   - **keyID** → this is your `S3_ACCESS_KEY_ID`
   - **applicationKey** → this is your `S3_SECRET_ACCESS_KEY`

You do **not** need to configure CORS on the bucket — the backend proxies
every file through itself (with the same auth + organization check it always
had), so the browser never talks to Backblaze directly.

## 4. Deploy to Render

1. Go to [render.com](https://render.com) and sign up (free, no card required
   for free-tier services).
2. **New → Blueprint**, connect your GitHub account, and select this repo.
   Render finds `render.yaml` at the repo root and shows you the two services
   it defines: `qtech-resolver-backend` and `qtech-resolver-frontend`.
3. Render prompts you for the secret values marked `sync: false` in
   `render.yaml`. Fill in:
   - `DATABASE_URL` → the Neon connection string from step 2
   - `S3_ENDPOINT_URL` → `https://s3.<region>.backblazeb2.com` from step 3
     (the full endpoint you noted, with `https://` in front)
   - `S3_ACCESS_KEY_ID` → the keyID from step 3
   - `S3_SECRET_ACCESS_KEY` → the applicationKey from step 3
   - `S3_BUCKET_NAME` → `qtech-resolver-uploads`
   - `S3_REGION` → the region code from the endpoint (e.g. `us-west-004`)

   Self-service joining (`/auth/signup/join`) is gated by the org's join code
   alone — anyone you share the code with can join, on any email address.
   Rotate the join code from the organization's Settings page if it ever
   leaks. Starting a brand-new organization (`/auth/signup/organization`) is
   never gated — there's nothing to protect until that call creates the org.
4. Click **Apply**. Render builds both services. The backend's
   `preDeployCommand` runs `alembic upgrade head` automatically before each
   deploy, so the database schema is created on this first deploy too — you
   don't need to run migrations by hand.
5. Wait for both services to show **Live** (a few minutes each).

### If the service names come out different

`render.yaml` assumes the backend ends up at
`qtech-resolver-backend.onrender.com` and the frontend at
`qtech-resolver-frontend.onrender.com` (Render normally honors the `name`
field exactly, unless one is already taken). Check each service's actual URL
on its dashboard page. If either differs from what's in `render.yaml`:

1. Open the **frontend** service → Environment → update `VITE_API_URL` to the
   backend's real URL → trigger a manual redeploy (this value is baked into
   the JS bundle at build time, so a restart alone won't pick it up).
2. Open the **backend** service → Environment → update `CORS_ORIGINS` to the
   frontend's real URL → the backend picks this up on its next restart.

## 5. Create QTech's organization

Nothing is seeded automatically — the app already has a self-serve flow for
exactly this. Visit the frontend's live URL and:

1. Click **Create a new organization**.
2. Name it "QTech Software", pick a ticket key prefix (e.g. `QTR`), and create
   your own account — you become its admin.
3. In **Settings**, copy the join code and share it with whoever else at
   QTech should have access. They sign up via **Join an existing
   organization**, search "QTech Software", and enter that code.

(`backend/seed.py` and `backend/backfill_demo.py` are dev-only tools that
generate fake demo tickets — don't run them against production.)

## 6. Verify

- Log in and confirm the board loads.
- Upload an attachment to a ticket and reopen it — this round-trips through
  Backblaze, so it confirms the storage setup end-to-end.
- Upload an avatar — same check, different bucket path.
- Check `https://<your-backend>.onrender.com/health` returns `{"status":"ok"}`.

## Adding a custom domain later

Render → the frontend service → **Settings → Custom Domains** → add your
domain and follow the DNS instructions shown there (a CNAME record, usually).
Once it's live, update the backend's `CORS_ORIGINS` to include the new
domain (comma-separated if you're keeping the onrender.com one too), and
update the frontend's `VITE_API_URL` if you also move the backend to a custom
domain and redeploy the frontend.

## Everyday deploys after this

Once the Blueprint is applied, Render auto-deploys on every push to your
default branch — `git push` is the whole deploy process from here on.
Migrations run automatically via `preDeployCommand` before each deploy.
