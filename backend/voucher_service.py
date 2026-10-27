"""Single voucher PDF renderer. Display formatting never changes stored amounts."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, KeepTogether, SimpleDocTemplate, Spacer, Table, TableStyle

TEAL = colors.HexColor('#276f77')
INK = colors.HexColor('#193b3e')
MUTED = colors.HexColor('#5c7477')
LINE = colors.HexColor('#d5e2e3')
PALE = colors.HexColor('#eef5f5')


def _display(value):
    return '-' if value is None or not str(value).strip() else str(value).strip()


def _paragraph(value, style):
    return Paragraph(escape(_display(value)).replace('\n', '<br/>'), style)


def format_amount(value, currency='IDR', *, quantity=False):
    """Indonesian separators, exact Decimal; unknown values remain unknown.

    Prices/quantities retain up to six meaningful decimals; voucher totals have
    already been rounded by the financial service. This only formats display.
    """
    if value is None or value == '':
        return '-'
    try:
        with localcontext() as ctx:
            ctx.prec = 60
            number = Decimal(str(value))
            if not number.is_finite():
                return '-'
            number = number.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
            raw = format(abs(number), ',.6f').rstrip('0').rstrip('.')
            if not quantity and '.' in raw and len(raw.rsplit('.', 1)[1]) == 1:
                raw += '0'
            grouped = raw.translate(str.maketrans({',': '.', '.': ','}))
            sign = '-' if number < 0 else ''
            if quantity:
                return sign + grouped
            code = str(currency or '').strip().upper()
            prefix = 'Rp' if code == 'IDR' else code
            return f'{sign}{prefix} {grouped}'.strip()
    except (InvalidOperation, ValueError, TypeError):
        return '-'


def format_date(value):
    try:
        return date.fromisoformat(str(value)).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return _display(value)


def _reviewed_date(value):
    try:
        from zoneinfo import ZoneInfo
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo:
            return parsed.astimezone(ZoneInfo('Asia/Jakarta')).strftime('%d/%m/%Y %H:%M WIB')
        return parsed.strftime('%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        return _display(value)


def generate_voucher_pdf(invoice_data, output_path, voucher_number, requester_name=None,
                         approver_name=None, *, draft=False, version=None, reviewed_at=None):
    """Render supplied reviewed values; no invoice or tax recalculation here."""
    is_stream = hasattr(output_path, 'write')
    if not is_stream:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    body = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=13, textColor=INK)
    bold = ParagraphStyle('Label', parent=body, fontName='Helvetica-Bold')
    muted = ParagraphStyle('Muted', parent=body, fontSize=8, leading=11, textColor=MUTED)
    title = ParagraphStyle('Title', parent=bold, fontSize=19, leading=24, spaceAfter=4)
    section = ParagraphStyle('Section', parent=bold, fontSize=10, leading=14, spaceAfter=6)
    small = ParagraphStyle('Cell', parent=body, fontSize=8, leading=11)
    right = ParagraphStyle('Money', parent=small, fontSize=7.5, leading=10, alignment=TA_RIGHT)
    center = ParagraphStyle('Center', parent=small, alignment=TA_CENTER)
    header = ParagraphStyle('Header', parent=small, fontName='Helvetica-Bold', textColor=colors.white)
    header_right = ParagraphStyle('HeaderRight', parent=header, alignment=TA_RIGHT)
    total_style = ParagraphStyle('Final', parent=bold, fontSize=11, leading=16, alignment=TA_RIGHT)
    currency = invoice_data.get('currency') or ''
    amount = lambda value: format_amount(value, currency)
    p = _paragraph
    tax = invoice_data.get('voucher_tax')
    total = amount(invoice_data.get('total_amount'))
    story = [p('AMIGA / ADMINISTRASI INVOICE', muted),
             p('VOUCHER PENGELUARAN', title),
             p('DRAFT - Belum ditinjau AMIGA' if draft else 'Voucher resmi - Ditinjau AMIGA', bold),
             p(' | '.join(part for part in [f'Versi invoice: {version}' if version is not None else '',
                 f'Ditinjau: {_reviewed_date(reviewed_at)}' if reviewed_at else ''] if part), muted), Spacer(1, 3*mm)]
    date_or_period = format_date(invoice_data.get('invoice_date')) if invoice_data.get('invoice_date') else invoice_data.get('service_period')
    metadata = [[p('Nomor voucher',muted),p(voucher_number,body),'',''],
        [p('Nomor invoice',muted),p(invoice_data.get('invoice_number'),body),p('Tanggal / Periode',muted),p(date_or_period,body)],
        [p('Pemasok',muted),p(invoice_data.get('supplier_name'),body),p('Diajukan oleh',muted),p(requester_name,body)],
        [p('Peruntukan',muted),p(invoice_data.get('purpose'),body),'','']]
    # Full-width voucher/purpose rows and wrapping company names avoid clipping.
    details = Table(metadata, colWidths=[29*mm,56*mm,29*mm,56*mm], hAlign='LEFT')
    details.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
        ('SPAN',(1,0),(3,0)),('SPAN',(1,3),(3,3)),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    story.extend([details,Spacer(1,4*mm),p('Informasi pembayaran',section)])
    bank = Table([[p('Bank',muted),p(invoice_data.get('supplier_bank_name'),body),p('Nomor rekening',muted),p(invoice_data.get('supplier_bank_account_number'),body)],
                  [p('Atas nama',muted),p(invoice_data.get('supplier_bank_account_name'),body),p('Metode',muted),p(invoice_data.get('payment_method'),body)]],
                 colWidths=[22*mm,63*mm,30*mm,55*mm],hAlign='LEFT')
    bank.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.5,LINE),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([bank,Spacer(1,5*mm),p('Rincian barang / jasa',section),p('Mata uang: '+_display(currency)+' | Nominal memakai titik ribuan dan koma desimal.',muted),Spacer(1,2*mm)])
    rows = [[p(label,header_right if index>2 else header) for index,label in enumerate(['No','Keterangan','Qty','Harga satuan','Diskon','Pajak','Total baris'])]]
    for index,item in enumerate(invoice_data.get('line_items') or [],1):
        if not isinstance(item,dict):
            continue
        rows.append([p(index,center),p(item.get('description'),small),p(format_amount(item.get('quantity'),quantity=True),center),
                     *[p(amount(item.get(key)),right) for key in ['unit_price','discount_amount','tax_amount','line_total']]])
    if len(rows)==1:
        rows.append([p('1',center),p('Pembayaran invoice '+_display(invoice_data.get('invoice_number')),small),p('-',center),
                     p('-',right),p('-',right),p('-',right),p(total,right)])
    items = Table(rows,colWidths=[8*mm,48*mm,12*mm,27*mm,22*mm,22*mm,31*mm],repeatRows=1,splitInRow=1,hAlign='LEFT')
    items.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),TEAL),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LINEBELOW',(0,0),(-1,0),.7,TEAL),('LINEBELOW',(0,1),(-1,-1),.35,LINE),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([items,Spacer(1,3*mm)])
    totals = [('Subtotal rincian',invoice_data.get('subtotal')),('Diskon invoice',invoice_data.get('invoice_discount_amount')),
              ('Pajak invoice sebelum penyesuaian',invoice_data.get('tax_amount'))]
    if tax:
        calculated=tax['calculated']
        totals.extend([('Total sebelum penyesuaian',calculated['source_total']),('Penyesuaian PPN',calculated['vat_adjustment']),
                       ('Penyesuaian potongan '+tax['plan']['withholding_kind'],calculated['withholding_adjustment'])])
    total_rows=[[p(label,body),p(amount(value),right)] for label,value in totals]
    total_rows.append([p('TOTAL AKHIR VOUCHER',bold),p(total,total_style)])
    summary = Table(total_rows,colWidths=[117*mm,53*mm],hAlign='LEFT')
    summary.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LINEABOVE',(0,-1),(-1,-1),.8,TEAL),('BACKGROUND',(0,-1),(-1,-1),PALE),
        ('TOPPADDING',(0,-1),(-1,-1),9),('BOTTOMPADDING',(0,-1),(-1,-1),9)]))
    story.extend([KeepTogether(summary),Spacer(1,3*mm)])
    if tax and tax['plan'].get('note'):
        story.extend([p('Catatan pemeriksaan reviewer',section),p(tax['plan']['note'],body),Spacer(1,3*mm)])
    disclaimer=('DRAFT. Belum disetujui reviewer. Tidak dapat digunakan sebagai voucher resmi.' if draft else
        'Voucher ini telah ditinjau oleh AMIGA. Persetujuan pembayaran dan pelaksanaan pembayaran merupakan kewenangan klien.')
    story.extend([p(disclaimer,muted),Spacer(1,4*mm)])
    signatures=Table([[p('Diajukan oleh',muted),p('Ditinjau oleh AMIGA',muted)],
                      [Spacer(1,10*mm),Spacer(1,10*mm)],
                      [p(requester_name,body),p(approver_name,body)]],colWidths=[85*mm,85*mm],hAlign='LEFT')
    signatures.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),3),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),('LINEABOVE',(0,2),(-1,2),.5,LINE)]))
    story.append(KeepTogether(signatures))
    pdf=SimpleDocTemplate(output_path if is_stream else str(output_path),pagesize=A4,rightMargin=20*mm,leftMargin=20*mm,
        topMargin=16*mm,bottomMargin=17*mm,title=f'Voucher Pengeluaran {voucher_number}',author='AMIGA')
    def decorate(canvas,document):
        canvas.saveState()
        canvas.setStrokeColor(LINE);canvas.line(20*mm,13*mm,190*mm,13*mm)
        canvas.setFillColor(MUTED);canvas.setFont('Helvetica',7)
        canvas.drawString(20*mm,9*mm,'AMIGA | Administrasi, bukan otorisasi pembayaran')
        canvas.drawRightString(190*mm,9*mm,f'Halaman {document.page}')
        if draft:
            canvas.setFillColor(colors.Color(.75,.75,.75,alpha=.16));canvas.setFont('Helvetica-Bold',80)
            canvas.translate(105*mm,148*mm);canvas.rotate(40);canvas.drawCentredString(0,0,'DRAFT')
        canvas.restoreState()
    pdf.build(story,onFirstPage=decorate,onLaterPages=decorate)
    return output_path
