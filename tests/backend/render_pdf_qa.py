"""Generate clearly fictional voucher samples for visual QA, not live records."""
from pathlib import Path
from backend.pdf_service import render_voucher
from test_api import invoice_fields

directory = Path('.runtime-temp/pdf-qa')
directory.mkdir(parents=True, exist_ok=True)
fields = invoice_fields('QC-FIKTIF-001')
fields['vendor_name'] = 'PT Vendor Fiktif untuk QC'
fields['line_items'] = [dict(fields['line_items'][0], description='Contoh barang fiktif untuk pemeriksaan tata letak') for _ in range(3)]
fields.update(subtotal='660.60', total_amount='650.50')
(directory / 'voucher-draft.pdf').write_bytes(render_voucher(fields, 'QC-DRAFT', 1))
fields['line_items'] = [dict(fields['line_items'][0], description=f'{index + 1}. Contoh item fiktif QC, bukan tagihan nyata') for index in range(45)]
fields.update(subtotal='9909.00', total_amount='9898.90')
(directory / 'voucher-reviewed.pdf').write_bytes(render_voucher(fields, 'QC-FIKTIF-REVIEWED', 2, 'Reviewer Fiktif QC', '2026-10-15T00:00:00Z'))
print('Wrote two fictional QA samples in .runtime-temp/pdf-qa')
