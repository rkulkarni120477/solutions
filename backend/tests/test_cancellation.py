import subprocess
import sys
import threading
import time
import pytest
from app import worker, artifacts
from app.db import Job, Version, Artifact, Proposal
from test_workspace import sample_solution, fake_render
from test_proposals import COMPLETE


def queued(client,preferences=None):
    pid = client.post('/api/projects', json={'title':'Cancellation check'}).json()['id']
    response = client.post(f'/api/projects/{pid}/generate', json={'prompt':'Design an enterprise knowledge portal', **({'preferences':preferences} if preferences else {})})
    assert response.status_code == 202
    return pid, response.json()


def test_cancel_is_owned_idempotent_and_queued_work_never_runs(workspace):
    alice, bob, sessions = workspace
    pid, job = queued(alice)
    endpoint = '/api/jobs/'+job['id']+'/cancel'
    assert bob.post(endpoint).status_code == 404
    assert alice.post(endpoint).json() == {'status':'Cancelled','cancelled':True}
    assert alice.post(endpoint).json()['status'] == 'Cancelled'
    assert not worker.run_once()
    assert alice.get(f'/api/projects/{pid}').json()['jobs'][0]['status'] == 'Cancelled'
    assert alice.post(f'/api/projects/{pid}/generate',json={'prompt':'Start a new version after cancellation'}).status_code == 202


def test_cancellation_discards_a_late_model_response(workspace, monkeypatch):
    alice, _, sessions = workspace
    pid, job = queued(alice)
    def late_response(context):
        assert alice.post('/api/jobs/'+job['id']+'/cancel').status_code == 200
        return sample_solution()
    monkeypatch.setattr(worker,'generate',late_response)
    assert worker.run_once()
    with sessions() as db:
        assert db.get(Job,job['id']).status == 'Cancelled'
        assert db.get(Version,job['version_id']).response is None
        assert db.query(Artifact).filter_by(project_id=pid).count() == 0


def test_cancellation_keeps_completed_files_and_stops_unfinished_exports(workspace):
    alice, _, sessions = workspace
    pid, job = queued(alice)
    from app.storage import storage
    storage.put('saved-result.docx',b'completed result')
    with sessions() as db:
        db.get(Job,job['id']).status='Creating Files'
        completed=Artifact(project_id=pid,version_id=job['version_id'],kind='docx',filename='saved.docx',status='Completed',key='saved-result.docx')
        db.add(completed)
        for status in ['Queued','Creating Files']:
            db.add(Artifact(project_id=pid,version_id=job['version_id'],kind='pdf',filename='pending.pdf',status=status))
        db.commit()
        completed_id=completed.id
    assert alice.post('/api/jobs/'+job['id']+'/cancel').status_code==200
    with sessions() as db:
        files=db.query(Artifact).filter_by(version_id=job['version_id']).all()
        assert [a.status for a in files].count('Cancelled')==2
        assert db.get(Artifact,completed_id).status=='Completed'
    link=alice.post('/api/artifacts/'+completed_id+'/download-link').json()['url']
    assert alice.get(link).content==b'completed result'


def test_cancelled_stage_cannot_be_resurrected(workspace):
    alice, _, sessions = workspace
    _, job = queued(alice)
    with sessions() as db:
        stale_job=db.get(Job,job['id'])
        alice.post('/api/jobs/'+job['id']+'/cancel')
        with pytest.raises(worker.JobCancelled):
            worker.stage(db,stale_job,'Completed')
    with sessions() as db:
        assert db.get(Job,job['id']).status=='Cancelled'


def test_cancellation_during_file_build_prevents_publication(workspace,monkeypatch):
    alice, _, sessions = workspace
    _, job = queued(alice)
    monkeypatch.setattr(worker,'generate',lambda context:sample_solution())
    monkeypatch.setattr(worker,'render_diagram',fake_render)
    calls=[]
    def build(*args):
        calls.append(1)
        assert alice.post('/api/jobs/'+job['id']+'/cancel').status_code==200
        return b'late file bytes'
    monkeypatch.setattr(worker,'build_artifact',build)
    assert worker.run_once()
    assert len(calls)==1
    with sessions() as db:
        assert db.get(Job,job['id']).status=='Cancelled'
        assert all(a.status=='Cancelled' and a.key is None for a in db.query(Artifact).filter_by(version_id=job['version_id']))


def test_cancelling_a_finished_job_preserves_its_status(workspace):
    alice, _, sessions = workspace
    _, job = queued(alice)
    with sessions() as db:
        db.get(Job,job['id']).status='Completed'
        db.commit()
    assert alice.post('/api/jobs/'+job['id']+'/cancel').json()=={'status':'Completed','cancelled':False}


def test_proposal_can_be_cancelled_and_explicitly_retried(workspace):
    alice, _, sessions=workspace
    pid=alice.post('/api/projects',json={'title':'Proposal cancellation'}).json()['id']
    response=alice.post(f'/api/projects/{pid}/proposals',json={'request':COMPLETE}).json()
    assert alice.post('/api/jobs/'+response['job']['id']+'/cancel').status_code==200
    with sessions() as db:
        assert db.get(Proposal,response['proposal_id']).status=='Cancelled'
    assert alice.post('/api/proposals/'+response['proposal_id']+'/retry').status_code==202


def test_isolated_worker_terminates_its_running_process_on_cancel(workspace,monkeypatch):
    alice, _, sessions=workspace
    _, job=queued(alice)
    original_popen=subprocess.Popen
    started=threading.Event()
    processes=[]
    def popen(command,*args,**options):
        if 'app.worker_task' not in command:
            return original_popen(command,*args,**options)
        process=original_popen([sys.executable,'-c','import time; time.sleep(60)'],*args,**options)
        processes.append(process)
        started.set()
        return process
    monkeypatch.setattr(worker.subprocess,'Popen',popen)
    results=[]
    def cancel():
        assert started.wait(10)
        results.append(alice.post('/api/jobs/'+job['id']+'/cancel').status_code)
    thread=threading.Thread(target=cancel)
    thread.start()
    begin=time.monotonic()
    try:
        worker.run_isolated(job['id'])
    finally:
        thread.join(timeout=10)
        for process in processes:
            if process.poll() is None:
                worker.stop_process(process)
    assert results==[200]
    assert time.monotonic()-begin<10
    assert processes[0].poll() is not None
    with sessions() as db:
        assert db.get(Job,job['id']).status=='Cancelled'


def test_worker_launch_failure_is_reported_instead_of_leaving_job_running(workspace,monkeypatch):
    alice, _, sessions=workspace
    _, job=queued(alice)
    def unavailable(*args,**kwargs):
        raise OSError('Cannot launch worker')
    monkeypatch.setattr(worker.subprocess,'Popen',unavailable)
    worker.run_isolated(job['id'])
    with sessions() as db:
        assert db.get(Job,job['id']).status=='Failed'


def test_real_isolated_job_generates_files_in_the_test_database(workspace,monkeypatch):
    alice, _, sessions=workspace
    # Keep this subprocess test independent of a live diagram-rendering service.
    _, job=queued(alice,{'outputs':['solution']})
    from app.storage import storage
    monkeypatch.setenv('DATABASE_URL',str(sessions.kw['bind'].url).replace('\\','/'))
    monkeypatch.setenv('STORAGE_PATH',str(storage.root))
    assert worker.run_once(isolate=True)
    with sessions() as db:
        result=db.get(Job,job['id'])
        assert result.status=='Completed',result.error
        files=db.query(Artifact).filter_by(version_id=job['version_id']).all()
        assert {file.kind for file in files}=={'docx','pdf','pptx','zip'}
        assert all(file.status=='Completed' for file in files)


def test_cancel_during_artifact_planning_does_not_leave_queued_files(workspace,monkeypatch):
    alice, _, sessions=workspace
    _, job=queued(alice)
    monkeypatch.setattr(worker,'generate',lambda context:sample_solution())
    monkeypatch.setattr(worker,'render_diagram',fake_render)
    original=artifacts.plan_artifacts
    def plan(db,version,documents=None,job=None):
        alice.post('/api/jobs/'+job.id+'/cancel')
        return original(db,version,documents,job=job)
    monkeypatch.setattr(worker,'plan_artifacts',plan)
    worker.run_once()
    with sessions() as db:
        assert db.get(Job,job['id']).status=='Cancelled'
        assert db.query(Artifact).filter_by(version_id=job['version_id']).count()==0
