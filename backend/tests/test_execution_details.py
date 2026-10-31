import json
from fastapi.testclient import TestClient
from app import worker, artifacts, providers
from app.db import Job, JobEvent
from app.main import app
from app.config import settings
from app.execution import observe_job, emit
from test_workspace import sample_solution, fake_render
from test_proposals import COMPLETE


def queued(client):
    pid=client.post('/api/projects',json={'title':'Execution detail check'}).json()['id']
    job=client.post(f'/api/projects/{pid}/generate',json={'prompt':'PRIVATE REQUEST CONTENT for an enterprise portal','preferences':{'outputs':['solution','presentation']}}).json()
    return pid,job


def test_execution_details_are_owned_and_queued_activity_is_recorded(workspace):
    alice,bob,_=workspace
    _,job=queued(alice)
    path=f"/api/jobs/{job['id']}/execution"
    anonymous=TestClient(app)
    assert anonymous.get(path).status_code==401
    anonymous.close()
    assert bob.get(path).status_code==404
    data=alice.get(path).json()
    assert data['recorded'] and data['current']['agent']=='RequestQueue'
    assert data['stages'][0]['stage']=='Queued'
    assert data['activity'][0]['kind']=='stage_started'
    assert 'PRIVATE REQUEST CONTENT' not in json.dumps(data)


def test_actual_worker_stage_timings_and_file_activity_are_recorded(workspace, monkeypatch):
    monkeypatch.setattr(worker, 'render_diagram', fake_render)
    monkeypatch.setattr(artifacts, 'render_diagram', fake_render)
    alice,_,_=workspace
    _,job=queued(alice)
    assert worker.run_once()
    data=alice.get(f"/api/jobs/{job['id']}/execution").json()
    assert data['status']=='Completed'
    assert [row['stage'] for row in data['stages']]==['Queued','Building Context','Generating Solution','Estimating','Planning Resources','Defining Methodology','Designing Diagrams','Creating Files']
    assert all(row['duration_ms']>=0 and row['finished_at'] for row in data['stages'])
    assert all(row['started_at'].endswith(('Z','+00:00')) for row in data['stages'])
    assert {row['agent'] for row in data['stages']}=={'RequestQueue','ContextBuilder','SolutionAgent','EstimationsAgent','ResourcesAgent','DeliveryMethodologyAgent','DiagramsAgent','DocumentBuilder'}
    assert any(row['kind']=='context_built' for row in data['activity'])
    assert len([row for row in data['activity'] if row['kind']=='file_completed'])==40
    assert 'PRIVATE REQUEST CONTENT' not in json.dumps(data)


def test_model_usage_retries_and_timings_without_recording_response_or_secrets(workspace,monkeypatch):
    monkeypatch.setattr(worker,'render_diagram',fake_render)
    monkeypatch.setattr(artifacts,'render_diagram',fake_render)
    alice,_,_=workspace
    _,job=queued(alice)
    monkeypatch.setattr(settings,'llm_provider','bedrock')
    monkeypatch.setattr(settings,'llm_model','us.anthropic.claude-test')
    monkeypatch.setattr(settings,'aws_bearer_token_bedrock',None)
    monkeypatch.setattr(settings,'openai_api_key','PRIVATE CREDENTIAL')
    calls=[]
    class Client:
        def converse(self,**options):
            calls.append(options)
            result=sample_solution().model_dump()
            schema=options['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json']
            if schema.get('title')=='EstimationResult':
                result={'estimates':result['estimates'],'contingency_percent':15,'commercial_model':'effort_only','commercial_basis':'No commercial terms provided.'}
            elif schema.get('title')=='ResourcePlan':
                from app.agents import ResourcesAgent,ExecutionBus
                result=ResourcesAgent(ExecutionBus()).heuristic(sample_solution()).model_dump()
            elif schema.get('title')=='MethodologyPlan':
                from app.schemas import MethodologyPlan,Methodology
                result=MethodologyPlan(methodology=Methodology(name='Agile',overview='Iterative delivery with quality gates.'),phases=sample_solution().phases).model_dump()
            elif schema.get('title')=='ArchitectureViews':
                from app.diagrams import DiagramsAgent
                result=DiagramsAgent().demo(sample_solution()).model_dump()
            if len(calls)==1:
                result['sections'][0]['classification']='PRIVATE INVALID MODEL OUTPUT'
            return {'stopReason':'tool_use','usage':{'inputTokens':700,'outputTokens':1100,'totalTokens':1800},'output':{'message':{'content':[{'toolUse':{'name':'submit_result','input':result}}]}}}
    monkeypatch.setattr(providers.boto3,'client',lambda *args,**kwargs:Client())
    worker.run_once()
    data=alice.get(f"/api/jobs/{job['id']}/execution").json()
    assert data['status']=='Completed'
    assert data['provider']['model']=='us.anthropic.claude-test'
    requests=[event for event in data['activity'] if event['kind']=='provider_request_started']
    responses=[event for event in data['activity'] if event['kind']=='provider_response_received']
    assert len(requests)==len(responses)==6
    assert responses[0]['details']['input_tokens']==700
    assert responses[0]['details']['output_tokens']==1100
    assert any(event['kind']=='provider_retry' for event in data['activity'])
    assert any(event['kind']=='schema_validation_failed' for event in data['activity'])
    assert all(event['details']['duration_ms']>=0 for event in data['activity'] if event['kind']=='provider_request_finished')
    text=json.dumps(data)
    assert not any(secret in text for secret in ['PRIVATE REQUEST CONTENT','PRIVATE CREDENTIAL','PRIVATE INVALID MODEL OUTPUT'])


def test_cancelled_workflow_records_terminal_event_and_drops_late_activity(workspace):
    alice,_,sessions=workspace
    _,job=queued(alice)
    assert alice.post(f"/api/jobs/{job['id']}/cancel").status_code==200
    with observe_job(job['id'],sessions):
        emit('provider_request_finished','A late model result must not appear.')
    data=alice.get(f"/api/jobs/{job['id']}/execution").json()
    assert data['status']=='Cancelled'
    assert data['activity'][-1]['kind']=='workflow_cancelled'
    assert data['stages'][0]['outcome']=='Cancelled'
    assert not any(event['kind']=='provider_request_finished' for event in data['activity'])


def test_legacy_work_has_no_fabricated_execution_history(workspace):
    alice,_,sessions=workspace
    _,job=queued(alice)
    with sessions() as db:
        db.query(JobEvent).filter_by(job_id=job['id']).delete()
        db.get(Job,job['id']).status='Generating Solution'
        db.commit()
    data=alice.get(f"/api/jobs/{job['id']}/execution").json()
    assert not data['recorded'] and data['activity']==[] and data['stages']==[]
    assert data['current']['implementation']=='app.agents.SolutionAgent.run'
    assert data['current']['agent_type']=='Agent'


def test_export_worker_startup_does_not_claim_to_build_model_context(workspace):
    alice,_,sessions=workspace
    _,job=queued(alice)
    with sessions() as db:
        row=db.get(Job,job['id'])
        row.kind,row.status='files','Building Context'
        db.commit()
    data=alice.get(f"/api/jobs/{job['id']}/execution").json()
    assert data['current']['agent']=='JobWorker'
    assert data['current']['implementation']=='app.worker.run_isolated'


def test_rfp_exposes_actual_specialist_agent_classes(workspace,monkeypatch):
    alice,_,_=workspace
    monkeypatch.setattr(worker,'render_diagram',fake_render)
    monkeypatch.setattr(artifacts,'render_diagram',fake_render)
    pid=alice.post('/api/projects',json={'title':'RFP agent trace'}).json()['id']
    result=alice.post(f'/api/projects/{pid}/proposals',json={'request':COMPLETE,'formats':['docx']}).json()
    worker.run_once()
    data=alice.get(f"/api/jobs/{result['job']['id']}/execution").json()
    actors={row['agent'] for row in data['stages']}
    assert {'RequirementsCollectorAgent','ProposalCreatorAgent','EstimationsAgent','ResourcesAgent','DeliveryMethodologyAgent','DocumentsAgent'}<=actors
    assert all(row['agent_type']=='Agent' for row in data['stages'] if row['stage']!='Queued')
