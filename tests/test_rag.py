"""Unit tests use mocked AI responses; live retrieval is checked separately."""
from unittest.mock import Mock, patch
import pytest
import rag
from app import app
from quiz import QUESTIONS

def test_vector_features_are_normalized_and_distinguish_topics():
    v=rag.embed('customers without orders',{})
    assert len(v)==512
    assert sum(x*x for x in v)==pytest.approx(1)
    assert v!=rag.embed('menu price drink revenue',{})

@pytest.mark.parametrize('q',QUESTIONS)
def test_validation_accepts_expected_result_and_aliases(q):
    actual={'columns':['alias']*len(q['columns']),'rows':q['rows'],'truncated':False}
    assert rag.validate_result(actual,q['id'])['correct']

def test_validation_preserves_null_duplicates_and_requested_order():
    assert not rag.validate_result({'columns':['name'],'rows':[[None]],'truncated':False},5)['correct']
    assert not rag.validate_result({'columns':['name'],'rows':[['Emery'],['Emery']],'truncated':False},5)['correct']
    q=QUESTIONS[0]
    assert not rag.validate_result({'columns':q['columns'],'rows':list(reversed(q['rows'])),'truncated':False},1)['correct']
    assert not rag.validate_result({'columns':['name'],'rows':[['Emery']],'truncated':True},5)['correct']

def test_generate_passes_retrieved_context_to_provider(monkeypatch):
    monkeypatch.setenv('AI_API_KEY','unit-test-only')
    monkeypatch.setenv('AI_MODEL','test-model')
    source={'id':'retrieved-test','text':'The column is sale_price.'}
    response=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':'```sql\nSELECT 1;\n```'}}]})
    with patch('rag.requests.post',return_value=response) as post:
        sql,model=rag.generate('What is the price?',[source])
        assert sql=='SELECT 1;'
        assert 'sale_price' in post.call_args.kwargs['json']['messages'][0]['content']
        assert model=='test-model'

def test_unsafe_model_output_is_never_executed():
    with patch('rag.retrieve',return_value=([{'id':'s','text':'schema'}],1)),patch('rag.generate',return_value=('DELETE FROM quiz_data.orders','test')),patch('db.run_query') as execute:
        result=rag.pipeline('delete everything',1,execute=True)
        assert not result['safe_to_run']
        assert result['execution'] is None
        execute.assert_not_called()

def test_generate_requires_verified_signin():
    with app.test_client() as client,patch('rag.pipeline') as pipeline:
        response=client.post('/api/generate',json={'question':'Show drinks','question_id':1})
        assert response.status_code==401
        pipeline.assert_not_called()

def test_quota_rejection_does_not_call_model(monkeypatch):
    monkeypatch.setenv('AI_API_KEY','unit-test-only')
    monkeypatch.setenv('AI_MODEL','test-model')
    verified='11111111-1111-4111-8111-111111111111'
    with app.test_client() as client,patch('app.requests.get',return_value=Mock(status_code=200,json=lambda:{'id':verified})),patch('db.reserve_ai_request',return_value=False),patch('rag.pipeline') as pipeline:
        response=client.post('/api/generate',headers={'Authorization':'Bearer valid'},json={'question':'Show drinks','question_id':1})
        assert response.status_code==429
        pipeline.assert_not_called()

def test_real_chroma_vector_search_with_fixture_documents(monkeypatch):
    fixtures=[
      {'id':'fixture-customers','title':'Customer orders','kind':'test fixture','text':'Customers without orders, customers never purchased.'},
      {'id':'fixture-revenue','title':'Revenue','kind':'test fixture','text':'Revenue sales quantity multiplied by unit price category revenue.'},
      {'id':'fixture-drinks','title':'Drinks','kind':'test fixture','text':'Drinks affordable coffee tea price menu drinks.'},
    ]
    monkeypatch.setattr(rag,'_index',None)
    monkeypatch.setattr(rag,'knowledge',lambda:fixtures)
    result,count=rag.retrieve('customers without orders',top_k=2)
    assert count==3
    assert result[0]['id']=='fixture-customers'
    assert result[0]['distance']<result[1]['distance']
