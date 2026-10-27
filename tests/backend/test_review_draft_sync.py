"""Atomic edits + tax plan: no lost draft or partial save. Isolated database only."""
import copy,unittest
from io import BytesIO
from sqlalchemy import select,func
from pypdf import PdfReader
import test_api
from backend.models import Invoice,InvoiceVersion,InvoiceTaxPlan,Audit
from backend.repository import fields_for
from backend.voucher_tax import defaults

class ReviewDraftSyncTests(unittest.TestCase):
    def setUp(self):self.a=test_api.ApiTests();self.a.setUp()
    def tearDown(self):self.a.tearDown()
    def ready(self):return self.a.take(self.a.processed(evidence=False))
    def payload(self,req):
        inv=req['invoices'][0]
        return {'expected_version':inv['current_version'],'expected_tax_revision':0,'acknowledged':True,'plan':{**defaults(inv['fields']),'withholding_mode':'DEDUCT','withholding_rate':'13','withholding_base':'100','note':'Pajak dan koreksi hasil pemeriksaan fixture'}}
    def save(self,req,payload,actor='finance'):
        return self.a.call(actor,'PATCH',f"/api/requests/{req['id']}/invoices/{req['invoices'][0]['id']}/review-draft",json=payload)
    def changed(self,req):
        f=copy.deepcopy(req['invoices'][0]['fields']);f['line_items'][0].update(quantity='3',line_total='320.30');f.update(subtotal='320.30',total_amount='310.20')
        return {'fields':f,'field_sources':req['invoices'][0]['field_sources'],'item_count_confirmed':True,'reason':'Koreksi jumlah dari pemeriksaan reviewer'}

    def test_invoice_and_tax_save_together_preview_and_official_use_same_net(self):
        req=self.ready();inv=req['invoices'][0];data={**self.payload(req),'invoice':self.changed(req)}
        result=self.save(req,data);self.assertEqual(result.status_code,200,result.json);saved=result.json['data']
        self.assertTrue(saved['revision_created']);self.assertEqual(saved['invoice']['current_version'],2)
        self.assertEqual(saved['voucher_tax']['calculated']['net_payable'],'297.20');self.assertEqual(saved['voucher_tax']['revision'],1)
        req['invoices'][0]=saved['invoice']
        with self.a.app.extensions['amiga_db']() as db:
            invoice=db.get(Invoice,inv['id']);self.assertEqual(fields_for(db,invoice)['total_amount'],'310.20')
            self.assertEqual(fields_for(db,invoice,1)['total_amount'],'210.10')
            self.assertEqual(db.get(InvoiceTaxPlan,(inv['id'],2)).withholding_rate,'13')
        url=f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/preview.pdf"
        pdf=self.a.actor('finance').get(url);self.assertIn('Rp 297,20',' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages));pdf.close()
        approved=self.a.decision(req,expected_tax_revision=1);self.assertEqual(approved.status_code,200,approved.json)
        pdf=self.a.actor('company').get(url);self.assertIn('Rp 297,20',' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages));pdf.close()

    def test_invalid_tax_rolls_back_invoice_revision_and_audit(self):
        req=self.ready();inv=req['invoices'][0];data={**self.payload(req),'invoice':self.changed(req)};data['plan']['withholding_rate']='101'
        with self.a.app.extensions['amiga_db']() as db:before=db.scalar(select(func.count()).select_from(Audit))
        result=self.save(req,data);self.assertEqual(result.status_code,422,result.json)
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.get(Invoice,inv['id']).current_version,1)
            self.assertIsNone(db.get(InvoiceVersion,(inv['id'],2)))
            self.assertIsNone(db.get(InvoiceTaxPlan,(inv['id'],2)))
            self.assertEqual(db.scalar(select(func.count()).select_from(Audit)),before)

    def test_tax_only_save_preserves_version_and_enforces_stale_input_and_permissions(self):
        req=self.ready();data=self.payload(req)
        for actor,expected in [('owner',403),('admin',403),('finance2',404),('other',404)]:self.assertEqual(self.save(req,data,actor).status_code,expected,actor)
        self.assertEqual(self.save(req,{**data,'acknowledged':False}).status_code,422)
        result=self.save(req,data);self.assertEqual(result.status_code,200,result.json)
        self.assertFalse(result.json['data']['revision_created']);self.assertEqual(result.json['data']['invoice']['current_version'],1)
        self.assertEqual(result.json['data']['voucher_tax']['calculated']['net_payable'],'197.10')
        self.assertEqual(self.save(req,data).status_code,409)
        self.assertEqual(self.save(req,{**data,'expected_tax_revision':1,'expected_version':0}).status_code,409)
        same=self.save(req,{**data,'expected_tax_revision':1});self.assertEqual(same.status_code,200,same.json)
        self.assertEqual(same.json['data']['voucher_tax']['revision'],1)

if __name__=='__main__':unittest.main()
