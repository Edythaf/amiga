"""Tax math, immutable voucher output and independent batch task integration. No paid AI calls."""
import copy,json,unittest
from io import BytesIO
from decimal import Decimal
from unittest.mock import Mock
from sqlalchemy import select,func
from pypdf import PdfReader
import test_api
from backend.models import WorkRequest,Invoice,UploadBatch,RequestIntake,InvoiceTaxPlan,Review
from backend.processing import process_one
from backend.voucher_tax import defaults,calculate_tax,normalize_plan
from backend.validation import InvalidDraft,validate


class TaxBatchTests(unittest.TestCase):
    def setUp(self):
        self.a=test_api.ApiTests();self.a.setUp()
        self.files=[('one.pdf',test_api.pdf_bytes('one')),('two.pdf',test_api.pdf_bytes('two'))]
        self.evidence=test_api.pdf_bytes('bank evidence')
    def tearDown(self):self.a.tearDown()
    def ready(self):
        req=self.a.processed();self.a.take(req);return req
    def plan(self,req,**overrides):
        return {**defaults(req['invoices'][0]['fields']),'note':'Pemeriksaan pajak fixture oleh reviewer',**overrides}
    def save(self,req,plan,revision=0,actor='finance'):
        inv=req['invoices'][0]
        return self.a.call(actor,'PATCH',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher-tax",json={
            'expected_version':inv['current_version'],'expected_tax_revision':revision,'plan':plan,'acknowledged':True})
    def analyze(self,req):
        inv=req['invoices'][0]
        return self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher-tax/analyze",json={'expected_version':inv['current_version']})
    def batch(self,key='fixture-batch-key-0001',files=None,evidence=True,actor='owner',client='A'):
        return self.a.call(actor,'POST','/api/requests/batch',data={'client_id':client,'request_type':'Invoice vendor','channel':'Portal',
            'request_date':'2026-01-02','deadline':'2026-12-31','idempotency_key':key,
            'invoice_files[]':[(BytesIO(data),name) for name,data in (files or self.files)],
            'evidence_files[]':[(BytesIO(self.evidence),'bank.pdf')] if evidence else []})

    def test_tax_math_adds_missing_vat_deducts_pph_and_never_double_adds(self):
        f=test_api.invoice_fields();f['line_items'][0]['tax_amount']='0';f['total_amount']='1000000';f['subtotal']='1000000'
        p={**defaults(f),'vat_mode':'ADD','vat_rate':'11','vat_base':'1000000','withholding_mode':'DEDUCT','withholding_rate':'2','withholding_base':'1000000','note':'Fixture'}
        self.assertEqual(calculate_tax(f,normalize_plan(p))['net_payable'],'1090000.00')
        f['invoice_tax_amount']='110000';f['total_amount']='1110000'
        with self.assertRaises(InvalidDraft):calculate_tax(f,p)
        p['vat_mode']='KEEP';self.assertEqual(calculate_tax(f,p)['net_payable'],'1090000.00')
        p['vat_mode']='REPLACE';p['vat_rate']='12';self.assertEqual(calculate_tax(f,p)['net_payable'],'1100000.00')
        p['source_withholding']='20000'
        with self.assertRaises(InvalidDraft):calculate_tax(f,p)
        p['withholding_mode']='KEEP';self.assertEqual(calculate_tax(f,p)['withholding_adjustment'],'0')
        p['vat_rate']='100.1'
        with self.assertRaises(InvalidDraft):normalize_plan(p)

    def test_tax_save_keeps_source_and_confirmation_and_official_pdf_uses_net(self):
        req=self.ready();inv=req['invoices'][0];source=copy.deepcopy(inv['fields'])
        result=self.save(req,self.plan(req,withholding_mode='DEDUCT',withholding_kind='PPh 23 jasa',withholding_rate='2',withholding_base='100'))
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['data']['calculated']['net_payable'],'208.10')
        detail=self.a.actor('owner').get('/api/requests/'+req['id']).json['data']
        self.assertEqual(detail['invoices'][0]['fields'],source);self.assertTrue(detail['invoices'][0]['uploader_confirmation']['confirmed'])
        self.assertEqual(self.a.decision(req).status_code,409)
        response=self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/approve",json={'expected_version':1,'expected_tax_revision':1})
        self.assertEqual(response.status_code,200,response.json)
        pdf=self.a.call('company','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download",json={'expected_version':1})
        text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages)
        self.assertIn('Rp 208,10',text);self.assertIn('PPh 23 jasa',text)
        self.assertEqual(self.save(req,self.plan(req),revision=1).status_code,409)
        with self.a.app.extensions['amiga_db']() as db:
            review=db.scalar(select(Review).where(Review.invoice_id==inv['id']))
            self.assertEqual(review.validation_snapshot['voucher_tax']['calculated']['net_payable'],'208.10')

    def test_tax_reviewer_permissions_stale_edits_and_invalid_amounts(self):
        req=self.ready();p=self.plan(req)
        for actor,status in [('owner',403),('company',403),('admin',403),('finance2',404)]:self.assertEqual(self.save(req,p,actor=actor).status_code,status)
        self.assertEqual(self.save(req,p).status_code,200)
        self.assertEqual(self.save(req,{**p,'note':'Other tab'}).status_code,409)
        self.assertEqual(self.save(req,{**p,'vat_mode':'ADD','vat_rate':'11'},revision=1).status_code,422)
        self.assertEqual(self.save(req,{**p,'withholding_rate':'NaN'},revision=1).status_code,422)

    def test_tax_ai_chooses_catalog_rate_preserves_existing_tax_and_caches(self):
        req=self.ready()
        value={'vat_rule':'PPN_NON_LUXURY','vat_base':'100','withholding_rule':'PPH23_SERVICE','withholding_base':'100',
            'source_withholding':'0','withholding_in_total':False,'note':'Fixture: jasa badan, bukti subjek tersedia.', 'missing_facts':[], 'evidence':['Jasa fixture']}
        ai=Mock(return_value=value);self.a.app.config['TAX_ANALYZER']=ai
        result=self.analyze(req);self.assertEqual(result.status_code,200,result.json)
        plan=result.json['data'];self.assertEqual(plan['plan']['vat_mode'],'KEEP');self.assertEqual(plan['plan']['withholding_rate'],'2')
        self.assertEqual(plan['revision'],0);self.assertFalse(plan['applied'])
        self.assertEqual(self.analyze(req).status_code,200);ai.assert_called_once()
        self.assertEqual(self.save(req,{**plan['plan'],'note':'Reviewer has checked source'}).status_code,200)

    def test_tax_ai_missing_status_or_failure_does_not_invent_payable(self):
        req=self.ready()
        self.a.app.config['TAX_ANALYZER']=Mock(return_value={'vat_rule':'REVIEW','vat_base':'100','withholding_rule':'REVIEW','withholding_base':'100',
            'source_withholding':'0','withholding_in_total':False,'note':'NPWP/PKP belum diketahui.','missing_facts':['Status PKP'],'evidence':[]})
        result=self.analyze(req).json['data'];self.assertEqual(result['plan']['vat_mode'],'KEEP');self.assertEqual(result['plan']['withholding_mode'],'KEEP')
        self.assertEqual(result['calculated']['net_payable'],'210.10')

    def test_reviewer_corrects_ai_nominal_exactly_and_issued_pdf_stays_immutable(self):
        req=self.ready()
        self.a.app.config['TAX_ANALYZER']=Mock(return_value={'vat_rule':'NONE','vat_base':'100','withholding_rule':'PPH23_SERVICE','withholding_base':'100',
            'source_withholding':'0','withholding_in_total':False,'note':'Fixture AI proposal','missing_facts':[],'evidence':[]})
        proposal=self.analyze(req).json['data']['plan']
        plan={**proposal,'withholding_amount':'3.33','note':'Reviewer corrected AI suggestion'}
        result=self.save(req,plan);self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['data']['calculated']['net_payable'],'206.77')
        self.assertEqual(result.json['data']['plan']['withholding_amount'],'3.33')
        self.assertEqual(self.analyze(req).json['data']['plan']['withholding_amount'],'3.33')
        self.assertEqual(self.a.decision(req,expected_tax_revision=1).status_code,200)
        inv=req['invoices'][0]
        pdf=self.a.actor('finance').get(f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/preview.pdf")
        self.assertIn('Rp 206,77',' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages));pdf.close()
        self.assertEqual(self.save(req,{**plan,'withholding_amount':'1'},revision=1).status_code,409)

    def test_nominal_correction_invalid_negative_and_stale_revision_are_rejected(self):
        req=self.ready()
        for value in ['-1','abc','NaN','1000000']:
            self.assertEqual(self.save(req,self.plan(req,withholding_mode='DEDUCT',withholding_amount=value)).status_code,422)
        good=self.save(req,self.plan(req,withholding_mode='DEDUCT',withholding_amount='0'))
        self.assertEqual(good.status_code,200,good.json)
        self.assertEqual(good.json['data']['calculated']['net_payable'],'210.10')
        self.assertEqual(self.save(req,self.plan(req,withholding_mode='DEDUCT',withholding_amount='1')).status_code,409)

    def test_existing_source_pph_is_not_deducted_twice_and_can_be_corrected(self):
        f=test_api.invoice_fields();f['total_amount']='208.10'
        p={**defaults(f),'source_withholding':'2','withholding_mode':'KEEP','withholding_rate':'2','withholding_base':'100','note':'Sudah dipotong dalam PDF'}
        self.assertEqual(calculate_tax(f,p)['net_payable'],'208.10')
        checked=validate(f,1,1,tolerance='0.01',source_withholding='2')
        self.assertTrue(checked['valid'],checked)
        p['withholding_mode']='REPLACE';p['withholding_rate']='3'
        self.assertEqual(calculate_tax(f,p)['net_payable'],'207.10')

    def test_batch_files_are_atomic_idempotent_and_tenant_scoped(self):
        result=self.batch();self.assertEqual(result.status_code,201,result.json);items=result.json['data']['items'];self.assertEqual(len(items),2)
        again=self.batch();self.assertEqual({r['id'] for r in again.json['data']['items']},{r['id'] for r in items})
        self.assertEqual(self.batch(files=[('other.pdf',test_api.pdf_bytes('other'))]).status_code,409)
        self.assertEqual(self.batch(key='other-key-00000001',client='B').status_code,403)
        self.assertEqual(self.batch(key='other-key-00000002',actor='company').status_code,403)
        self.assertEqual(self.batch(key='other-key-00000003',files=[('good.pdf',test_api.pdf_bytes()),('bad.pdf',b'bad')]).status_code,422)
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UploadBatch)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(WorkRequest)),2)
        for item in items:process_one(self.a.app,item['id'])
        for item in items:
            detail=self.a.actor('owner').get('/api/requests/'+item['id']).json['data'];self.assertEqual(len(detail['invoices']),1)

    def test_multi_invoice_pdf_splits_one_task_per_invoice_and_distinct_reviewers_claim(self):
        self.a.rows=[test_api.invoice_fields('FIRST'),test_api.invoice_fields('SECOND')]
        result=self.batch(files=[('combined.pdf',test_api.pdf_bytes('two invoices'))]);root=result.json['data']['items'][0]
        process_one(self.a.app,root['id'])
        listing=self.a.actor('owner').get('/api/requests').json['data']['items'];self.assertEqual(len(listing),2)
        requests=[self.a.actor('owner').get('/api/requests/'+row['id']).json['data'] for row in listing]
        self.assertEqual({r['invoices'][0]['fields']['invoice_number'] for r in requests},{'FIRST','SECOND'})
        self.assertTrue(all(len(r['invoices'])==1 for r in requests))
        for r in requests:
            self.assertNotIn('DUPLICATE_FILE',[i['code'] for i in r['invoices'][0]['validation']['issues']])
            self.a.prepare_review(r)
        for req,actor in zip(requests,['finance','finance2']):
            response=self.a.call(actor,'POST','/api/tasks/'+req['id']+'/claim',json={});self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.a.actor('finance').get('/api/requests/'+requests[1]['id']).status_code,404)
        self.assertEqual(self.a.actor('finance2').get('/api/requests/'+requests[0]['id']).status_code,404)
        self.assertEqual(self.a.extractions,1)
        with self.a.app.extensions['amiga_db']() as db:self.assertEqual(db.scalar(select(func.count()).select_from(RequestIntake)),2)

    def test_browser_money_fixture_expected_values_match_decimal_server(self):
        from pathlib import Path
        for case in json.loads((Path(__file__).parents[1]/'fixtures/voucher_tax_math.json').read_text()):
            self.assertEqual(calculate_tax(case['fields'],case['plan']),case['expected'],case['name'])

    def test_batch_invalid_second_extraction_row_creates_no_partial_children(self):
        self.a.rows=[test_api.invoice_fields('FIRST'),{'invalid':'field'}]
        result=self.batch(files=[('combined.pdf',test_api.pdf_bytes())]);req=result.json['data']['items'][0]
        process_one(self.a.app,req['id'])
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(WorkRequest)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(Invoice)),0)
            self.assertEqual(db.get(WorkRequest,req['id']).processing_status,'FAILED')

    def test_manual_output_must_be_refreshed_after_tax_change(self):
        req=self.ready();inv=req['invoices'][0]
        result=self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/manual-pdf",data={
            'expected_version':1,'expected_previous_id':'','content_confirmed':'true','review_pdf':(BytesIO(test_api.pdf_bytes('Revised final, unsigned')),'final.pdf')})
        self.assertEqual(result.status_code,201,result.json)
        old=result.json['data']['id']
        self.assertEqual(self.save(req,self.plan(req,withholding_mode='DEDUCT',withholding_rate='2',withholding_base='100')).status_code,200)
        response=self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/approve",json={'expected_version':1,'expected_tax_revision':1})
        self.assertEqual(response.status_code,409);self.assertEqual(response.json['error']['code'],'MANUAL_TAX_STALE')
        pdf=test_api.pdf_bytes('Final after corrected taxes')
        result=self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/manual-pdf",data={
            'expected_version':1,'expected_previous_id':old,'content_confirmed':'true','review_pdf':(BytesIO(pdf),'final-corrected.pdf')})
        self.assertEqual(result.status_code,201,result.json)
        self.assertEqual(self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/approve",json={'expected_version':1,'expected_tax_revision':1}).status_code,200)
        downloaded=self.a.call('company','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download",json={'expected_version':1})
        self.assertEqual(downloaded.data,pdf)

    def test_ai_failure_is_sanitized_and_existing_manual_tax_is_preserved(self):
        req=self.ready();p=self.plan(req,withholding_mode='DEDUCT',withholding_rate='2',withholding_base='100')
        self.assertEqual(self.save(req,p).status_code,200)
        self.a.app.config['TAX_ANALYZER']=Mock(side_effect=RuntimeError('private provider credential'))
        result=self.analyze(req);self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['data']['ai_state'],'FAILED');self.assertEqual(result.json['data']['plan'],p)
        self.assertNotIn('private provider credential',result.get_data(as_text=True))
