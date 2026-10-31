import json
import pytest
from app import providers
from app.config import settings
from app.schemas import Preferences, Solution
from app.solution_draft import SolutionDraft, SolutionOutline, DetailedSection, DeliverySeed
from app.context import build_context
from test_workspace import sample_solution
from test_context_budget import rfp_attachment


def outline():
    data={key:value for key,value in sample_solution().model_dump().items() if key in SolutionOutline.model_fields}
    return SolutionOutline.model_validate({**data,'section_topics':[{'title':'Solution architecture','classification':'recommendation'}]})


def test_primary_contract_excludes_delegated_expensive_outputs(monkeypatch):
    schema=providers.solution_schema()
    assert schema['title']=='SolutionDraft'
    assert not {'diagrams','resources','methodology','racii','pricing'} & set(schema['properties'])
    assert schema['properties']['sections']['maxItems']==8
    values={key:value for key,value in sample_solution().model_dump().items() if key in SolutionDraft.model_fields}
    draft=SolutionDraft.model_validate(values)
    assert isinstance(draft.solution(),Solution) and draft.solution().diagrams==[]


def test_draft_validation_retry_does_not_request_delegated_legacy_fields():
    from pydantic import ValidationError
    values={key:value for key,value in sample_solution().model_dump().items() if key in SolutionDraft.model_fields}
    values['sections'][0]['content']='x'*2601
    with pytest.raises(ValidationError) as error:
        providers.validate_solution(json.dumps(values))
    repair=providers.retry_instruction(error.value)
    assert 'sections.0.content: string_too_long' in repair
    assert 'diagrams' not in repair and 'artifact_requests' not in repair


def test_parts_preserve_reference_citations_and_bound_large_rfp(monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','bedrock')
    monkeypatch.setattr(settings,'llm_model','test')
    monkeypatch.setattr(providers.time,'sleep',lambda _:None)
    ctx=build_context('Prepare an enterprise proposal from all supplied requirements',Preferences().model_dump(),[rfp_attachment()],[],['Retain audit records'])
    original=json.dumps(ctx)
    calls=[]
    def complete(system,payload):
        assert providers.request_size(system,payload)<=settings.max_input_tokens
        data=json.loads(payload);title=data['schema']['title'];calls.append(title)
        if title=='SolutionDraft':raise providers.OutputLimitError('truncated')
        assert data['input']['context']['approved_decisions']==['Retain audit records']
        if title=='SolutionOutline':return outline().model_dump_json()
        if title=='DetailedSection':
            return DetailedSection(title='Solution architecture',content='Complete section content.',classification='recommendation',sources=[ctx['reference_passages'][0]['id']]).model_dump_json()
        return DeliverySeed(estimates=sample_solution().estimates,phases=sample_solution().phases).model_dump_json()
    monkeypatch.setattr(providers,'_complete',complete)
    result=providers.generate(ctx)
    assert result.sections[0].sources==[ctx['reference_passages'][0]['id']]
    assert json.dumps(ctx)==original
    assert calls==['SolutionDraft','SolutionOutline','DetailedSection','DeliverySeed']


def test_failed_section_does_not_publish_a_partial_solution(monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','bedrock')
    monkeypatch.setattr(settings,'llm_model','test')
    ctx=build_context('Design an enterprise portal',Preferences().model_dump(),[],[],[])
    def complete(system,payload):
        name=json.loads(payload)['schema']['title']
        if name=='SolutionDraft':raise providers.OutputLimitError('truncated')
        if name=='SolutionOutline':return outline().model_dump_json()
        raise providers.ProviderError('Section model is unavailable')
    monkeypatch.setattr(providers,'_complete',complete)
    with pytest.raises(providers.ProviderError,match='Section model is unavailable'):
        providers.generate(ctx)


def test_parts_retry_invalid_citations_without_accepting_them(monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','bedrock')
    monkeypatch.setattr(settings,'llm_model','test')
    monkeypatch.setattr(providers.time,'sleep',lambda _:None)
    ctx=build_context('Design an enterprise portal',Preferences(outputs=['solution']).model_dump(),[],[],[])
    attempts=[]
    def complete(system,payload):
        data=json.loads(payload);name=data['schema']['title']
        if name=='SolutionDraft':raise providers.OutputLimitError('truncated')
        if name=='SolutionOutline':return outline().model_dump_json()
        attempts.append(data)
        return DetailedSection(title='Solution architecture',content='Complete section.',classification='recommendation',sources=['not-supplied'] if len(attempts)==1 else []).model_dump_json()
    monkeypatch.setattr(providers,'_complete',complete)
    result=providers.generate(ctx)
    assert len(attempts)==2 and result.sections[0].sources==[]
    assert result.estimates==[] and result.phases==[]
