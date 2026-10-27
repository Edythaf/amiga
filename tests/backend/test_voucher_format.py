"""PDF display stays readable while decimal values and source data stay intact."""
import copy
import unittest
from io import BytesIO
from pypdf import PdfReader
from backend.pdf_service import render_voucher
from backend.voucher_service import format_amount


def fixture():
    fields = dict(vendor_name='PT Contoh Fiktif', invoice_number='CONTOH/2026/014',
        invoice_date='2026-10-15', currency='IDR', bank_name='Bank Contoh',
        account_number='0000123456789', account_holder='PT Contoh Fiktif',
        subtotal='10750000.00', invoice_discount_amount='0', invoice_tax_amount='1155000', total_amount='11905000.00',
        line_items=[dict(description=label,quantity=qty,unit_price=price,discount_amount='0',tax_amount='0',line_total=total)
            for label,qty,price,total in [('Pengadaan access point Wi-Fi 6','4','1850000','7400000'),
                ('Jasa konfigurasi jaringan','2','1250000','2500000'),('Kabel dan konektor jaringan','10','85000','850000')]])
    tax=dict(plan=dict(withholding_kind='PPh',note='Hasil pemeriksaan fixture. Angka ini data uji, bukan rekomendasi pajak.'),
        calculated=dict(source_total='11905000.00',vat_adjustment='-1155000.00',withholding_adjustment='860000.00',net_payable='9890000.00'))
    return fields,tax


class VoucherFormatTests(unittest.TestCase):
    def test_grouping_currency_and_six_decimal_precision_without_float(self):
        self.assertEqual(format_amount('1000000.00'),'Rp 1.000.000')
        self.assertEqual(format_amount('-1155000.00'),'-Rp 1.155.000')
        self.assertEqual(format_amount('123456789012345678.123456','USD'),'USD 123.456.789.012.345.678,123456')
        self.assertEqual(format_amount('12.500000',quantity=True),'12,5')
        for value in [None,'','not a number','NaN','Infinity']:
            self.assertEqual(format_amount(value),'-')

    def test_pdf_groups_every_amount_and_preserves_source_and_account(self):
        fields,tax=fixture();before=copy.deepcopy((fields,tax))
        data=render_voucher(fields,'vch_fixture',3,'Reviewer Contoh','2026-10-16T10:00:00Z',requester_name='Uploader Contoh',tax=tax)
        pdf=PdfReader(BytesIO(data));text=' '.join(p.extract_text() for p in pdf.pages)
        for value in ['Rp 1.850.000','Rp 7.400.000','Rp 9.890.000','-Rp 1.155.000','Rp 860.000',
                      '0000123456789','15/10/2026','16/10/2026 17:00 WIB','Catatan pemeriksaan reviewer']:
            self.assertIn(value,text)
        self.assertNotIn('IDR 9890000.00',text)
        self.assertNotIn('DRAFT',text)
        self.assertEqual(len(pdf.pages),1)
        self.assertIn('Uploader Contoh',text)
        self.assertIn('Reviewer Contoh',text)
        self.assertEqual((fields,tax),before)

    def test_long_notes_and_many_items_paginate_with_repeated_header(self):
        fields,tax=fixture()
        fields['line_items']=[{**fields['line_items'][0],'description':f'ITEM-{index:03d} Barang <uji> & jasa dengan keterangan panjang yang boleh membungkus.'} for index in range(65)]
        tax['plan']['note']=('Catatan pemeriksaan panjang dengan bukti dan penjelasan. '*32)+' CATATAN-SELESAI'
        pdf=PdfReader(BytesIO(render_voucher(fields,'vch_long_fixture',1,requester_name='Nama pengaju '*20,tax=tax)))
        texts=[p.extract_text() for p in pdf.pages]
        self.assertGreater(len(pdf.pages),2)
        text=' '.join(texts)
        self.assertIn('CATATAN-SELESAI',text)
        for index in range(65):self.assertIn(f'ITEM-{index:03d}',text)
        for page in texts:
            self.assertIn('Halaman',page)
            if 'ITEM-' in page:self.assertIn('Harga satuan',page)
        self.assertIn('DRAFT',text)


if __name__=='__main__':unittest.main()
