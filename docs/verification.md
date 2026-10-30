# Local verification — October 29, 2026

## Presentation export update

The response package now always includes a structured PowerPoint briefing. The expanded suite passes **18 backend tests**, including automatic PPTX inclusion when the flag is omitted, native estimate tables/chart values, calculated costs, missing-data disclosures, pagination, shape bounds, ownership checks, and export refresh without a provider call. The frontend production build passes with the included-presentation notice and Refresh deliverables action.

A representative deck with a real rendered architecture was opened read-only and exported by installed Microsoft PowerPoint. All **25 slides** were visually inspected after consolidating sparse continuation layouts. PowerPoint detected **zero text-box overflows**, and OOXML/relationship/chart validation passed. These checks validate the generator against the sample and focused edge cases; arbitrary customer content can still require visual review. Use `scripts/render-presentation.ps1` for local Windows/PowerPoint rendering.

Existing responses can use **Files → Refresh deliverables** to generate new files in a new version without another LLM response. Their earlier artifacts are preserved.

## Passed

- **14 backend tests**: authentication/ownership, cross-origin protection, context retrieval/budgets/provenance, isolated document extraction, scanned-PDF warnings, decimal estimate totals, real document parsing, spreadsheet formula protection, durable queue processing, immutable versions, signed downloads, partial failures and artifact retries, provider failures and unsafe Mermaid rejection.
- **Actual service smoke test**: demo sign-in, saved project, attached Markdown reference, context-aware labeled demo response, real Mermaid rendering, all artifact downloads and a second follow-up version. Verified DOCX (90,801 bytes), PDF (67,192), XLSX (7,100), PPTX (94,352), editable Mermaid source (429), SVG (28,769), PNG (53,581), JPG (66,530), and ZIP (342,268). The ZIP includes a manifest. The smoke project was deleted after completion. File sizes can vary with metadata and dependency versions.
- **Migration round trip**: upgrade → downgrade → upgrade on an isolated database, followed by Alembic model-parity check.
- **Production builds**: TypeScript + Vite frontend and bundled Mermaid renderer.
- **Dependency audits**: npm audits for both packages and pip-audit for the Python environment reported no known vulnerabilities after updates.
- **Compose YAML**: parsed and checked for expected services.

## Environment limits

Docker Desktop's daemon was unavailable, so container image builds, PostgreSQL/MinIO integration and Compose startup were not run. Local acceptance used SQLite and filesystem storage. Browser-control hosting was unavailable, so interactive visual/responsive/accessibility browser QA was not performed. The renderer itself did run actual installed Chrome in headless mode to produce diagrams; that does not substitute for frontend visual QA.

No live provider credentials or enterprise OIDC configuration were supplied. Live OpenAI, Azure OpenAI, Bedrock and federated sign-in need staging validation. AWS deployment, infrastructure encryption/policies, restore/load tests and production operational controls were not executed.

Two compatibility deprecation warnings remain in current Authlib/Starlette dependencies regarding their eventual migration from httpx to httpx2. Tests pass; this does not affect the current API adapter contract. Revisit when those libraries remove compatibility support.

## Reproduce

See [README](../README.md) for setup. Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe scripts/verify-migrations.py
npm.cmd --prefix frontend run build
npm.cmd --prefix renderer run build
# With API and renderer running:
.\.venv\Scripts\python.exe scripts/smoke.py
```
