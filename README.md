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

Open **http://localhost:5173**. Vite proxies same-origin `/api` calls. The embedded worker is for local single-process use only. For a single-port compiled preview, set `PUBLIC_URL=http://localhost:8000`, build the UI and run just the API and renderer. `scripts/start-local.ps1` starts a compiled preview at `http://localhost:6001` in hidden background processes on Windows; `scripts/stop-local.ps1` stops only those processes.

The Windows launcher defaults to port 6001 (`scripts/start-local.ps1 -Port 6001`); use `-Port` to select another port. It sets `PUBLIC_URL` to match. Port 6000 is restricted by browsers; use the default port 6001 for normal browser access.

On macOS/Linux use `.venv/bin/python`, `npm`, and `export PYTHONPATH=backend`. Chrome may be selected using `CHROMIUM_PATH`; otherwise install the renderer's Playwright Chromium version.

## Acceptance walkthrough

The home page includes six sample prompts. Open **Prompts** in the left menu to browse 18 templates across Architecture & design, Cloud & modernization, AI & knowledge, Data & integrations, Security & resilience, and Delivery & estimates. Search or filter by category, expand the full text, copy a prompt, or choose **Use this prompt** to fill a new solution with matching output selections. Replace bracketed details and review before submitting. Browsing the library and returning to Workspace preserves your current draft/project; choosing a template from a saved project starts a new solution.

1. Sign into the demo workspace. Select an example or describe a requirement.
2. Attach a UTF-8 Markdown/TXT, PDF or DOCX reference. Set cloud, constraints and desired outputs under Advanced Options. Every output package automatically includes a PowerPoint project briefing.
3. Submit and watch **Queued → Building Context → Generating Solution → Creating Files → Completed**. Reopen the project from Recent projects if you navigate away.
4. Review the narrative, reference IDs, assumptions and unresolved questions. Approve an assumption to include it in subsequent context.
5. Open Diagrams for a server-rendered PNG. Download SVG/PNG/JPG/Mermaid source. Edit the source and save a new version.
6. Edit effort/rates, currency, contingency and FTE under Estimates. Save to calculate totals on the backend and generate a new immutable revision. Missing rates yield **Rates required**, not an invented price.
7. Download DOCX, PDF, XLSX, the included PPTX briefing and the ZIP package from Files. The 16:9 briefing covers the executive summary, proposed solution, architecture, editable estimate tables/chart, calculated costs when rates are supplied, delivery roadmap, assumptions and decisions. Unrequested or missing estimates/diagrams are explicitly identified. Links appear only for completed files. A failed export has its own retry action; successful files remain available. For an existing response, choose **Refresh deliverables** in Files to create updated exports as a new version without another LLM response. Earlier versions remain unchanged.
8. Ask a follow-up. Switch versions to reopen previous outputs. The saved context includes prior prompts/summaries, approved decisions and relevant reference passages.

Demo accounts are generated per browser session. Clearing cookies loses access to that demo account. Use OIDC for durable enterprise identity.

## Backend execution details

The workflow panel includes a backend execution inspector. Click any workflow card to inspect its recorded component/class, implementation handler, stage start/end times and elapsed duration. The selected view shows model request starts/finishes, provider-reported token counts and stop reasons, validation retries, reference-selection counts, diagram checks and per-file export activity. **Follow current agent** resumes automatic selection; **All workflow activity** includes the other steps. The inspector refreshes while work is active and remains available after completion, failure or cancellation.

Standard solutions use context/document worker components and a solution-generation LLM step; RFP workflows expose the actual specialist agent classes. Human approval and publication actions remain in the proposal's existing agent activity log. Operational events exclude prompts, document contents, model response bodies, credentials and hidden reasoning. Old jobs without recordings are clearly labelled; history and timings are not fabricated.

Production upgrades must apply migration `0004` before starting workers. `GET /api/jobs/{id}/execution` enforces project ownership and returns up to 300 recent events plus recorded stage timings.

## Reset a running workflow

Click **Reset** in the running workflow box to stop the current job and return to a blank **New solution** page. The project, references, previous versions and completed files remain available in My projects. The cancellation endpoint checks project ownership, is safe to repeat, and leaves already finished jobs unchanged. Cancelled jobs are terminal; unfinished files are marked Cancelled and can be explicitly retried. A cancelled RFP can also be retried from its project.

Workers supervise each job in a separate process, checking persisted cancellation while the model or exporter is running. Reset terminates that local process tree and frees the worker for subsequent requests. An already accepted provider request may continue remotely and may still be billed; cancellation prevents its late result from advancing the local workflow. No job is automatically reissued.

API: `POST /api/jobs/{id}/cancel`.

## Multi-agent presales (RFP responses)

Choose **New RFP response** in the left menu. Paste the RFP text or summary, pick the output formats (Word, PowerPoint or both), optionally attach RFP documents, and submit. Every request goes to the **Orchestrator agent**, which classifies the request and assigns work to the specialist agents:

| Agent | Responsibility |
|---|---|
| Orchestrator | Accepts all UI requests (new RFP, answers, change requests, approval, retry, free-text messages), routes them by proposal state and coordinates execution. It never infers approval from free text. |
| RequirementsCollector | Extracts must/shall requirements and validates scope, timeline, budget, technical environment, integrations, security/compliance and more. If information is missing, the proposal waits in **Awaiting Information** and the UI asks the user. |
| ProposalCreator | Plans the response format, sections and win themes, generates the solution and coordinates the Estimations, Resources and Documents agents. |
| Estimations | Effort by activity with contingency that grows with open assumptions. |
| Resources | Proposed team: roles, headcount and allocation. |
| DeliveryMethodology | Delivery approach (Agile/hybrid/SAFe), phases and governance. |
| Documents | Builds the Word document and/or PowerPoint deck with technical diagrams, estimates, team and methodology. |

Flow: **Collecting Requirements → (Awaiting Information) → Drafting → Pending Review → Live**. In **Pending Review** a reviewer (human in the loop) reads the draft files, then either requests changes (another drafting round that uses the comments) or chooses **Approve & publish**. Approval copies the draft files into immutable **Response Documents**, shown under the proposal with signed download links. The agent activity log shows every message exchanged between agents. With a live provider each agent uses the LLM with schema-validated output. Provider failures stop the workflow with an actionable error; deterministic logic is used only in explicit demo mode.

API: `POST /api/projects/{id}/orchestrator` (free-text entry point), `POST /api/projects/{id}/proposals`, `POST /api/proposals/{id}/answers`, `POST /api/proposals/{id}/review`, `POST /api/proposals/{id}/retry`, `POST /api/response-documents/{id}/download-link`.

## Reusable proposal templates

Open **Templates** in the left menu to upload private Word (`.docx`, `.dotx`) and PowerPoint (`.pptx`, `.potx`) templates, up to the configured upload limit per file. The library supports downloads and removal with confirmation. Legacy `.doc`/`.ppt`, encrypted files, macros and embedded objects are not supported.

Choose a Word and/or PowerPoint template under **New RFP response > Proposal templates**, or in a solution's **Advanced options**. Leaving a selector on **Workspace default** keeps the standard export. Template choices are saved with proposal versions and apply to DOCX/PPTX exports, including revisions and refreshed deliverables; PDF exports retain the standard layout.

Uploads are converted into content-free formats **before storage**; original uploads are not retained. Word keeps named styles, detected body fonts, paragraph spacing and page settings. Body content, tables, images, header/footer text, comments, metadata and unrelated package parts are removed. No insertion markers or title/summary tokens are needed. PowerPoint keeps its canvas, theme, detected body font, colors, decorative geometry and reusable master/layout formatting. Sample slides, all text, pictures, charts, notes, comments and metadata are removed. Generated proposals supply fresh content using the saved format. Downloads return the cleaned format, normalized to `.docx` or `.pptx`.

For a library created before this behavior, run `PYTHONPATH=backend python scripts/clean-template-library.py` (PowerShell: set `$env:PYTHONPATH='backend'` first). It cleans active and archived template sources in place without modifying generated proposal artifacts.

Removing a template hides it from new selections. Its cleaned format is retained privately for existing proposal versions and file retries. Templates belong to the signed-in user; demo accounts remain tied to their browser session. Production upgrades must run the `0003` migration before starting the API/worker.

API: `GET/POST /api/templates`, `GET /api/templates/{id}/file`, `DELETE /api/templates/{id}`.

## Configure a live provider

Copy the relevant values into `.env`. Secrets remain backend-only; never use `VITE_` variables for credentials. Restart API and worker after changes.

| Provider | Required configuration |
|---|---|
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `LLM_MODEL` with a model supporting Chat Completions JSON mode and `max_completion_tokens` |
| Azure OpenAI | `LLM_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT=https://…`, `AZURE_OPENAI_API_KEY`, `LLM_MODEL=<deployment-name>`, compatible `AZURE_OPENAI_API_VERSION` |
| Amazon Bedrock | `LLM_PROVIDER=bedrock`, `LLM_MODEL=<model-or-inference-profile-ID>`, `AWS_REGION`, AWS credential chain with Converse/model invocation permission |

The adapter uses schema-shaped tool output for Anthropic Claude models on Bedrock and JSON mode for the other adapters, then validates every response against the Pydantic schema. Output-token truncation is detected explicitly and retried once with a shorter response instruction; schema failures receive bounded field-level feedback. Raw model responses are not logged. It rejects unknown citation IDs. There are at most two provider attempts per call with fixed timeouts; live diagram validation may request one bounded repair. Invalid responses fail with actionable errors; no live-provider failure silently falls back to demo. Choose token limits compatible with your model. The input budget uses UTF-8 bytes as a conservative token upper bound, accounting for the complete serialized schema, system instructions, provenance, JSON escaping and retry overhead before selecting reference passages. Lexical passage retrieval and up to four prior version summaries keep context bounded; excluded passages are explicitly identified as unreviewed.

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

Development auto-creates missing tables but does not alter existing ones. To upgrade a local SQLite database created before migration `0002` (presales agents) without an `alembic_version` table, back it up and run `alembic -c backend/alembic.ini stamp 0001` then `upgrade head` with `PYTHONPATH=backend`. Production does not auto-create tables. Alembic owns a frozen initial schema and supports downgrade. SQL JSON columns store structured solutions and extracted passages. SQL-backed queue claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED`; no extra broker is necessary for this MVP. Use one worker with SQLite. Jobs abandoned beyond a 20-minute lease become Failed, with interrupted files marked retryable; completed outputs are retained. A provider call may be billed before a crash, so jobs are not silently reissued.

Use `STORAGE_BACKEND=s3`, `S3_BUCKET`, optional `S3_ENDPOINT` for S3-compatible storage. Production S3 writes request AES256 server-side encryption by default. Local MinIO disables that request because no KMS is configured. Object keys are server-generated; file names cannot select filesystem paths. Configure private buckets, encryption, lifecycle, backups and transport in the deployment environment.

Schedule `python -m app.retention` daily. It deletes inactive projects older than `RETENTION_DAYS`, their objects, and expired audit metadata, while skipping active jobs. Audit events record IDs/actions only, without prompt, document or credential bodies. Worker and API must share database, storage, secrets and provider settings.

Optional OCR: install `pypdfium2`, `pytesseract` and the Tesseract OS binary; set `OCR_ENABLED=true`. OCR handles image-only PDFs, at most 30 pages within the parser deadline. Mixed PDFs report missing-text pages rather than pretending they were read. OCR accuracy requires human review. Extraction runs in a child process with a 45-second deadline and CPU/address-space limits on Linux. Windows uses the deadline but has no POSIX resource limits. DOCX expanded archive size and PDF page count are bounded.

For architecture, operational limits and AWS deployment guidance see [docs/architecture.md](docs/architecture.md) and [docs/deployment-aws.md](docs/deployment-aws.md). This is a functional MVP with production safeguards; enterprise rollout still requires configured identity/provider validation, infrastructure deployment, threat review, restore/load tests and operational ownership.
