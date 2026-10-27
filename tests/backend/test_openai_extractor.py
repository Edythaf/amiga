"""Provider contract tests use a mocked transport and never spend API credits."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import requests
from backend.openai_extractor import extract_pdf, extraction_schema, ENDPOINT
from backend.ai_config import resolve_openai_key
from backend.processing import real_extractor
from backend.validation import normalize
from test_api import invoice_fields, pdf_bytes


class OpenAIExtractorTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'.runtime-temp'
        root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.path=Path(self.temp.name)/'test.pdf'
        self.path.write_bytes(pdf_bytes())
        self.config={'AI_PROVIDER':'openai','OPENAI_API_KEY':'fictional-secret-key','OPENAI_MODEL':'gpt-6-luna'}

    def tearDown(self):
        self.temp.cleanup()

    def response(self, **changes):
        value={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'invoices':[invoice_fields()],'ocr_text':'fixture'})}]}],'usage':{'input_tokens':100,'output_tokens':50},**changes}
        return Mock(status_code=200,json=Mock(return_value=value))

    def test_pdf_and_schema_use_luna_responses_store_false_no_redirects_and_no_retry(self):
        response=self.response()
        with patch('backend.openai_extractor.requests.post',return_value=response) as post:
            result=real_extractor(self.path,self.config)
        args,kwargs=post.call_args
        self.assertEqual(args,(ENDPOINT,))
        payload=kwargs['json']
        self.assertEqual(payload['model'],'gpt-6-luna')
        self.assertFalse(payload['store'])
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['headers']['Authorization'],'Bearer fictional-secret-key')
        self.assertTrue(payload['input'][0]['content'][0]['file_data'].startswith('data:application/pdf;base64,JVBER'))
        self.assertTrue(payload['text']['format']['strict'])
        self.assertNotIn('fictional-secret-key',json.dumps(payload))
        self.assertNotIn('fictional-secret-key',json.dumps(result))
        self.assertEqual(normalize(result['invoices'][0])['account_number'],'0000123')
        self.assertEqual(result['provider'],'openai')
        post.assert_called_once()
        response.close.assert_called_once()

    def test_all_schema_fields_required_nullable_and_no_additional_properties(self):
        schema=extraction_schema()
        invoice=schema['properties']['invoices']['items']
        self.assertEqual(set(invoice['properties']),set(invoice['required']))
        self.assertFalse(invoice['additionalProperties'])
        self.assertEqual(invoice['properties']['total_amount']['type'],['string','null'])
        self.assertFalse(invoice['properties']['line_items']['items']['additionalProperties'])

    def test_provider_errors_are_sanitized_and_never_fall_back_to_bedrock(self):
        for status,code in [(401,'OPENAI_AUTH_FAILED'),(403,'OPENAI_ACCESS_DENIED'),(404,'OPENAI_MODEL_UNAVAILABLE'),(429,'OPENAI_QUOTA_LIMIT'),(500,'OPENAI_UNAVAILABLE'),(302,'OPENAI_UNAVAILABLE')]:
            response=Mock(status_code=status,text='secret from provider must not be reflected')
            with patch('backend.openai_extractor.requests.post',return_value=response) as post, self.assertRaisesRegex(RuntimeError,code):
                real_extractor(self.path,self.config)
            post.assert_called_once()
            response.json.assert_not_called()
        with patch('backend.openai_extractor.requests.post',side_effect=requests.Timeout('fictional-secret-key')) as post:
            with self.assertRaisesRegex(RuntimeError,'^OPENAI_UNAVAILABLE$'):
                extract_pdf(self.path,self.config)
            post.assert_called_once()

    def test_incomplete_refusal_and_malformed_output_do_not_publish_partial_invoices(self):
        cases=[(self.response(status='incomplete'),'EXTRACTION_TRUNCATED'),
               (self.response(output=[{'type':'message','content':[{'type':'refusal','refusal':'No'}]}]),'EXTRACTION_REFUSED'),
               (self.response(output=[]),'EXTRACTION_INVALID_OUTPUT'),
               (self.response(status='failed'),'EXTRACTION_INVALID_OUTPUT')]
        for response,code in cases:
            with patch('backend.openai_extractor.requests.post',return_value=response),self.assertRaisesRegex(RuntimeError,code):
                extract_pdf(self.path,self.config)

    def test_missing_key_or_invalid_pdf_never_sends_a_request(self):
        with patch('backend.openai_extractor.requests.post') as post:
            with self.assertRaisesRegex(RuntimeError,'EXTRACTION_NOT_CONFIGURED'):
                extract_pdf(self.path,{**self.config,'OPENAI_API_KEY':''})
            self.path.write_bytes(b'not a PDF')
            with self.assertRaisesRegex(RuntimeError,'EXTRACTION_INVALID_PDF'):
                extract_pdf(self.path,self.config)
            post.assert_not_called()

    def test_key_file_reuses_atlas_secret_without_copying_it_or_accepting_ambiguity(self):
        secret='sk-fictional-key-with-enough-characters'
        path=Path(self.temp.name)/'key.txt'
        path.write_text('GPT_LUNA_API='+secret+'\n',encoding='utf-8')
        self.assertEqual(resolve_openai_key({'OPENAI_API_KEY_FILE':str(path)}),secret)
        self.assertEqual(resolve_openai_key({'GPT_LUNA_API':secret}),secret)
        path.write_text(secret+'\nsk-another-fictional-key-with-enough-characters',encoding='utf-8')
        self.assertEqual(resolve_openai_key({'OPENAI_API_KEY_FILE':str(path)}),'')
