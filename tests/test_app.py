from unittest.mock import Mock, patch
import pytest
from app import app
from db import validate_query
from quiz import QUESTIONS

@pytest.fixture
def client():
    app.config['TESTING']=True
    return app.test_client()

@pytest.mark.parametrize('path,method',[('/api/run','post'),('/api/save','post'),('/api/answers','get')])
def test_signed_out_cannot_access_database(client,path,method):
    with patch('db.connect') as connect:
        response=getattr(client,method)(path,json={'question_id':1,'query':'SELECT 1'})
        assert response.status_code==401
        connect.assert_not_called()

def test_forged_session_rejected(client):
    with patch('app.requests.get',return_value=Mock(status_code=401)),patch('db.connect') as connect:
        response=client.post('/api/run',headers={'Authorization':'Bearer forged'},json={'question_id':1,'query':'SELECT 1'})
        assert response.status_code==401
        connect.assert_not_called()

def test_verified_identity_used_instead_of_request_user(client):
    verified='11111111-1111-4111-8111-111111111111'
    with patch('app.requests.get',return_value=Mock(status_code=200,json=lambda:{'id':verified})),patch('db.save_answer') as save:
        response=client.post('/api/save',headers={'Authorization':'Bearer valid'},json={'question_id':1,'query':"SELECT 'test'",'user_id':'attacker'})
        assert response.status_code==200
        save.assert_called_once_with(verified,1,"SELECT 'test'")

@pytest.mark.parametrize('query',[
 'DELETE FROM quiz_data.orders', 'SELECT 1; SELECT 2',
 'WITH gone AS (DELETE FROM quiz_data.orders RETURNING *) SELECT * FROM gone',
 'SELECT * FROM auth.users', 'SELECT * FROM quiz_private.audit_log',
 "SELECT set_config('role','postgres',false)", "SELECT pg_read_file('/etc/passwd')",
 'SELECT * INTO quiz_data.newtable FROM quiz_data.orders',
 'SELECT * FROM quiz_data.orders FOR UPDATE', 'SELECT * FROM pg_catalog.pg_authid',
 "SELECT 'postgres'::regrole", 'SELECT public.count(*) FROM quiz_data.orders',
 'SELECT * FROM otherdb.quiz_data.orders', 'SELECT CURRENT_USER',
])
def test_unsafe_sql_rejected(query):
    with pytest.raises(ValueError):validate_query(query)

@pytest.mark.parametrize('question',QUESTIONS)
def test_reference_answers_allowed(question):validate_query(question['sql'])

def test_equivalent_query_and_comments_allowed():
    validate_query("-- a different valid solution\nSELECT name FROM customers WHERE id NOT IN (SELECT customer_id FROM orders) ORDER BY name;")

def test_public_pages_and_point_total(client):
    assert client.get('/').status_code==200
    data=client.get('/api/quiz').json
    assert sum(q['points'] for q in data['questions'])==20
    assert len(data['questions'])==5
    assert all(q['sql'] and q['columns'] and q['rows'] for q in data['questions'])

def test_no_private_config_exposed(client):
    assert set(client.get('/api/config').json)=={'url','key'}
