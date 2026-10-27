"""Real source-backed document/HTTP/PDF integration; cloud calls stay mocked."""
from io import BytesIO
from pathlib import Path
from decimal import Decimal
import json
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select
import test_api
from backend.models import Document, Extraction
from backend.modules.upload import service
from backend.modules.upload.portal_adapter import from_source_invoice, extract_for_portal, SOURCE_ID
from backend.processing import process_one


class PrimaryBackendTests(unittest.TestCase):
    def setUp(self):
        self.a=test_api.ApiTests()
        self.a.setUp()

    def tearDown(self):
        self.a.tearDown()

    def image_upload(self, content=None, filename='invoice.png', actor='owner', client='A'):
        if content is None:
            output=BytesIO()
            Image.new('RGB',(300,500),'white').save(output,format='PNG')
            content=output.getvalue()
        response=self.a.call(actor,'POST','/api/requests',data={
            'client_id':client,'request_type':'Invoice vendor','channel':'Portal',
            'request_date':'2026-10-16','deadline':'2026-10-20',
            'invoice_file':(BytesIO(content),filename)})
        return response,content

    def test_supplied_layout_owns_live_auth_admin_upload_and_worker(self):
        for endpoint, module in [('api.local_login','auth'),('api.update_user','admin'),('api.upload','upload')]:
            self.assertEqual(self.a.app.view_functions[endpoint].__module__,'backend.modules.'+module+'.routes')
        self.assertEqual(process_one.__module__,'backend.modules.upload.queue_worker')
        self.assertEqual(self.a.app.test_client().get('/health').json['backend_source'],SOURCE_ID)
        for path in ['/queue/data','/upload','/source/login','/backend/.env.source','/backend/storage/queue.sqlite3']:
            self.assertEqual(self.a.actor('owner').get(path).status_code,404)

    def test_image_converts_to_pdf_original_kept_and_tenant_boundary_preserved(self):
        response,original=self.image_upload()
        self.assertEqual(response.status_code,201,response.json)
        req=response.json['data']
        docs=req['documents']
        self.assertEqual({d['type'] for d in docs},{'INVOICE','SOURCE_IMAGE'})
        source=next(d for d in docs if d['type']=='SOURCE_IMAGE')
        pdf=next(d for d in docs if d['type']=='INVOICE')
        client=self.a.actor('owner')
        with client.get(source['download_url']) as response:
            self.assertEqual(response.data,original)
        with client.get(pdf['download_url']) as response:
            content=response.data
        self.assertTrue(content.startswith(b'%PDF-'))
        self.assertEqual(len(PdfReader(BytesIO(content)).pages),1)
        for doc in docs:self.assertEqual(self.a.actor('other').get(doc['download_url']).status_code,404)
        self.assertTrue(process_one(self.a.app,req['id']))
        detail=client.get('/api/requests/'+req['id']).json['data']
        self.assertEqual(len(detail['invoices']),1)
        self.assertEqual(self.a.revise(detail).status_code,200)
        fresh=client.get('/api/requests/'+req['id']).json['data']
        self.a.take(fresh)
        self.assertEqual(self.a.decision(fresh).status_code,200)
        invoice=fresh['invoices'][0]
        voucher=client.get(f"/api/requests/{req['id']}/invoices/{invoice['id']}/voucher/preview.pdf")
        text=''.join(p.extract_text() for p in PdfReader(BytesIO(voucher.data)).pages)
        self.assertIn('Peruntukan',text)  # supplied primary voucher layout
        self.assertIn('Diskon invoice',text)
        self.assertIn('0000123',text)
        self.assertNotIn('DRAFT',text)

    def test_same_photo_conversion_is_deterministic_and_duplicate_detected(self):
        first,original=self.image_upload()
        second,_=self.image_upload(original)
        self.assertEqual(first.status_code,201)
        self.assertEqual(second.status_code,201)
        with self.a.app.extensions['amiga_db']() as db:
            rows=list(db.scalars(select(Document).where(Document.type=='INVOICE')))
            self.assertEqual(rows[0].sha256,rows[1].sha256)
        for response in [first,second]:process_one(self.a.app,response.json['data']['id'])
        detail=self.a.actor('owner').get('/api/requests/'+second.json['data']['id']).json['data']
        self.assertIn('DUPLICATE_FILE',[i['code'] for i in detail['invoices'][0]['validation']['issues']])

    def test_invalid_image_fails_without_request_or_orphan_files(self):
        response,_=self.image_upload(b'not a picture')
        self.assertEqual(response.status_code,422)
        self.assertEqual(list((self.a.path/'documents').iterdir()),[])
        self.assertEqual(self.a.actor('owner').get('/api/requests').json['data']['total'],0)

    def test_image_content_must_match_filename_format(self):
        output=BytesIO();Image.new('RGB',(20,20)).save(output,'PNG')
        response,_=self.image_upload(output.getvalue(),filename='invoice.jpg')
        self.assertEqual(response.status_code,422)

    def test_jpeg_and_webp_supported_by_primary_inspector(self):
        for image_format,suffix in [('JPEG','jpg'),('WEBP','webp')]:
            output=BytesIO();Image.new('RGB',(20,20),'white').save(output,image_format)
            response,_=self.image_upload(output.getvalue(),filename='invoice.'+suffix)
            self.assertEqual(response.status_code,201,response.json)

    def test_source_json_preserves_decimal_precision_and_unknown_amounts(self):
        parsed=service.parse_invoice_json('```json\n{"supplier_name":"Vendor", "total_amount":123456789012345678.123456,"line_items":[]}\n```')
        fields=from_source_invoice(parsed)
        self.assertEqual(fields['total_amount'],'123456789012345678.123456')
        self.assertIsNone(fields['invoice_discount_amount'])
        self.assertEqual(fields['vendor_name'],'Vendor')

    def test_bedrock_primary_pipeline_mixed_pdf_requests_ocr_and_maps_source_names(self):
        path=self.a.path/'mixed.pdf'
        path.write_bytes(test_api.pdf_bytes('Invoice',pages=2))
        source={'supplier_name':'Fiktif','supplier_bank_account_number':'0000123',
                'total_amount':Decimal('100.25'),'line_items':[]}
        def ocr(path,kind,target,*args):
            target.write_text('OCR fixture',encoding='utf-8')
            return {'status':'OCR_EXTRACTED'}
        with patch.object(service,'extract_pdf_text',return_value={'status':'OCR_REQUIRED'}), \
             patch.object(service,'extract_document_with_bedrock',side_effect=ocr) as read, \
             patch.object(service,'extract_invoice_data_with_bedrock',return_value={'invoices':[source]}):
            result=extract_for_portal(path,{**self.a.app.config,'AI_PROVIDER':'bedrock','BEDROCK_MODEL_ID':'fixture'})
        read.assert_called_once()
        self.assertEqual(result['source_backend'],SOURCE_ID)
        self.assertEqual(result['invoices'][0]['account_number'],'0000123')
        self.assertEqual(result['source_invoices'][0]['total_amount'],'100.25')
        json.dumps(result)  # immutable raw result must be persistable without floats/Decimal objects

    def test_text_on_other_page_does_not_hide_a_scanned_page(self):
        import pymupdf
        path=self.a.path/'mixed.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40,40),'Invoice with text that is definitely longer than thirty characters')
            pdf.new_page()
            pdf.save(path)
        result=service.extract_pdf_text(path,self.a.path/'text.txt')
        self.assertEqual(result['status'],'OCR_REQUIRED')

    def test_truncated_cloud_response_never_publishes_partial_rows(self):
        client=Mock()
        client.converse.return_value={'stopReason':'max_tokens','output':{'message':{'content':[{'text':'{"invoices":[]}'}]}}}
        with patch.object(service.boto3,'client',return_value=client), self.assertRaisesRegex(service.OcrError,'EXTRACTION_TRUNCATED'):
            service.extract_invoice_data_with_bedrock('fixture','fixture','fixture')

    def test_bedrock_failure_keeps_actionable_code_without_publishing_invoice(self):
        req=self.a.upload()
        self.a.app.config['EXTRACTOR']=Mock(side_effect=service.OcrError('BEDROCK_ACCESS_DENIED'))
        process_one(self.a.app,req['id'])
        detail=self.a.actor('owner').get('/api/requests/'+req['id']).json['data']
        self.assertEqual(detail['processing']['error_code'],'BEDROCK_ACCESS_DENIED')
        self.assertEqual(detail['status'],'EXCEPTION')
        self.assertEqual(detail['work_status'],'EXTRACTION_FAILED')
        self.assertEqual(detail['invoices'],[])
