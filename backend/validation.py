"""Exact decimal validation; unknown amounts stay unknown and block approval."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP
import re
from .models import HEADER_FIELDS, ITEM_FIELDS, MONEY_FIELDS, now


class InvalidDraft(ValueError):
    pass


def amount(value):
    if value is None or value == '':
        return None
    if isinstance(value, (float, bool)):
        raise InvalidDraft('Nominal harus string decimal, bukan float/bool.')
    value = str(value)
    if not re.fullmatch(r'-?\d{1,18}(?:\.\d{1,6})?', value):
        raise InvalidDraft('Format decimal tidak valid (maksimal 18 angka dan 6 desimal).')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidDraft('Nominal tidak valid.') from exc
    if not result.is_finite() or result < 0:
        raise InvalidDraft('Nominal harus positif atau nol dan finite.')
    return format(result, 'f')


def normalize(fields):
    if not isinstance(fields, dict) or set(fields) - set(HEADER_FIELDS) - {'line_items'}:
        raise InvalidDraft('Field invoice tidak dikenal.')
    result = {}
    for key in HEADER_FIELDS:
        value = fields.get(key)
        if key in MONEY_FIELDS:
            value = amount(value)
        elif value is not None:
            if not isinstance(value, str) or len(value) > 2000:
                raise InvalidDraft('Field teks harus string maksimal 2000 karakter.')
            value = value.strip() or None
        result[key] = value
    if result['currency'] and not re.fullmatch('[A-Z]{3}', result['currency']):
        raise InvalidDraft('Mata uang harus kode tiga huruf kapital.')
    for key in ('invoice_date', 'due_date'):
        if result[key]:
            try:
                if date.fromisoformat(result[key]).isoformat() != result[key]:
                    raise ValueError()
            except ValueError as exc:
                raise InvalidDraft('Tanggal harus YYYY-MM-DD.') from exc
    rows = fields.get('line_items', [])
    if not isinstance(rows, list) or len(rows) > 500:
        raise InvalidDraft('Maksimal 500 item per invoice.')
    result['line_items'] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - set(ITEM_FIELDS):
            raise InvalidDraft('Field item tidak dikenal.')
        description = row.get('description')
        if description is not None and (not isinstance(description, str) or len(description) > 4000):
            raise InvalidDraft('Deskripsi item tidak valid.')
        result['line_items'].append({key: (description or None) if key == 'description' else amount(row.get(key))
                                     for key in ITEM_FIELDS})
    return result


def validate(fields, version, expected_count, extra_issues=(), resolutions=None, tolerance='1',source_withholding='0'):
    issues = list(extra_issues)
    def flag(code, message, field=None):
        issues.append({'code': code, 'severity': 'BLOCK', 'message': message, 'field': field, 'resolved': False})
    for key in ('vendor_name', 'invoice_number', 'invoice_date', 'currency', 'bank_name', 'account_number', 'account_holder'):
        if not fields.get(key):
            flag('MISSING_' + key.upper(), 'Lengkapi ' + key.replace('_', ' ') + '.', key)
    items = fields['line_items']
    if not items:
        flag('MISSING_ITEMS', 'Belum ada rincian item.')
    if expected_count is None or expected_count != len(items):
        flag('ITEM_COUNT_UNCONFIRMED', 'Periksa seluruh item hasil pemeriksaan dan konfirmasi jumlahnya.')
    calculated = []
    tol = Decimal(tolerance)
    with localcontext() as ctx:
        ctx.prec = 50
        for index, row in enumerate(items):
            if not row.get('description'):
                flag('MISSING_ITEM_DESCRIPTION', f'Deskripsi item {index + 1} belum lengkap.')
            components = [row.get(k) for k in ('quantity', 'unit_price', 'discount_amount', 'tax_amount')]
            reported = row.get('line_total')
            if any(n is None for n in components) or reported is None:
                flag('UNKNOWN_ITEM_AMOUNT', f'Nominal item {index + 1} belum lengkap, termasuk diskon dan pajak.')
            if any(n is None for n in components):
                continue
            quantity, price, discount, tax = map(Decimal, components)
            computed = (quantity * price - discount + tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            calculated.append(computed)
            if computed < 0 or (reported is not None and abs(computed - Decimal(reported).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) > tol):
                flag('LINE_TOTAL_MISMATCH', f'Perhitungan item {index + 1} berbeda dari total baris yang disimpan.')
        subtotal = sum(calculated, Decimal(0)) if items and len(calculated) == len(items) else None
        total = delta = None
        if any(fields[k] is None for k in MONEY_FIELDS):
            flag('UNKNOWN_INVOICE_AMOUNT', 'Subtotal, diskon, pajak, dan total harus terkonfirmasi.')
        if subtotal is not None:
            if fields['subtotal'] is not None and abs(subtotal - Decimal(fields['subtotal']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) > tol:
                flag('SUBTOTAL_MISMATCH', 'Jumlah item berbeda dengan subtotal yang disimpan.')
            if fields['invoice_discount_amount'] is not None and fields['invoice_tax_amount'] is not None:
                total = (subtotal - Decimal(fields['invoice_discount_amount']) + Decimal(fields['invoice_tax_amount']) - Decimal(source_withholding)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                delta = total - Decimal(fields['total_amount']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if fields['total_amount'] is not None else None
                if total < 0 or (delta is not None and abs(delta) > tol):
                    flag('TOTAL_MISMATCH', 'Total perhitungan berbeda dengan total yang disimpan.')
    if fields['invoice_date'] and fields['invoice_date'] > date.today().isoformat():
        flag('SUSPICIOUS_DATE', 'Tanggal invoice berada di masa depan.')
    for issue in issues:
        resolution = (resolutions or {}).get(issue['code'])
        issue['resolved'] = bool(resolution)
        if resolution:
            issue['resolution'] = resolution
    return {'valid': not any(i['severity'] == 'BLOCK' and not i['resolved'] for i in issues),
            'version': version, 'executed_at': now(), 'tolerance': tolerance, 'currency': fields['currency'],
            'calculated': {k: format(v, 'f') if v is not None else None
                           for k, v in [('subtotal', subtotal), ('total', total), ('delta', delta)]},
            'issues': issues}
