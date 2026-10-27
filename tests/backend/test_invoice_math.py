"""Shared browser/server financial contract; source figures never get overwritten."""
import json
from pathlib import Path
import unittest
from backend.validation import normalize, validate
from test_api import invoice_fields


class InvoiceMathTests(unittest.TestCase):
    def test_browser_server_rounding_contract(self):
        cases=json.loads((Path(__file__).parents[1]/'fixtures/invoice_math.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                fields=invoice_fields()
                fields.update(subtotal=case['subtotal'],total_amount=case['reported'],
                    invoice_discount_amount=case['discount'],invoice_tax_amount=case['tax'],
                    line_items=[dict(zip(('quantity','unit_price','discount_amount','tax_amount','line_total'),row),description='Fixture') for row in case['items']])
                fields=normalize(fields)
                result=validate(fields,1,len(fields['line_items']),tolerance='0.01')
                self.assertEqual(result['calculated'],{key:case[key] for key in ('subtotal','total','delta')})
                self.assertEqual(fields['total_amount'],case['reported'])

    def test_missing_source_totals_still_show_calculation_but_block_approval(self):
        fields=invoice_fields()
        fields['line_items'][0]['line_total']=None
        fields['total_amount']=None
        result=validate(normalize(fields),1,1)
        self.assertFalse(result['valid'])
        self.assertEqual(result['calculated'],{'subtotal':'220.20','total':'210.10','delta':None})
        self.assertTrue({'UNKNOWN_ITEM_AMOUNT','UNKNOWN_INVOICE_AMOUNT'} <= {i['code'] for i in result['issues']})
