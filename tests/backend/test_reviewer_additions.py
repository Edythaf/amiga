"""Reviewer additions without a new PDF; all records live in isolated fixtures."""
import copy, unittest
from io import BytesIO
from sqlalchemy import select, func
from pypdf import PdfReader
import test_api
from backend.models import Document, Extraction, Invoice, Voucher, Review, ManualReviewPDF
from backend.repository import fields_for
from backend.voucher_tax import defaults


class ReviewerAdditionTests(unittest.TestCase):
    def setUp(self):
        self.a=test_api.ApiTests();self.a.setUp()
    def tearDown(self):self.a.tearDown()
    def ready(self):
        req=self.a.processed(evidence=False);return self.a.take(req)

    def test_reviewer_adds_item_and_bank_without_new_pdf_and_publishes_result(self):
        req=self.ready();inv=req['invoices'][0];original=copy.deepcopy(inv['fields'])
        with self.a.app.extensions['amiga_db']() as db:raw=copy.deepcopy(db.scalar(select(Extraction)).payload)
        fields=copy.deepcopy(original)
        fields.update(bank_name='Bank Tambahan',account_number='000098765',account_holder='Penerima hasil review',due_date='2026-01-31',subtotal='270.20',total_amount='260.10')
        fields['line_items'].append(dict(description='Jasa tambahan tidak tercantum PDF',quantity='1',unit_price='50',discount_amount='0',tax_amount='0',line_total='50'))
        response=self.a.revise(req,account='finance',fields=fields,field_sources=inv['field_sources'],reason='Item dan rekening dilengkapi dari pemeriksaan reviewer, tanpa bukti PDF baru.')
        self.assertEqual(response.status_code,200,response.json);edited=response.json['data'];req['invoices'][0]=edited
        self.assertTrue(edited['validation']['valid'],edited['validation'])
        for key in ('bank_name','account_number','account_holder','due_date','subtotal','total_amount'):
            self.assertEqual(edited['field_sources'][key]['source_type'],'REVIEWER')
            self.assertIn('pemeriksaan reviewer',edited['field_sources'][key]['notes'])
        self.assertFalse(edited['uploader_confirmation']['confirmed'])
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Document)),1)
            self.assertEqual(db.scalar(select(Extraction)).payload,raw)
            self.assertEqual(fields_for(db,db.get(Invoice,inv['id']),1),original)
        # The existing version confirmation workflow stays intact, without any new file.
        result=self.a.decision(req,voucher_pdf_source='GENERATED');self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['data']['voucher_pdf_source'],'GENERATED')
        pdf=self.a.actor('company').get(f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/preview.pdf")
        text=' '.join(' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages).split())
        self.assertIn('Jasa tambahan tidak tercantum PDF',text);self.assertIn('000098765',text);pdf.close()

    def test_uploader_cannot_forge_reviewer_provenance_and_other_reviewer_cannot_edit(self):
        req=self.ready();inv=req['invoices'][0];fields=copy.deepcopy(inv['fields']);fields['account_number']='999'
        doc=next(d for d in req['documents'] if d['type']=='INVOICE')
        source={'account_number':{'document_id':doc['id'],'source_type':'REVIEWER','page':None,'notes':'Claimed reviewer input'}}
        forged=self.a.revise(req,fields=fields,field_sources=source)
        self.assertEqual(forged.status_code,403,forged.json)
        self.assertEqual(self.a.revise(req,fields=fields).status_code,422)
        self.assertEqual(self.a.revise(req,account='finance2',fields=fields,field_sources=source).status_code,404)
        self.assertEqual(self.a.revise(req,account='admin',fields=fields,field_sources=source).status_code,403)

    def test_reviewer_provenance_noop_preserves_version_and_foreign_source_rejected(self):
        req=self.ready();inv=req['invoices'][0];fields=copy.deepcopy(inv['fields']);fields['account_number']='555'
        result=self.a.revise(req,account='finance',fields=fields,field_sources={'account_number':None},reason='Rekening tambahan diperiksa manual')
        self.assertEqual(result.status_code,200,result.json);req['invoices'][0]=result.json['data'];version=result.json['data']['current_version']
        result=self.a.revise(req,account='finance',field_sources=req['invoices'][0]['field_sources'])
        self.assertEqual(result.status_code,200,result.json);self.assertFalse(result.json['data']['revision_created']);self.assertEqual(result.json['data']['current_version'],version)
        other=self.a.processed(content=test_api.pdf_bytes('other request'),evidence=False)
        source={'account_number':{'document_id':other['documents'][0]['id'],'source_type':'REVIEWER'}}
        self.assertEqual(self.a.revise(req,account='finance',field_sources=source).status_code,422)
        # A saved reviewer source cannot be reused to disguise an uploader's new bank value.
        fields=copy.deepcopy(req['invoices'][0]['fields']);fields['account_number']='666'
        self.assertEqual(self.a.revise(req,fields=fields,field_sources=req['invoices'][0]['field_sources']).status_code,403)

    def test_generated_voucher_after_tax_change_requires_explicit_choice_preserves_manual_pdf(self):
        req=self.ready();inv=req['invoices'][0];base=f"/api/requests/{req['id']}/invoices/{inv['id']}"
        manual=test_api.pdf_bytes('Original manual final')
        upload=self.a.call('finance','POST',base+'/manual-pdf',data={'expected_version':inv['current_version'],'expected_previous_id':'','content_confirmed':'true','review_pdf':(BytesIO(manual),'final.pdf')})
        self.assertEqual(upload.status_code,201,upload.json)
        plan={**defaults(inv['fields']),'withholding_mode':'DEDUCT','withholding_rate':'2','withholding_base':'100','note':'PPh tambahan hasil pemeriksaan'}
        tax=self.a.call('finance','PATCH',base+'/voucher-tax',json={'expected_version':inv['current_version'],'expected_tax_revision':0,'acknowledged':True,'plan':plan})
        self.assertEqual(tax.status_code,200,tax.json)
        data={'expected_version':inv['current_version'],'expected_tax_revision':1}
        self.assertEqual(self.a.call('finance','POST',base+'/approve',json=data).status_code,409)
        self.assertEqual(self.a.call('finance','POST',base+'/approve',json={**data,'voucher_pdf_source':'UNKNOWN'}).status_code,422)
        done=self.a.call('finance','POST',base+'/approve',json={**data,'voucher_pdf_source':'GENERATED'})
        self.assertEqual(done.status_code,200,done.json);self.assertEqual(done.json['data']['voucher_pdf_source'],'GENERATED')
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(bytes(db.get(ManualReviewPDF,upload.json['data']['id']).pdf),manual)
            voucher=db.scalar(select(Voucher));self.assertNotEqual(bytes(voucher.pdf),manual)
            review=db.get(Review,voucher.review_id);self.assertEqual(review.validation_snapshot['voucher_pdf_source'],'GENERATED')
            self.assertIsNone(review.validation_snapshot['manual_pdf_id'])
            self.assertIn('Rp 208,10',' '.join(p.extract_text() for p in PdfReader(BytesIO(voucher.pdf)).pages))


if __name__=='__main__':unittest.main()
