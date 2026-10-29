# AWS reference deployment

This is deployment guidance, not deployed infrastructure or a cost quote. Use your organization's infrastructure repository and controls to provision the following topology. No cloud resources are created by this repository.

## Reference services

| Concern | Reference configuration |
|---|---|
| Web/API | ECS Fargate service using the root Dockerfile, behind an HTTPS Application Load Balancer and AWS WAF |
| Jobs | Separate ECS worker service using the same image, command `python -m app.worker`, `EMBEDDED_WORKER=false` |
| Relational state and queue | Private multi-AZ RDS PostgreSQL, encrypted storage, TLS-required connections, PITR and restore drills |
| Files | Private S3 bucket, blocked public access, encryption, least-privilege task roles and lifecycle aligned to retention |
| Diagrams | Private renderer task/service, network egress blocked, restricted filesystem and CPU/memory, Chromium sandbox enabled |
| Enterprise identity | Tenant-specific Entra/OIDC provider with exact HTTPS callback URI |
| Model access | Bedrock using task roles, or OpenAI/Azure credentials injected from Secrets Manager |
| Secrets | Secrets Manager injected at runtime; never bake credentials or `.env` into an image |
| Telemetry | CloudWatch metrics/logs with content-free audit events, alerts for failed jobs and old queue entries |
| Cleanup | EventBridge Scheduler daily ECS task running `python -m app.retention` |

## Release sequence

1. Build and scan both images in CI. Use committed npm lockfiles and pinned Python dependencies, run the focused tests, typecheck/build the UI and renderer, then push immutable image digests to ECR.
2. Provision private subnets, RDS, S3, task roles, secrets, renderer and HTTPS ingress. Use ACM and your DNS zone. API security group accepts ALB traffic only; DB accepts API/worker traffic only; renderer accepts worker traffic only.
3. Set `ENVIRONMENT=production`, `AUTH_MODE=oidc`, `LLM_PROVIDER=<live-provider>`, `LLM_MODEL`, `DATABASE_URL=postgresql+psycopg://…?sslmode=require`, `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_SSE=AES256`, `PUBLIC_URL=https://…`, `SECURE_COOKIES=true`, `EMBEDDED_WORKER=false`. Unset `S3_ENDPOINT` for native S3. Inject unique high-entropy `SESSION_SECRET` and `RENDERER_SECRET` (32+ bytes each). API and worker settings must match.
4. Register `<PUBLIC_URL>/api/auth/callback` with the identity provider. Populate the tenant's discovery URL and OIDC client credentials. Validate the actual issuer and tenant boundary before accepting customer content.
5. Run a one-off task `alembic -c backend/alembic.ini upgrade head`. Start API/worker only after success. Never use development table auto-creation in production.
6. Deploy the API with `/api/health` as its liveness probe. That endpoint is intentionally content-free and is not a dependency readiness check: add authenticated synthetic transactions for DB/storage/provider/renderer availability.
7. Enable model access and least-privilege invocation permissions. Validate a representative structured response with your chosen model, region and quotas; supported JSON behavior and token limits vary by deployment. No model or pricing is assumed to be available.
8. Run staging acceptance with actual OIDC, PostgreSQL and S3, then file-format/diagram verification, authorization probes, load/queue-concurrency tests and a backup restore. Promote immutable images only after those checks pass.

## Renderer hardening

The renderer's local Compose `RENDERER_NO_SANDBOX=true` flag is convenience for local Linux container compatibility. Production must run nonroot Chromium with a tested seccomp/user-namespace sandbox configuration (for example on a hardened ECS EC2 host or equivalent dedicated sandbox service), `RENDERER_NO_SANDBOX=false`, no outbound network except essential process controls, read-only root filesystem and a bounded writable `/tmp`. Do not blindly copy the local container policy into Fargate if Chromium sandbox prerequisites are unavailable. For that case deploy the renderer on an appropriately isolated runtime and keep API/worker on Fargate.

The browser also denies all page network requests, rejects external URL/directive syntax, limits input and image dimensions, and creates a fresh browser for each render. These application controls supplement infrastructure isolation.

## Operational decisions to validate

Set SLOs, RTO/RPO, backup retention, residency and incident ownership with stakeholders. Configure KMS keys if policy requires customer-managed encryption; adapt `storage.py` to supply `SSEKMSKeyId` where required. Require encrypted transport with S3/RDS policies. The application cannot enforce at-rest encryption of unmanaged local disks. Use WAF/ALB protections for overall request rate and upload body limits; the app independently limits generation jobs per user and upload sizes.

Rotate session secrets with a deliberate sign-out policy, renderer secrets across both services, and provider credentials. Restrict operator access to extracted reference text and stored solution JSON as confidential data. Review generated pricing/architecture assumptions with a human. Never log credential-bearing environment dumps, full provider errors, customer documents or prompts.

Costs are intentionally unquoted. Estimate them with current regional AWS/provider calculators after user counts, token volume, retention, availability and staffing are known. Keep recurring infrastructure/model consumption separate from implementation effort and labor rates.
