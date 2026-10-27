"""Voucher-only tax adjustments; original invoice amounts remain unchanged."""
from decimal import Decimal,localcontext,ROUND_HALF_UP
from .models import InvoiceTaxPlan
from .validation import amount,InvalidDraft

FIELDS=('vat_mode','vat_rate','vat_base','withholding_mode','withholding_kind','withholding_rate','withholding_base','source_withholding','note','withholding_amount')
CATALOG={
    'PPN_NON_LUXURY':('PPN efektif nonmewah','11','https://www.jdih.kemenkeu.go.id/dok/pmk-131-tahun-2024/summary'),
    'PPN_LUXURY':('PPN barang mewah','12','https://www.jdih.kemenkeu.go.id/dok/pmk-131-tahun-2024/summary'),
    'PPH23_SERVICE':('PPh 23 jasa','2','https://www.pajak.go.id/id/pph-pasal-23'),
    'PPH23_RENT':('PPh 23 sewa selain tanah/bangunan','2','https://www.pajak.go.id/id/pph-pasal-23'),
    'PPH4_RENT':('PPh final sewa tanah/bangunan','10','https://www.pajak.go.id/id/pemotongan-pajak-penghasilan-pasal-4-ayat-2-3'),
    'PPH22_GOV':('PPh 22 pembelian oleh pemungut tertentu','1.5','https://www.pajak.go.id/pph-pasal-22'),
}


def defaults(fields):
    return dict(vat_mode='KEEP',vat_rate='0',vat_base=fields.get('subtotal') or '0',withholding_mode='KEEP',
        withholding_kind='PPh',withholding_rate='0',withholding_base=fields.get('subtotal') or '0',source_withholding='0',note='',withholding_amount=None)


def normalize_plan(value):
    if not isinstance(value,dict) or set(value) not in (set(FIELDS),set(FIELDS)-{'withholding_amount'}):raise InvalidDraft('Lengkapi seluruh rincian pajak voucher.')
    if value['vat_mode'] not in ('KEEP','ADD','REPLACE') or value['withholding_mode'] not in ('KEEP','DEDUCT','REPLACE'):
        raise InvalidDraft('Cara perlakuan pajak tidak valid.')
    result={**value,'withholding_amount':None if value.get('withholding_amount') in (None,'') else amount(value['withholding_amount'])}
    for key in ('vat_rate','vat_base','withholding_rate','withholding_base','source_withholding'):
        result[key]=amount(value[key])
        if result[key] is None:raise InvalidDraft('Isi tarif dan dasar pajak, gunakan nol bila tidak berlaku.')
    if any(Decimal(result[k])>100 for k in ('vat_rate','withholding_rate')):raise InvalidDraft('Tarif pajak harus antara 0 dan 100 persen.')
    for key,size in [('withholding_kind',80),('note',2000)]:
        if not isinstance(result[key],str) or not 1<=len(result[key].strip())<=size:raise InvalidDraft('Isi jenis PPh dan alasan perlakuan pajak.')
        result[key]=result[key].strip()
    return result


def calculate_tax(fields,plan):
    with localcontext() as ctx:
        ctx.prec=60
        q=lambda n:Decimal(n).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        if fields.get('total_amount') is None:raise InvalidDraft('Total sumber belum terkonfirmasi.')
        taxes=[fields.get('invoice_tax_amount')]+[row.get('tax_amount') for row in fields['line_items']]
        source_vat=q(sum((Decimal(v or '0') for v in taxes),Decimal(0)))
        if plan['vat_mode']!='KEEP' and any(v is None for v in taxes):raise InvalidDraft('Konfirmasikan pajak sumber sebelum menambah atau menggantinya.')
        source_pph=q(plan['source_withholding'])
        if plan['vat_mode']=='ADD' and source_vat>0:raise InvalidDraft('Pajak sudah tercatat. Pilih pertahankan atau ganti pajak sumber agar tidak ganda.')
        if plan['withholding_mode']=='DEDUCT' and source_pph>0:raise InvalidDraft('PPh sudah ada. Pilih pertahankan atau ganti potongan agar tidak ganda.')
        vat=q(Decimal(plan['vat_base'])*Decimal(plan['vat_rate'])/100)
        pph=q(plan['withholding_amount']) if plan.get('withholding_amount') not in (None,'') else q(Decimal(plan['withholding_base'])*Decimal(plan['withholding_rate'])/100)
        vat_delta=Decimal(0) if plan['vat_mode']=='KEEP' else vat-(source_vat if plan['vat_mode']=='REPLACE' else 0)
        pph_delta=Decimal(0) if plan['withholding_mode']=='KEEP' else pph-(source_pph if plan['withholding_mode']=='REPLACE' else 0)
        net=q(q(fields['total_amount'])+vat_delta-pph_delta)
        if net<0:raise InvalidDraft('Potongan menghasilkan nilai voucher negatif. Periksa dasar dan tarif.')
        return {k:format(v,'f') for k,v in dict(source_total=q(fields['total_amount']),source_vat=source_vat,
            source_withholding=source_pph,vat=vat,withholding=pph,vat_adjustment=vat_delta,withholding_adjustment=pph_delta,net_payable=net).items()}


def plan_dto(db,inv,fields):
    row=db.get(InvoiceTaxPlan,(inv.id,inv.current_version))
    plan={key:getattr(row,key) for key in FIELDS} if row else defaults(fields)
    try:calculated=calculate_tax(fields,plan);error=None
    except InvalidDraft as exc:calculated=None;error=str(exc)
    return {'version':inv.current_version,'revision':row.revision if row else 0,'plan':plan,'calculated':calculated,'error':error,
        'ai_state':row.ai_state if row else 'NONE','ai_result':row.ai_result if row else None,
        'edited_at':row.edited_at if row else None,'applied':bool(row and row.revision>0)}


def applied_tax(db,inv,fields,version=None):
    row=db.get(InvoiceTaxPlan,(inv.id,version or inv.current_version))
    if not row or row.revision==0:return None
    plan={key:getattr(row,key) for key in FIELDS}
    return {'revision':row.revision,'plan':plan,'calculated':calculate_tax(fields,plan),'edited_at':row.edited_at}
