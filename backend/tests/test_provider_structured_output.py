import json
import pytest
from app import providers
from app.config import settings
from app.schemas import Preferences, ProposalPlan
from app.context import build_context
from test_workspace import sample_solution


@pytest.fixture
def bedrock(monkeypatch):
    monkeypatch.setattr(settings, 'llm_provider', 'bedrock')
    monkeypatch.setattr(settings, 'llm_model', 'us.anthropic.claude-sonnet-test')
    monkeypatch.setattr(settings, 'aws_bearer_token_bedrock', None)


def test_bedrock_forces_schema_tool_and_sends_schema_only_once(bedrock, monkeypatch):
    calls = []
    expected = {'status':'connected'}
    class Client:
        def converse(self, **options):
            calls.append(options)
            return {'stopReason':'tool_use','usage':{'outputTokens':20},'output':{'message':{'content':[{'toolUse':{'name':'submit_result','input':expected}}]}}}
    monkeypatch.setattr(providers.boto3, 'client', lambda *args,**kwargs: Client())
    schema = {'type':'object','properties':{'status':{'type':'string'}},'required':['status']}
    response = providers._complete('Return the result.', json.dumps({'schema':schema,'input':{'request':'connect'}}))
    assert json.loads(response) == expected
    call = calls[0]
    assert call['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'] == schema
    assert call['toolConfig']['toolChoice'] == {'tool':{'name':'submit_result'}}
    message = json.loads(call['messages'][0]['content'][0]['text'])
    assert 'schema' not in message and message['input']['request']=='connect'


def test_bedrock_truncated_tool_output_is_not_accepted_as_success(bedrock, monkeypatch):
    class Client:
        def converse(self, **options):
            return {'stopReason':'max_tokens','output':{'message':{'content':[{'text':'{"title": "partial'}]}}}
    monkeypatch.setattr(providers.boto3,'client',lambda *args,**kwargs:Client())
    with pytest.raises(providers.OutputLimitError,match='output-token limit'):
        providers._complete('Return JSON.',json.dumps({'schema':{'type':'object'},'input':{}}))


def test_truncation_switches_to_validated_parts_within_input_budget(bedrock, monkeypatch):
    context=build_context('Design an enterprise portal',Preferences().model_dump(),[],[],[])
    calls=[]
    def complete(system,payload):
        assert providers.request_size(system,payload)<=settings.max_input_tokens
        data=json.loads(payload)
        calls.append(data)
        title=data['schema']['title']
        if title=='SolutionDraft':
            raise providers.OutputLimitError('Output limit')
        from app.solution_draft import SolutionOutline, DetailedSection, DeliverySeed
        s=sample_solution()
        if title=='SolutionOutline':
            values={key:value for key,value in s.model_dump().items() if key in SolutionOutline.model_fields}
            values['section_topics']=[{'title':'Proposed solution','classification':'recommendation'},{'title':'Security and risks','classification':'requires validation'}]
            return SolutionOutline.model_validate(values).model_dump_json()
        if title=='DetailedSection':
            topic=data['input']['topic']
            return DetailedSection(**topic,content='Complete solution-specific detail with boundaries, dependencies and decisions.',sources=[]).model_dump_json()
        return DeliverySeed(estimates=s.estimates,phases=s.phases).model_dump_json()
    monkeypatch.setattr(providers,'_complete',complete)
    result=providers.generate(context)
    assert [section.title for section in result.sections]==['Proposed solution','Security and risks']
    assert [call['schema']['title'] for call in calls]==['SolutionDraft','SolutionOutline','DetailedSection','DetailedSection','DeliverySeed']
    assert result.estimates and result.diagrams==[]
    assert all(call['input']['context']==context for call in calls[1:])


def test_repair_identifies_invalid_fields_without_logging_response_content(bedrock,monkeypatch,caplog):
    context=build_context('Design an enterprise portal',Preferences().model_dump(),[],[],[])
    invalid=sample_solution().model_dump()
    invalid['sections'][0]['classification']='PRIVATE INVALID INPUT'
    calls=[]
    def complete(system,payload):
        calls.append(json.loads(payload))
        if len(calls)==1:
            return json.dumps(invalid)
        repair=calls[1]['repair']
        assert 'sections.0.classification: literal_error' in repair
        assert 'PRIVATE INVALID INPUT' not in repair
        assert len(json.dumps(repair,ensure_ascii=False).encode())<=providers.REPAIR_RESERVE
        return sample_solution().model_dump_json()
    monkeypatch.setattr(providers,'_complete',complete)
    assert providers.generate(context).title
    assert 'PRIVATE INVALID INPUT' not in caplog.text


def test_repeated_truncation_has_specific_error_instead_of_schema_error(bedrock,monkeypatch):
    context=build_context('Design an enterprise portal',Preferences().model_dump(),[],[],[])
    calls=[]
    def complete(*args):
        calls.append(1)
        raise providers.OutputLimitError('Output limit')
    monkeypatch.setattr(providers,'_complete',complete)
    with pytest.raises(providers.ProviderError,match='shorter retry'):
        providers.generate(context)
    assert len(calls)==3  # One draft, then two bounded outline attempts.


def test_agent_schema_failure_gets_targeted_repair(bedrock,monkeypatch):
    expected=ProposalPlan(response_type='Response',formats=['docx'],outline=['Solution'],win_themes=[],tone='Clear')
    calls=[]
    def complete(system,payload):
        calls.append(json.loads(payload))
        if len(calls)==1:
            return json.dumps({**expected.model_dump(),'formats':['invalid']})
        assert 'formats.0: literal_error' in calls[1]['repair']
        return expected.model_dump_json()
    monkeypatch.setattr(providers,'_complete',complete)
    assert providers.structured(ProposalPlan,'Plan a proposal.',{'request':'Enterprise portal'})==expected
