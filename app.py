import os
import uuid
from functools import wraps
from flask import Flask, jsonify, render_template, request, g
import requests
import psycopg
import db
import rag
from quiz import QUESTIONS, SCHEMA

app = Flask(__name__, static_folder='public/static', static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 20000

def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        authorization = request.headers.get('Authorization', '')
        if not authorization.startswith('Bearer ') or len(authorization) > 10000:
            return jsonify(error='Sign in to run queries or save answers.'), 401
        try:
            # Verify with Supabase Auth, never trust a browser-supplied user ID.
            response = requests.get(os.environ['SUPABASE_URL']+'/auth/v1/user',
                headers={'apikey': os.environ['SUPABASE_PUBLISHABLE_KEY'], 'Authorization': authorization}, timeout=10)
            if response.status_code != 200: return jsonify(error='Your session expired. Sign in again.'), 401
            g.user_id = str(uuid.UUID(response.json()['id']))
        except (requests.RequestException, ValueError, KeyError):
            return jsonify(error='Unable to verify your session. Please sign in again.'), 401
        return fn(*args, **kwargs)
    return wrapper

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    if request.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
    return response

@app.get('/')
def index():
    return render_template('index.html')

@app.get('/api/config')
def config():
    # This is a publishable key, not a database password or service-role key.
    return jsonify(url=os.getenv('SUPABASE_URL',''), key=os.getenv('SUPABASE_PUBLISHABLE_KEY',''))

@app.get('/api/quiz')
def quiz(): return jsonify(questions=QUESTIONS, schema=SCHEMA)

@app.get('/api/answers')
@authenticated
def get_answers(): return jsonify(answers=db.answers(g.user_id))

def payload():
    value=request.get_json(silent=True) or {}
    q=value.get('question_id')
    if type(q) is not int or q not in {x['id'] for x in QUESTIONS}:
        raise ValueError('Choose a valid question.')
    query=value.get('query')
    if not isinstance(query,str) or not query.strip() or len(query)>12000:
        raise ValueError('Enter SQL of at most 12,000 characters.')
    return q,query

@app.post('/api/run')
@authenticated
def run():
    question_id, query = payload()
    result = db.run_query(query)
    db.audit_run(g.user_id, question_id, query)
    return jsonify(result)

@app.post('/api/save')
@authenticated
def save():
    question_id, query = payload()
    db.save_answer(g.user_id, question_id, query)
    return jsonify(saved=True)

@app.get('/api/health')
def health(): return jsonify(status='ok')

@app.post('/api/generate')
@authenticated
def generate_sql():
    value=request.get_json(silent=True) or {}
    question=value.get('question')
    question_id=value.get('question_id')
    execute=value.get('execute',False)
    if not isinstance(question,str) or not 5<=len(question.strip())<=1500:
        raise ValueError('Enter a natural-language question between 5 and 1,500 characters.')
    if type(question_id) is not int or question_id not in {q['id'] for q in QUESTIONS}:
        raise ValueError('Choose a valid quiz question for comparison.')
    if type(execute) is not bool:raise ValueError('Execute must be true or false.')
    if not os.getenv('AI_API_KEY') or not os.getenv('AI_MODEL'):
        return jsonify(error='AI generation is not configured. Contact the quiz owner.'),503
    if not db.reserve_ai_request(g.user_id):
        return jsonify(error='AI usage limit reached. Limit: 5 requests per minute, 30 per user per day, and a shared daily budget.'),429
    return jsonify(rag.pipeline(question.strip(),question_id,execute,g.user_id))

@app.errorhandler(rag.RAGError)
def ai_error(error):return jsonify(error=str(error)),502

@app.errorhandler(ValueError)
def bad_query(error): return jsonify(error=str(error)), 400

@app.errorhandler(psycopg.Error)
def database_error(error):
    # Do not return connection strings, credentials, or internal table details.
    if isinstance(error, psycopg.errors.QueryCanceled): message='Query exceeded the 3-second limit.'
    elif isinstance(error, (psycopg.ProgrammingError, psycopg.DataError)):
        message=error.diag.message_primary or 'Check the SQL syntax, columns, and table names.'
    else: message='Database is unavailable. Please try again shortly.'
    return jsonify(error=message), 400 if not isinstance(error, psycopg.OperationalError) else 503

if __name__ == '__main__': app.run(host='127.0.0.1', port=5050)
