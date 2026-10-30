"""Explicit owner-only setup and live CI checks; never prints credentials."""
import sys
from pathlib import Path
import db
from quiz import QUESTIONS

def check():
    for q in QUESTIONS:
        actual=db.run_query(q['sql'])
        assert actual['columns']==q['columns'], f"Question {q['id']} column mismatch"
        assert actual['rows']==q['rows'], f"Question {q['id']} result mismatch: {actual['rows']}"
    with db.connect() as conn:
        row=conn.execute("SELECT has_table_privilege('cafe_quiz_reader','quiz_private.audit_log','UPDATE'), has_table_privilege('cafe_quiz_reader','quiz_private.audit_log','DELETE'), has_table_privilege('cafe_quiz_reader','quiz_private.audit_log','INSERT')").fetchone()
        assert row == (False,False,False), 'Taker role can edit audit log'
        assert conn.pgconn.ssl_in_use, 'Python connection is not using TLS'
    print('PASS: all five live answers; audit permissions; encrypted PostgreSQL connection.')

if __name__=='__main__':
    if sys.argv[1:] == ['setup']:
        with db.connect() as conn:
            conn.execute(Path(__file__).with_name('sql').joinpath('setup.sql').read_text())
        print('Quiz schemas and fictional data installed.')
    elif sys.argv[1:] == ['check']: check()
    elif sys.argv[1:] == ['rag-setup']:
        with db.connect() as conn:
            conn.execute(Path(__file__).with_name('sql').joinpath('rag.sql').read_text())
        print('RAG usage limits installed.')
    elif sys.argv[1:] == ['rag-check']:
        import rag
        for q in QUESTIONS:
            sources,count=rag.retrieve(q['prompt'])
            assert sources and count>=9
            assert any(s['id']==f'example-{q["id"]}' for s in sources), f'Question {q["id"]} example not retrieved'
            print('PASS Chroma retrieval:',q['title'],[s['id'] for s in sources])
    else: raise SystemExit('Usage: python manage.py setup|check|rag-setup|rag-check')
