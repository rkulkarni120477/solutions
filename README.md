# Solution Architect Workspace

A full-stack MVP for **Prompt → Context → LLM → Results → Downloadable Deliverables**. React/TypeScript/Tailwind, FastAPI, durable SQL-backed jobs, versioned projects, private object storage and a separately isolated Mermaid renderer.

The default is an **explicitly labeled deterministic demo**. It creates real files but does not claim to provide a tailored live-model solution. Live OIDC, OpenAI, Azure OpenAI and Bedrock adapters require your credentials and account access.

## Quick start: Docker Compose

Requires Docker Desktop with Linux containers and Compose v2.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Open **http://localhost:8000**. Click **Sign in** or **Sign in & submit**. Compose starts PostgreSQL, MinIO, a bucket initializer, a migration task, the API with compiled UI, a worker, and the private renderer. Database and object data survive container restarts.

```powershell
docker compose logs -f worker
docker compose down
```

Do not use `down -v` unless you intend to erase local data. Compose is a local development configuration: its database credentials, HTTP object transport and unsandboxed Chromium container flag are not production settings.

## Local development without Docker

Requires Python 3.11+, Node 22.12+ (Node 24 also works), and Chromium. PowerShell commands below run from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
npm.cmd --prefix frontend ci
npm.cmd --prefix renderer ci
npm.cmd --prefix renderer run build
npm.cmd --prefix renderer exec -- playwright install chromium
npm.cmd --prefix frontend run build
```

Three terminals for hot-reload development:

```powershell
# Terminal 1, root. SQLite and local files are written under .data/.
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal 2, root. Optional: set CHROMIUM_PATH to installed Chrome/Chromium.
cd renderer
npm.cmd start

# Terminal 3, root. PUBLIC_URL in .env should remain http://localhost:5173.
cd frontend
npm.cmd run dev
```

Open **http://localhost:5173**. Vite proxies same-origin `/api` calls. The embedded worker is for local single-process use only. For a single-port compiled preview, set `PUBLIC_URL=http://localhost:8000`, build the UI and run just the API and renderer. `scripts/start-local.ps1` starts this compiled preview in hidden background processes on Windows; `scripts/stop-local.ps1` stops only those processes.

On macOS/Linux use `.venv/bin/python`, `npm`, and `export PYTHONPATH=backend`. Chrome may be selected using `CHROMIUM_PATH`; otherwise install the renderer's Playwright Chromium version.

## Acceptance walkthrough

1. Sign into the demo workspace. Select an example or describe a requirement.
2. Attach a UTF-8 Markdown/TXT, PDF or DOCX reference. Set cloud, constraints and desired outputs under Advanced Options. To exercise all formats, enable Presentation too.
3. Submit and watch **Queued → Building Context → Generating Solution → Creating Files → Completed**. Reopen the project from Recent projects if you navigate away.
4. Review the narrative, reference IDs, assumptions and unresolved questions. Approve an assumption to include it in subsequent context.
5. Open Diagrams for a server-rendered PNG. Download SVG/PNG/JPG/Mermaid source. Edit the source and save a new version.
6. Edit effort/rates, currency, contingency and FTE under Estimates. Save to calculate totals on the backend and generate a new immutable revision. Missing rates yield **Rates required**, not an invented price.
7. Download DOCX, PDF, XLSX, optional PPTX and the ZIP package from Files. Links appear only for completed files. A failed export has its own retry action; successful files remain available.
8. Ask a follow-up. Switch versions to reopen previous outputs. The saved context includes prior prompts/summaries, approved decisions and relevant reference passages.

Demo accounts are generated per browser session. Clearing cookies loses access to that demo account. Use OIDC for durable enterprise identity.

## Configure a live provider

Copy the relevant values into `.env`. Secrets remain backend-only; never use `VITE_` variables for credentials. Restart API and worker after changes.

| Provider | Required configuration |
|---|---|
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `LLM_MODEL` with a model supporting Chat Completions JSON mode and `max_completion_tokens` |
| Azure OpenAI | `LLM_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT=https://…`, `AZURE_OPENAI_API_KEY`, `LLM_MODEL=<deployment-name>`, compatible `AZURE_OPENAI_API_VERSION` |
| Amazon Bedrock | `LLM_PROVIDER=bedrock`, `LLM_MODEL=<model-or-inference-profile-ID>`, `AWS_REGION`, AWS credential chain with Converse/model invocation permission |

The adapter requests JSON and validates every response against the Pydantic schema. It rejects unknown citation IDs. There are at most two provider attempts per call with fixed timeouts; live diagram validation may request one bounded repair. Invalid responses fail with actionable errors; no live-provider failure silently falls back to demo. Choose token limits compatible with your model. The input budget uses UTF-8 bytes as a conservative token upper bound, with reserved schema/system overhead; lexical passage retrieval and four prior version summaries keep context bounded.

API references: [OpenAI JSON output](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat), [Bedrock Converse](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html), [Authlib Starlette OIDC](https://docs.authlib.org/en/v1.5.2/client/starlette.html).

## Enterprise authentication

Set `AUTH_MODE=oidc`, client ID/secret and a tenant-specific `OIDC_METADATA_URL`. For Entra ID, use the tenant's OpenID discovery endpoint and register a **Web** redirect URI at `<PUBLIC_URL>/api/auth/callback`. Authlib handles state, PKCE, nonce, ID-token signature, issuer and audience validation. The app stores only its user ID in a signed HttpOnly SameSite session cookie. ID/access tokens are not persisted to the browser session. Set `SECURE_COOKIES=true` and HTTPS in production. Logout clears the app session; it does not log the user out of the enterprise identity provider.

All project, attachment, conversation/version, job visibility and artifact operations enforce ownership. Downloads require both an expiring signed token and the matching authenticated user. Same-origin mutation checks and a custom request header protect browser requests. There is no public file bucket or anonymous download endpoint.

## Tests and builds

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run build
npm.cmd --prefix renderer run build
```

The focused suite covers authorization and CSRF checks, provenance and context budgets, isolated extraction, decimal estimate totals, real document parsing, formula-injection defenses, durable jobs, versions, package manifests, signed downloads, partial failures and retry, provider errors, and unsafe Mermaid rejection. Unit tests substitute the renderer; `scripts/smoke.py` tests the actual running API and renderer, generates every file format, checks signatures, tests a follow-up and cleans up its project.

```powershell
.\.venv\Scripts\python.exe scripts/smoke.py
```

## Storage, migrations and operations

Production uses PostgreSQL via `DATABASE_URL=postgresql+psycopg://…`. Migrate once before releasing API/worker:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

Development auto-creates tables; production does not. Alembic owns a frozen initial schema and supports downgrade. SQL JSON columns store structured solutions and extracted passages. SQL-backed queue claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED`; no extra broker is necessary for this MVP. Use one worker with SQLite. Jobs abandoned beyond a 20-minute lease become Failed, with interrupted files marked retryable; completed outputs are retained. A provider call may be billed before a crash, so jobs are not silently reissued.

Use `STORAGE_BACKEND=s3`, `S3_BUCKET`, optional `S3_ENDPOINT` for S3-compatible storage. Production S3 writes request AES256 server-side encryption by default. Local MinIO disables that request because no KMS is configured. Object keys are server-generated; file names cannot select filesystem paths. Configure private buckets, encryption, lifecycle, backups and transport in the deployment environment.

Schedule `python -m app.retention` daily. It deletes inactive projects older than `RETENTION_DAYS`, their objects, and expired audit metadata, while skipping active jobs. Audit events record IDs/actions only, without prompt, document or credential bodies. Worker and API must share database, storage, secrets and provider settings.

Optional OCR: install `pypdfium2`, `pytesseract` and the Tesseract OS binary; set `OCR_ENABLED=true`. OCR handles image-only PDFs, at most 30 pages within the parser deadline. Mixed PDFs report missing-text pages rather than pretending they were read. OCR accuracy requires human review. Extraction runs in a child process with a 45-second deadline and CPU/address-space limits on Linux. Windows uses the deadline but has no POSIX resource limits. DOCX expanded archive size and PDF page count are bounded.

For architecture, operational limits and AWS deployment guidance see [docs/architecture.md](docs/architecture.md) and [docs/deployment-aws.md](docs/deployment-aws.md). This is a functional MVP with production safeguards; enterprise rollout still requires configured identity/provider validation, infrastructure deployment, threat review, restore/load tests and operational ownership.
