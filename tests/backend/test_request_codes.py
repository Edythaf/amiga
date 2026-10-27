"""Readable codes keep stable request UUIDs, company boundaries and counters."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,text,delete
import test_api
from backend.app import create_app
from backend.models import Client,CompanyNumber,RequestNumber,WorkRequest,Setting
from backend.request_numbers import assign_request_number


class RequestCodeTests(unittest.TestCase):
    def setUp(self):self.a=test_api.ApiTests();self.a.setUp()
    def tearDown(self):self.a.tearDown()

    def test_same_company_names_have_distinct_company_ids_and_sequences(self):
        with self.a.app.extensions['amiga_db'].begin() as db:
            for key in ['A','B']:db.get(Client,key).name='PT Maju'
        first=self.a.upload();second=self.a.upload();other=self.a.upload(account='other',client_id='B')
        self.assertEqual(first['request_code'],'REQ-20260101-0001-PT-MAJU-0001')
        self.assertEqual(second['request_code'],'REQ-20260101-0001-PT-MAJU-0002')
        self.assertEqual(other['request_code'],'REQ-20260101-0002-PT-MAJU-0001')
        self.assertTrue(first['id'].startswith('req_'))
        with self.a.app.extensions['amiga_db'].begin() as db:db.get(Client,'A').name='Nama baru'
        detail=self.a.actor('owner').get('/api/requests/'+first['request_code']).json['data']
        self.assertEqual(detail['request_code'],first['request_code']);self.assertEqual(detail['id'],first['id'])
        self.assertEqual(self.a.actor('other').get('/api/requests/'+first['request_code']).status_code,404)
        found=self.a.actor('owner').get('/api/requests',query_string={'search':first['request_code']}).json['data']
        self.assertEqual([r['id'] for r in found['items']],[first['id']])
        history=self.a.actor('owner').get('/api/agents/history',query_string={'request_id':first['request_code']})
        self.assertEqual(history.status_code,200,history.json)
        self.assertEqual(self.a.actor('other').get('/api/agents/history',query_string={'request_id':first['request_code']}).status_code,404)

    def test_backfill_on_restart_preserves_uuid_and_links_and_is_idempotent(self):
        req=self.a.processed();document_ids=[d['id'] for d in req['documents']]
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.execute(delete(RequestNumber));db.execute(delete(CompanyNumber))
            db.get(Setting,'schema_version').value='6'
        options={k:self.a.app.config[k] for k in ['TESTING','START_QUEUE_WORKER','SECRET_KEY','DATABASE_URL','UPLOAD_DIR','AUTH_METHOD','AI_PROVIDER','OPENAI_API_KEY','GOOGLE_CLIENT_ID','TOKEN_VERIFIER','EXTRACTOR']}
        restarted=create_app(options)
        try:
            with restarted.extensions['amiga_db'].begin() as db:
                row=db.get(RequestNumber,req['id']);code=row.code
                self.assertEqual(assign_request_number(db,db.get(WorkRequest,req['id'])).code,code)
                self.assertEqual(db.get(Setting,'schema_version').value,'8')
            detail=self.a.actor('owner').get('/api/requests/'+req['id']).json['data']
            self.assertEqual([d['id'] for d in detail['documents']],document_ids)
            self.assertEqual(detail['invoices'][0]['id'],req['invoices'][0]['id'])
        finally:restarted.extensions['amiga_engine'].dispose()

    def test_concurrent_allocation_and_rollback_do_not_duplicate_codes(self):
        # Unnumbered rows simulate legacy imports; every writer serializes exactly
        # as the real SQLite API does, with no live application database access.
        first=self.a.upload();second=self.a.upload()
        with self.a.app.extensions['amiga_db'].begin() as db:db.execute(delete(RequestNumber))
        def allocate(identifier):
            with self.a.app.extensions['amiga_db'].begin() as db:
                db.execute(text('BEGIN IMMEDIATE'))
                return assign_request_number(db,db.get(WorkRequest,identifier)).code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(allocate,[first['id'],second['id']]))
        self.assertEqual(len(set(codes)),2)
        self.assertEqual(allocate(first['id']),codes[0])
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.execute(delete(RequestNumber).where(RequestNumber.request_id==first['id']))
            next_number=db.get(CompanyNumber,'A').next_request
        with self.assertRaises(RuntimeError):
            with self.a.app.extensions['amiga_db'].begin() as db:
                assign_request_number(db,db.get(WorkRequest,first['id']))
                raise RuntimeError('Rollback fixture')
        with self.a.app.extensions['amiga_db']() as db:
            self.assertIsNone(db.get(RequestNumber,first['id']))
            self.assertEqual(db.get(CompanyNumber,'A').next_request,next_number)


if __name__=='__main__':unittest.main()
