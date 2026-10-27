"""Nova transport/pipeline regressions. No real AWS calls or credentials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
from backend.modules.upload import service
from backend.modules.upload.portal_adapter import extract_for_portal, to_source_invoice
from backend.validation import normalize, validate
from test_api import invoice_fields, pdf_bytes

MODEL='apac.amazon.nova-lite-v1:0'

def response(text,stop='end_turn'):
    return {'stopReason':stop,'output':{'message':{'content':[{'text':text}]}}}


class BedrockExtractorTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'.runtime-temp'
        root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.path=Path(self.temp.name)
        self.source=to_source_invoice(invoice_fields())

    def tearDown(self):
        self.temp.cleanup()

    def test_text_pdf_maps_all_invoices_without_openai_or_ocr_and_uses_nova_limit(self):
        path=self.path/'invoice.pdf'
        path.write_bytes(pdf_bytes('Fictional invoice with enough text to avoid an unnecessary OCR call.'))
        other=copy.deepcopy(self.source);other['invoice_number']='INV-B'
        client=Mock();client.converse.return_value=response(json.dumps({'invoices':[self.source,other]}))
        with patch.object(service.boto3,'client',return_value=client),patch('backend.openai_extractor.extract_pdf') as openai:
            result=extract_for_portal(path,{'AI_PROVIDER':'bedrock','BEDROCK_MODEL_ID':MODEL,'AWS_REGION':'ap-southeast-1'})
        openai.assert_not_called()
        client.converse.assert_called_once()
        self.assertEqual(client.converse.call_args.kwargs['inferenceConfig']['maxTokens'],5000)
        self.assertEqual([normalize(i)['invoice_number'] for i in result['invoices']],['INV-A','INV-B'])
        self.assertEqual(result['invoices'][0]['account_number'],'0000123')
        self.assertEqual(result['provider'],'bedrock')
        json.dumps(result)

    def test_invoice_tax_zero_and_unknown_remain_distinct_through_pipeline(self):
        path=self.path/'invoice.pdf'
        path.write_bytes(pdf_bytes('Fictional invoice with explicit zero tax or unknown invoice tax.'))
        for tax in (0, '0', None):
            source=copy.deepcopy(self.source);source['tax_amount']=tax
            client=Mock();client.converse.return_value=response(json.dumps({'invoices':[source]}))
            with self.subTest(tax=tax),patch.object(service.boto3,'client',return_value=client):
                result=extract_for_portal(path,{'AI_PROVIDER':'bedrock','BEDROCK_MODEL_ID':MODEL,'AWS_REGION':'ap-southeast-1'})
                fields=normalize(result['invoices'][0])
                self.assertEqual(fields['invoice_tax_amount'],None if tax is None else '0')
                codes=[issue['code'] for issue in validate(fields,1,len(fields['line_items']))['issues']]
                self.assertEqual('UNKNOWN_INVOICE_AMOUNT' in codes,tax is None)

    def test_scanned_pages_are_separate_requests_and_no_partial_ocr_file_is_published(self):
        path=self.path/'scan.pdf';path.write_bytes(pdf_bytes('',pages=2))
        target=self.path/'ocr.txt'
        client=Mock();client.converse.side_effect=[response('--- Halaman 1 ---\nInvoice'),response('partial','max_tokens')]
        with patch.object(service.boto3,'client',return_value=client),self.assertRaisesRegex(service.OcrError,'^EXTRACTION_TRUNCATED$'):
            service.extract_document_with_bedrock(path,'PDF',target,MODEL,'ap-southeast-1')
        self.assertFalse(target.exists())
        self.assertEqual(client.converse.call_count,2)
        for call in client.converse.call_args_list:
            self.assertEqual(sum('image' in b for b in call.kwargs['messages'][0]['content']),1)

    def test_malformed_outer_json_cannot_salvage_an_inner_invoice(self):
        invalid=['{"invoices":[{"invoice_number":"A","line_items":[]}',
                 '{"invoices":[]} trailing','{"invoices":[],"invoices":[{}]}',
                 '{"total_amount":NaN}','{"total_amount":Infinity}','[]']
        for text in invalid:
            with self.subTest(text=text),self.assertRaisesRegex(service.OcrError,'^EXTRACTION_INVALID_OUTPUT$'):
                service.parse_invoice_json(text)

    def test_filtered_tool_or_incomplete_responses_are_never_accepted(self):
        for stop,code in [('max_tokens','EXTRACTION_TRUNCATED'),('content_filtered','EXTRACTION_REFUSED'),
                          ('guardrail_intervened','EXTRACTION_REFUSED'),('tool_use','EXTRACTION_INVALID_OUTPUT'),(None,'EXTRACTION_INVALID_OUTPUT')]:
            client=Mock();client.converse.return_value=response(json.dumps({'invoices':[self.source]}),stop)
            with self.subTest(stop=stop),patch.object(service.boto3,'client',return_value=client),self.assertRaisesRegex(service.OcrError,'^'+code+'$'):
                service.extract_invoice_data_with_bedrock('fixture',MODEL,'ap-southeast-1')

    def test_cloud_errors_are_sanitized_and_never_retried_or_fallback(self):
        cases=[(NoCredentialsError(),'BEDROCK_AUTH_FAILED'),
               (EndpointConnectionError(endpoint_url='https://fictional.invalid/private'),'BEDROCK_UNAVAILABLE')]
        for aws,code in [('AccessDeniedException','BEDROCK_ACCESS_DENIED'),('ExpiredTokenException','BEDROCK_AUTH_FAILED'),
                         ('ThrottlingException','BEDROCK_QUOTA_LIMIT'),('ValidationException','BEDROCK_INVALID_REQUEST'),
                         ('ResourceNotFoundException','BEDROCK_MODEL_UNAVAILABLE')]:
            cases.append((ClientError({'Error':{'Code':aws,'Message':'PRIVATE_SECRET_MUST_NOT_LEAK'}},'Converse'),code))
        for error,code in cases:
            client=Mock();client.converse.side_effect=error
            with self.subTest(code=code),patch.object(service.boto3,'client',return_value=client),self.assertRaisesRegex(service.OcrError,'^'+code+'$'):
                service.extract_invoice_data_with_bedrock('fixture',MODEL,'ap-southeast-1')
            client.converse.assert_called_once()

    def test_invalid_invoice_container_and_items_are_not_silently_replaced(self):
        bad=[{}, {'invoices':None}, {'invoices':[{}]}, {'invoices':[{'supplier_name':'A','line_items':'missing'}]},
             {'invoices':[{'supplier_name':'A','line_items':[None]}]}, {'invoices':[self.source,'broken']}]
        for value in bad:
            client=Mock();client.converse.return_value=response(json.dumps(value))
            with self.subTest(value=value),patch.object(service.boto3,'client',return_value=client),self.assertRaisesRegex(service.OcrError,'^EXTRACTION_INVALID_OUTPUT$'):
                service.extract_invoice_data_with_bedrock('fixture',MODEL,'ap-southeast-1')
