import secrets
import threading
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Depends, Request, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .db import Base, engine, Session, get_db, User, Project, Version, Attachment, Job, Artifact, Audit, Proposal, AgentMessage, ResponseDocument, now, uid
from .schemas import Generate, Solution, EstimateUpdate, ProposalCreate, ProposalAnswers, ProposalReview, calculate
from .context import extract_isolated
from .storage import storage
from .artifacts import MIMES
from .worker import run_forever, ACTIVE

oauth = OAuth()
if settings.auth_mode == 'oidc':
    oauth.register(name='enterprise', client_id=settings.oidc_client_id, client_secret=settings.oidc_client_secret,
                   server_metadata_url=settings.oidc_metadata_url, client_kwargs={'scope': 'openid profile email', 'code_challenge_method': 'S256'})


@asynccontextmanager
async def lifespan(app):
    settings.validate_runtime()
    if settings.environment != 'production':
        Base.metadata.create_all(engine)  # Production exclusively uses Alembic.
    stop = threading.Event()
    thread = None
    if settings.embedded_worker:
        thread = threading.Thread(target=run_forever, args=(stop,), daemon=True)
        thread.start()
    yield
    stop.set()
    if thread:
        thread.join(timeout=2)


app = FastAPI(title='Solution Architect Workspace', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie='workspace_session', same_site='lax', https_only=settings.secure_cookies, max_age=28800)


@app.middleware('http')
async def security(request, call_next):
    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != settings.public_url.rstrip('/'):
            return Response('Cross-origin request rejected', status_code=403)
        if request.headers.get('x-workspace-request') != '1':
            return Response('Missing request protection header', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    if settings.secure_cookies:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def current_user(request: Request, db: DBSession = Depends(get_db)):
    user = db.get(User, request.session.get('user_id', ''))
    if not user:
        raise HTTPException(401, 'Sign in to access your workspace.')
    return user


def owned(db, user, project_id):
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(404, 'Project not found.')
    return project


def audit(db, user, action, resource):
    db.add(Audit(user_id=user.id, action=action, resource_id=resource))


def no_active_job(db, project_id):
    if db.scalar(select(Job.id).where(Job.project_id == project_id, Job.status.in_(['Queued', *ACTIVE])).limit(1)):
        raise HTTPException(409, 'This project is processing. Wait for completion before creating another revision.')


def limit_jobs(db, user):
    count = db.scalar(select(func.count()).select_from(Job).join(Project, Job.project_id == Project.id).where(Project.owner_id == user.id, Job.created_at > now()-timedelta(hours=1)))
    if count >= settings.jobs_per_hour:
        raise HTTPException(429, 'Hourly generation limit reached. Try again later.')


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/config')
def config():
    return {'auth_mode': settings.auth_mode, 'provider': settings.llm_provider, 'demo': settings.llm_provider == 'demo', 'retention_days': settings.retention_days, 'upload_max_mb': settings.upload_max_mb}


@app.post('/api/auth/demo')
def demo_login(request: Request, db: DBSession = Depends(get_db)):
    if settings.auth_mode != 'demo':
        raise HTTPException(404)
    existing = db.get(User, request.session.get('user_id', ''))
    if not existing:
        existing = User(subject='demo:' + uid(), name='Demo architect')
        db.add(existing)
        db.commit()
    request.session.clear()
    request.session['user_id'] = existing.id
    return {'name': existing.name}


@app.get('/api/auth/login')
async def login(request: Request):
    if settings.auth_mode != 'oidc':
        raise HTTPException(400, 'Use demo sign-in in this environment.')
    return await oauth.enterprise.authorize_redirect(request, settings.public_url + '/api/auth/callback')


@app.get('/api/auth/callback')
async def callback(request: Request, db: DBSession = Depends(get_db)):
    if settings.auth_mode != 'oidc':
        raise HTTPException(404)
    try:
        token = await oauth.enterprise.authorize_access_token(request)
        claims = token['userinfo']  # Authlib validates ID-token signature, issuer, audience and nonce.
        subject = claims['iss'] + '|' + claims['sub']
    except Exception:
        raise HTTPException(401, 'Enterprise sign-in failed. Check tenant, redirect URI and OIDC configuration.') from None
    user = db.scalar(select(User).where(User.subject == subject))
    if not user:
        user = User(subject=subject, name=claims.get('name', 'Architect')[:200])
        db.add(user)
        db.commit()
    request.session.clear()
    request.session['user_id'] = user.id
    audit(db, user, 'sign_in', user.id)
    db.commit()
    return RedirectResponse(settings.public_url)


@app.post('/api/auth/logout')
def logout(request: Request):
    request.session.clear()
    return {'ok': True}


@app.get('/api/me')
def me(user=Depends(current_user)):
    return {'id': user.id, 'name': user.name}


@app.get('/api/projects')
def projects(user=Depends(current_user), db: DBSession = Depends(get_db)):
    return db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc()).limit(100)).all()


class NewProject(BaseModel):
    title: str = Field(min_length=1, max_length=160)


@app.post('/api/projects', status_code=201)
def create_project(body: NewProject, user=Depends(current_user), db: DBSession = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == user.id)) >= 100:
        raise HTTPException(409, 'Project limit reached. Delete an unused project before creating another.')
    project = Project(owner_id=user.id, title=body.title)
    db.add(project)
    db.flush()
    audit(db, user, 'project_created', project.id)
    db.commit()
    return project


def version_view(db, v):
    return {'id': v.id, 'number': v.number, 'prompt': v.prompt, 'preferences': v.preferences,
            'response': v.response, 'totals': calculate(Solution.model_validate(v.response)) if v.response else None,
            'context_sources': v.context_sources, 'provider': v.provider, 'created_at': v.created_at,
            'artifacts': db.scalars(select(Artifact).where(Artifact.version_id == v.id)).all()}


@app.get('/api/projects/{project_id}')
def project_detail(project_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    versions = db.scalars(select(Version).where(Version.project_id == project_id).order_by(Version.number)).all()
    return {'project': project, 'versions': [version_view(db, v) for v in versions],
            'attachments': [{'id': a.id, 'filename': a.filename, 'size': a.size, 'warning': a.warning, 'passage_count':len(a.passages)} for a in db.scalars(select(Attachment).where(Attachment.project_id == project_id))],
            'jobs': db.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.created_at)).all(),
            'proposals': [proposal_view(db, p) for p in db.scalars(select(Proposal).where(Proposal.project_id == project_id).order_by(Proposal.created_at))],
            'response_documents': db.scalars(select(ResponseDocument).where(ResponseDocument.project_id == project_id).order_by(ResponseDocument.created_at)).all()}


def proposal_view(db, p):
    return {'id': p.id, 'status': p.status, 'request': p.request, 'formats': p.formats, 'preferences': p.preferences, 'requirements': p.requirements,
            'answers': p.answers, 'assumptions_accepted': p.assumptions_accepted, 'plan': p.plan, 'draft_version_id': p.draft_version_id,
            'reviews': p.reviews, 'error': p.error, 'approved_at': p.approved_at, 'published_at': p.published_at, 'created_at': p.created_at, 'updated_at': p.updated_at,
            'messages': db.scalars(select(AgentMessage).where(AgentMessage.proposal_id == p.id).order_by(AgentMessage.created_at)).all()}


@app.post('/api/projects/{project_id}/attachments', status_code=201)
def upload(project_id: str, file: UploadFile = File(...), user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    no_active_job(db, project_id)
    if db.scalar(select(func.count()).select_from(Attachment).where(Attachment.project_id == project_id)) >= 20:
        raise HTTPException(400, 'Maximum 20 reference documents per project.')
    filename = (file.filename or 'document').replace('\\', '/').rsplit('/',1)[-1]
    filename = ''.join(c for c in filename if c.isprintable())[:220]
    data = file.file.read(settings.upload_max_mb * 1024 * 1024 + 1)
    if not data or len(data) > settings.upload_max_mb * 1024 * 1024:
        raise HTTPException(400, f'Upload a non-empty document of at most {settings.upload_max_mb} MB.')
    try:
        passages, warning = extract_isolated(filename, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        raise HTTPException(400, 'Document extraction failed. Check the file is valid and unencrypted; use a text-based copy or configure optional OCR.') from None
    attachment = Attachment(project_id=project_id, filename=filename, key=f'{project_id}/references/{uid()}', size=len(data), passages=passages, warning=warning)
    try:
        storage.put(attachment.key, data)
    except Exception:
        raise HTTPException(503, 'Reference storage is unavailable. Check the storage configuration and retry the upload.') from None
    db.add(attachment)
    project.updated_at = now()
    db.flush()
    audit(db, user, 'attachment_uploaded', attachment.id)
    db.commit()
    return {'id':attachment.id, 'filename':filename, 'warning':warning,'passage_count':len(passages)}


@app.delete('/api/projects/{project_id}/attachments/{attachment_id}')
def delete_attachment(project_id: str, attachment_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    owned(db, user, project_id)
    no_active_job(db, project_id)
    attachment = db.get(Attachment, attachment_id)
    if not attachment or attachment.project_id != project_id:
        raise HTTPException(404)
    storage.delete(attachment.key)
    db.delete(attachment)
    audit(db, user, 'attachment_deleted', attachment_id)
    db.commit()
    return {'ok':True}


def new_version(db, project, prompt, preferences, response=None):
    # Lock project so version numbering and concurrent submissions remain consistent.
    db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    no_active_job(db, project.id)
    number = (db.scalar(select(func.max(Version.number)).where(Version.project_id == project.id)) or 0) + 1
    version = Version(project_id=project.id, number=number, prompt=prompt, preferences=preferences, provider=settings.llm_provider, response=response)
    db.add(version)
    db.flush()
    job = Job(project_id=project.id, version_id=version.id, kind='files' if response else 'solution')
    db.add(job)
    project.updated_at = now()
    db.commit()
    return job


@app.post('/api/projects/{project_id}/generate', status_code=202)
def submit(project_id: str, body: Generate, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    limit_jobs(db, user)
    job = new_version(db, project, body.prompt, body.preferences.model_dump())
    audit(db, user, 'generation_queued', job.id)
    db.commit()
    return job


@app.put('/api/projects/{project_id}/versions/{version_id}/estimates', status_code=202)
def update_estimates(project_id: str, version_id: str, body: EstimateUpdate, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    limit_jobs(db, user)
    version = db.get(Version, version_id)
    if not version or version.project_id != project_id or not version.response:
        raise HTTPException(404)
    solution = Solution.model_validate(version.response)
    solution = Solution.model_validate({**solution.model_dump(), **body.model_dump()})
    job = new_version(db, project, 'Estimate revision: ' + version.prompt[:15000], version.preferences, solution.model_dump())
    copied = db.get(Version, job.version_id)
    copied.provider = version.provider
    copied.context_sources = version.context_sources
    audit(db, user, 'estimate_revised', copied.id)
    db.commit()
    return job


@app.post('/api/projects/{project_id}/versions/{version_id}/refresh-files', status_code=202)
def refresh_files(project_id: str, version_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    limit_jobs(db, user)
    version = db.get(Version, version_id)
    if not version or version.project_id != project_id or not version.response:
        raise HTTPException(404, 'A completed solution response is required to refresh deliverables.')
    job = new_version(db, project, 'Deliverable refresh: ' + version.prompt[:15000],
                      version.preferences, Solution.model_validate(version.response).model_dump())
    refreshed = db.get(Version, job.version_id)
    refreshed.provider, refreshed.context_sources = version.provider, version.context_sources
    audit(db, user, 'deliverables_refreshed', refreshed.id)
    db.commit()
    return job


class DiagramUpdate(BaseModel):
    index: int = Field(ge=0, le=4)
    source: str = Field(min_length=5, max_length=20000)


@app.put('/api/projects/{project_id}/versions/{version_id}/diagram', status_code=202)
def update_diagram(project_id: str, version_id: str, body: DiagramUpdate, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    limit_jobs(db, user)
    version = db.get(Version, version_id)
    if not version or version.project_id != project_id or not version.response:
        raise HTTPException(404)
    solution = Solution.model_validate(version.response)
    if body.index >= len(solution.diagrams):
        raise HTTPException(400, 'Diagram index does not exist.')
    solution.diagrams[body.index].source = body.source
    job = new_version(db, project, 'Diagram revision: ' + version.prompt[:15000], version.preferences, solution.model_dump())
    copied = db.get(Version, job.version_id)
    copied.provider, copied.context_sources = version.provider, version.context_sources
    audit(db, user, 'diagram_revised', copied.id)
    db.commit()
    return job


class Decisions(BaseModel):
    decisions: list[str] = Field(max_length=30)


@app.put('/api/projects/{project_id}/decisions')
def decisions(project_id: str, body: Decisions, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    if any(len(d) > 1000 for d in body.decisions):
        raise HTTPException(400, 'Each decision must be at most 1000 characters.')
    project.decisions = body.decisions
    project.updated_at = now()
    audit(db, user, 'decisions_updated', project_id)
    db.commit()
    return {'ok':True}


@app.post('/api/artifacts/{artifact_id}/retry', status_code=202)
def retry(artifact_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(404)
    owned(db, user, artifact.project_id)
    no_active_job(db, artifact.project_id)
    limit_jobs(db, user)
    if artifact.status != 'Failed':
        raise HTTPException(409, 'Only failed artifacts can be retried.')
    artifact.status = 'Queued'
    job = Job(project_id=artifact.project_id, version_id=artifact.version_id, kind='artifact', artifact_id=artifact.id)
    db.add(job)
    audit(db, user, 'artifact_retry', artifact.id)
    db.commit()
    return job


signer = URLSafeTimedSerializer(settings.session_secret, salt='artifact-download')


@app.post('/api/artifacts/{artifact_id}/download-link')
def download_link(artifact_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    a = db.get(Artifact, artifact_id)
    if not a:
        raise HTTPException(404)
    owned(db, user, a.project_id)
    if a.status != 'Completed' or not a.key:
        raise HTTPException(409, 'This file is not ready. Retry failed generation from Files.')
    token = signer.dumps({'artifact':a.id, 'user':user.id})
    return {'url':f'/api/download/{token}', 'expires_in':settings.download_ttl}


@app.get('/api/download/{token}')
def download(token: str, inline: bool = False, user=Depends(current_user), db: DBSession = Depends(get_db)):
    try:
        claims = signer.loads(token, max_age=settings.download_ttl)
    except (BadSignature, SignatureExpired):
        raise HTTPException(403, 'Download link expired. Request a new link from Files.') from None
    if claims['user'] != user.id:
        raise HTTPException(404)
    a = db.get(Artifact, claims['artifact'])
    if not a:
        raise HTTPException(404)
    owned(db, user, a.project_id)
    if a.status != 'Completed' or not a.key:
        raise HTTPException(409, 'Artifact not available.')
    try:
        data = storage.get(a.key)
    except Exception:
        raise HTTPException(503, 'File storage is unavailable. Try again or check storage configuration.') from None
    ext = a.filename.rsplit('.',1)[-1]
    disposition = 'inline' if inline and ext in ['png', 'jpg'] else 'attachment'
    audit(db, user, 'artifact_downloaded', a.id)
    db.commit()
    return Response(data, media_type=MIMES.get(ext, 'application/octet-stream'), headers={'Content-Disposition':f'{disposition}; filename="{a.filename}"', 'Cache-Control':'private, no-store'})


OPEN_PROPOSAL = ['Queued', 'Collecting Requirements', 'Awaiting Information', 'Drafting', 'Pending Review']
PUBLISHED_KINDS = ['docx', 'pptx', 'pdf', 'xlsx', 'zip']


def owned_proposal(db, user, proposal_id):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(404, 'Proposal not found.')
    owned(db, user, proposal.project_id)
    return proposal


def queue_proposal(db, proposal, status='Queued'):
    no_active_job(db, proposal.project_id)
    proposal.status, proposal.error, proposal.updated_at = status, None, now()
    job = Job(project_id=proposal.project_id, proposal_id=proposal.id, kind='proposal')
    db.add(job)
    db.get(Project, proposal.project_id).updated_at = now()
    return job


@app.post('/api/projects/{project_id}/proposals', status_code=202)
def create_proposal(project_id: str, body: ProposalCreate, user=Depends(current_user), db: DBSession = Depends(get_db)):
    owned(db, user, project_id)
    limit_jobs(db, user)
    db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if db.scalar(select(Proposal.id).where(Proposal.project_id == project_id, Proposal.status.in_(OPEN_PROPOSAL)).limit(1)):
        raise HTTPException(409, 'This project already has an open proposal. Approve it or let it fail before starting another.')
    no_active_job(db, project_id)
    proposal = Proposal(project_id=project_id, request=body.request, formats=list(dict.fromkeys(body.formats)), preferences=body.preferences.model_dump())
    db.add(proposal)
    db.flush()
    db.add(AgentMessage(proposal_id=proposal.id, agent='User', recipient='RequirementsCollector', kind='task', content='New RFP response requested.'))
    job = queue_proposal(db, proposal)
    audit(db, user, 'proposal_created', proposal.id)
    db.commit()
    return {'proposal_id': proposal.id, 'job': job}


@app.post('/api/proposals/{proposal_id}/answers', status_code=202)
def answer_proposal(proposal_id: str, body: ProposalAnswers, user=Depends(current_user), db: DBSession = Depends(get_db)):
    proposal = owned_proposal(db, user, proposal_id)
    if proposal.status != 'Awaiting Information':
        raise HTTPException(409, 'This proposal is not waiting for information.')
    limit_jobs(db, user)
    proposal.answers = {**(proposal.answers or {}), **{k: v.strip() for k, v in body.answers.items() if v.strip()}}
    proposal.assumptions_accepted = proposal.assumptions_accepted or body.proceed_with_assumptions
    summary = f'Provided {len(body.answers)} answer(s)' + (' and asked the agents to proceed with assumptions.' if body.proceed_with_assumptions else '.')
    db.add(AgentMessage(proposal_id=proposal.id, agent='User', recipient='RequirementsCollector', kind='result', content=summary))
    job = queue_proposal(db, proposal)
    audit(db, user, 'proposal_answered', proposal.id)
    db.commit()
    return job


@app.post('/api/proposals/{proposal_id}/review')
def review_proposal(proposal_id: str, body: ProposalReview, user=Depends(current_user), db: DBSession = Depends(get_db)):
    proposal = owned_proposal(db, user, proposal_id)
    if proposal.status != 'Pending Review' or not proposal.draft_version_id:
        raise HTTPException(409, 'Only a proposal pending review can be approved or sent back.')
    no_active_job(db, proposal.project_id)
    entry = {'decision': body.decision, 'comments': body.comments.strip(), 'reviewer': user.name, 'version_id': proposal.draft_version_id, 'at': now().isoformat()}
    if body.decision == 'request_changes':
        limit_jobs(db, user)
        proposal.reviews = [*(proposal.reviews or []), entry]
        db.add(AgentMessage(proposal_id=proposal.id, agent='Reviewer', recipient='ProposalCreator', kind='question', content='Changes requested: ' + entry['comments']))
        job = queue_proposal(db, proposal)
        audit(db, user, 'proposal_changes_requested', proposal.id)
        db.commit()
        return {'status': proposal.status, 'job': job}
    artifacts = db.scalars(select(Artifact).where(Artifact.version_id == proposal.draft_version_id)).all()
    if not artifacts or any(a.status != 'Completed' for a in artifacts):
        raise HTTPException(409, 'All draft files must be completed before approval. Retry failed files first.')
    version = db.get(Version, proposal.draft_version_id)
    written = []
    try:
        for a in artifacts:
            if a.kind not in PUBLISHED_KINDS or not a.key:
                continue
            data = storage.get(a.key)
            key = f'{proposal.project_id}/response-documents/{proposal.id}/{a.filename}'
            storage.put(key, data, MIMES.get(a.filename.rsplit('.', 1)[-1], 'application/octet-stream'))
            written.append(key)
            db.add(ResponseDocument(project_id=proposal.project_id, proposal_id=proposal.id, version_id=version.id, kind=a.kind, filename=a.filename, key=key, size=len(data)))
    except Exception:
        db.rollback()
        for key in written:
            try:
                storage.delete(key)
            except Exception:
                pass
        raise HTTPException(503, 'Could not publish response documents. Check storage and retry approval.') from None
    stamp = now()
    proposal.reviews = [*(proposal.reviews or []), entry]
    proposal.status, proposal.approved_by, proposal.approved_at, proposal.published_at, proposal.updated_at = 'Live', user.id, stamp, stamp, stamp
    db.add(AgentMessage(proposal_id=proposal.id, agent='Reviewer', recipient='DocumentsAgent', kind='result', content='Approved' + (': ' + entry['comments'] if entry['comments'] else '.')))
    db.add(AgentMessage(proposal_id=proposal.id, agent='DocumentsAgent', recipient='User', kind='result', content=f'Published {len(written)} response document(s) from draft v{version.number}. The proposal is live.'))
    audit(db, user, 'proposal_approved', proposal.id)
    db.commit()
    return {'status': proposal.status, 'documents': len(written)}


@app.post('/api/proposals/{proposal_id}/retry', status_code=202)
def retry_proposal(proposal_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    proposal = owned_proposal(db, user, proposal_id)
    if proposal.status != 'Failed':
        raise HTTPException(409, 'Only a failed proposal can be retried.')
    limit_jobs(db, user)
    job = queue_proposal(db, proposal)
    audit(db, user, 'proposal_retried', proposal.id)
    db.commit()
    return job


response_signer = URLSafeTimedSerializer(settings.session_secret, salt='response-document-download')


@app.post('/api/response-documents/{document_id}/download-link')
def response_download_link(document_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    d = db.get(ResponseDocument, document_id)
    if not d:
        raise HTTPException(404)
    owned(db, user, d.project_id)
    return {'url': f'/api/response-download/{response_signer.dumps({"document": d.id, "user": user.id})}', 'expires_in': settings.download_ttl}


@app.get('/api/response-download/{token}')
def response_download(token: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    try:
        claims = response_signer.loads(token, max_age=settings.download_ttl)
    except (BadSignature, SignatureExpired):
        raise HTTPException(403, 'Download link expired. Request a new link.') from None
    d = db.get(ResponseDocument, claims['document']) if claims['user'] == user.id else None
    if not d:
        raise HTTPException(404)
    owned(db, user, d.project_id)
    try:
        data = storage.get(d.key)
    except Exception:
        raise HTTPException(503, 'File storage is unavailable. Try again or check storage configuration.') from None
    audit(db, user, 'response_document_downloaded', d.id)
    db.commit()
    ext = d.filename.rsplit('.', 1)[-1]
    return Response(data, media_type=MIMES.get(ext, 'application/octet-stream'), headers={'Content-Disposition': f'attachment; filename="{d.filename}"', 'Cache-Control': 'private, no-store'})


@app.delete('/api/projects/{project_id}')
def delete_project(project_id: str, user=Depends(current_user), db: DBSession = Depends(get_db)):
    project = owned(db, user, project_id)
    no_active_job(db, project_id)
    for a in db.scalars(select(Attachment).where(Attachment.project_id == project_id)):
        storage.delete(a.key)
    for a in db.scalars(select(Artifact).where(Artifact.project_id == project_id)):
        if a.key:
            storage.delete(a.key)
    for d in db.scalars(select(ResponseDocument).where(ResponseDocument.project_id == project_id)):
        storage.delete(d.key)
    audit(db, user, 'project_deleted', project_id)
    db.delete(project)
    db.commit()
    return {'ok':True}


dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')
    @app.get('/')
    def index():
        return FileResponse(dist / 'index.html')
