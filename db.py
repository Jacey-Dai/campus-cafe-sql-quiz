import json
import os
from pathlib import Path
from decimal import Decimal
import psycopg
from dotenv import load_dotenv
from pglast import parser

load_dotenv(Path(__file__).with_name('.env'))
TABLES = {'customers', 'orders', 'menu_items', 'order_items'}
FUNCTIONS = {'count', 'sum', 'avg', 'min', 'max', 'round', 'lower', 'upper', 'length', 'date_trunc', 'abs'}
NODES = {'SelectStmt', 'ResTarget', 'ColumnRef', 'String', 'Integer', 'Float', 'Boolean',
         'A_Const', 'A_Expr', 'BoolExpr', 'NullTest', 'BooleanTest', 'JoinExpr', 'RangeVar',
         'FuncCall', 'SortBy', 'A_Star', 'SubLink', 'TypeCast', 'TypeName',
         'CoalesceExpr', 'CaseExpr', 'CaseWhen', 'MinMaxExpr', 'RangeSubselect', 'Alias',
         'WithClause', 'CommonTableExpr', 'WindowDef', 'GroupingSet'}

def connect():
    # The session pooler is explicitly required by the assignment.
    return psycopg.connect(host=os.environ['PGHOST'], port=int(os.getenv('PGPORT', '5432')),
        dbname=os.getenv('PGDATABASE', 'postgres'), user=os.environ['PGUSER'],
        password=os.environ['PGPASSWORD'], sslmode='require', connect_timeout=10,
        prepare_threshold=None)

def validate_query(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 12000:
        raise ValueError('Enter a SELECT query of at most 12,000 characters.')
    try:
        parsed = json.loads(parser.parse_sql_json(query))
    except Exception:
        raise ValueError('SQL could not be parsed. Check your syntax.') from None
    statements = parsed.get('stmts', [])
    if len(statements) != 1 or 'SelectStmt' not in statements[0]['stmt']:
        raise ValueError('Run exactly one SELECT statement.')
    ctes = set()
    def collect(value):
        if isinstance(value, dict):
            if 'CommonTableExpr' in value:
                ctes.add(value['CommonTableExpr']['ctename'])
            for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    collect(statements[0]['stmt'])
    def walk(value):
        if isinstance(value, dict):
            for tag, node in value.items():
                if tag[0].isupper() and tag not in NODES:
                    raise ValueError('Only read-only quiz SELECT expressions are supported.')
                if tag == 'SelectStmt' and (node.get('intoClause') or node.get('lockingClause')):
                    raise ValueError('SELECT INTO and row locks are not allowed.')
                if tag == 'RangeVar':
                    schema, table = node.get('schemaname'), node['relname']
                    if node.get('catalogname') or schema not in (None, 'quiz_data') or (table not in TABLES and not (schema is None and table in ctes)):
                        raise ValueError('You may query only the four quiz_data tables.')
                if tag == 'FuncCall':
                    names = [x['String']['sval'] for x in node['funcname']]
                    if len(names) > 2 or names[-1] not in FUNCTIONS or (len(names) == 2 and names[0] != 'pg_catalog'):
                        raise ValueError('This function is not available in the quiz sandbox.')
                if tag in ('TypeName', 'typeName'):
                    names = [x['String']['sval'] for x in node.get('names', [])]
                    if not names or names[-1] not in {'int2','int4','int8','numeric','text','varchar','date','timestamp','timestamptz','float4','float8','bool'} or (len(names)>1 and names[:-1] != ['pg_catalog']):
                        raise ValueError('Use a standard numeric, text, boolean, or date type.')
                if tag == 'A_Expr':
                    names = [x['String']['sval'] for x in node.get('name', [])]
                    if len(names) != 1 or names[0] not in {'=','<>','!=','<','>','<=','>=','+','-','*','/','%','~~','!~~','~~*','!~~*','||'}:
                        raise ValueError('This operator is not supported.')
                walk(node)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(statements[0]['stmt'])
    return query.strip().rstrip(';')

def cell(value):
    if isinstance(value, Decimal): return str(value)
    if hasattr(value, 'isoformat'): return value.isoformat()
    return value

def run_query(query):
    query = validate_query(query)
    with connect() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute('SET LOCAL ROLE cafe_quiz_reader')
            cur.execute('SET LOCAL search_path = pg_catalog, quiz_data')
            cur.execute("SET LOCAL statement_timeout = '3000ms'")
            cur.execute("SET LOCAL lock_timeout = '1000ms'")
            # Extended protocol rejects multi-statement execution as a second guard.
            cur.execute(query, prepare=True)
            columns = [c.name for c in cur.description]
            rows = cur.fetchmany(201)
            return {'columns': columns, 'rows': [[cell(v) for v in row] for row in rows[:200]], 'truncated': len(rows)>200}

def save_answer(user_id, question_id, query):
    with connect() as conn:
        conn.execute('INSERT INTO quiz_private.answers(user_id,question_id,query) VALUES (%s,%s,%s) ON CONFLICT (user_id,question_id) DO UPDATE SET query=EXCLUDED.query, updated_at=now()', (user_id, question_id, query))
        conn.execute("INSERT INTO quiz_private.audit_log(user_id,action,question_id,query) VALUES (%s,'save',%s,%s)", (user_id, question_id, query))

def audit_run(user_id, question_id, query):
    with connect() as conn:
        conn.execute("INSERT INTO quiz_private.audit_log(user_id,action,question_id,query) VALUES (%s,'run',%s,%s)", (user_id, question_id, query))

def answers(user_id):
    with connect() as conn:
        rows = conn.execute('SELECT question_id,query FROM quiz_private.answers WHERE user_id=%s', (user_id,)).fetchall()
        return {str(q): sql for q, sql in rows}

def reserve_ai_request(user_id):
    with connect() as conn:
        # Serialize quota reservations so concurrent requests cannot overspend it.
        conn.execute('SELECT pg_advisory_xact_lock(83170608)')
        total,user_day,user_min=conn.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE user_id=%s), COUNT(*) FILTER (WHERE user_id=%s AND created_at>now()-interval '1 minute') FROM quiz_private.rag_requests WHERE created_at>now()-interval '24 hours'",(user_id,user_id)).fetchone()
        if total>=int(os.getenv('AI_DAILY_LIMIT','100')) or user_day>=30 or user_min>=5:
            return False
        conn.execute('INSERT INTO quiz_private.rag_requests(user_id) VALUES (%s)',(user_id,))
        return True
