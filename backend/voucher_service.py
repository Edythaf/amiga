from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _display(value):
    """Ubah nilai kosong menjadi tanda strip dan amankan untuk PDF."""
    if value is None:
        return "-"

    text = str(value).strip()
    return text or "-"


def _paragraph(value, style):
    """Buat teks aman untuk ditampilkan sebagai Paragraph ReportLab."""
    text = escape(_display(value)).replace("\n", "<br/>")
    return Paragraph(text, style)


def generate_voucher_pdf(
    invoice_data,
    output_path,
    voucher_number,
    requester_name=None,
    approver_name=None,
):
    """
    Buat PDF voucher dari data invoice yang sudah disetujui.

    Nilai total dan pajak hanya ditampilkan dari hasil ekstraksi.
    Fungsi ini tidak menghitung ulang nilai invoice atau pajak.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "VoucherTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#14243a"),
        spaceAfter=12,
    )

    label_style = ParagraphStyle(
        "VoucherLabel",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
    )

    value_style = ParagraphStyle(
        "VoucherValue",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
    )

    header_style = ParagraphStyle(
        "VoucherTableHeader",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    cell_style = ParagraphStyle(
        "VoucherTableCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )

    centered_cell_style = ParagraphStyle(
        "VoucherCenteredCell",
        parent=cell_style,
        alignment=TA_CENTER,
    )

    right_cell_style = ParagraphStyle(
        "VoucherRightCell",
        parent=cell_style,
        alignment=TA_RIGHT,
    )

    currency = _display(invoice_data.get("currency"))
    total_amount = _display(invoice_data.get("total_amount"))

    if currency != "-" and total_amount != "-":
        if not total_amount.upper().startswith(currency.upper()):
            total_amount = f"{currency} {total_amount}"

    invoice_date = invoice_data.get("invoice_date")
    service_period = invoice_data.get("service_period")
    date_or_period = invoice_date or service_period

    story = [
        Paragraph("VOUCHER PENGELUARAN", title_style),
    ]

    summary_rows = [
        [
            _paragraph("Nomor", label_style),
            _paragraph(voucher_number, value_style),
        ],
        [
            _paragraph("Nama", label_style),
            _paragraph(requester_name, value_style),
        ],
        [
            _paragraph("Peruntukan", label_style),
            _paragraph(invoice_data.get("purpose"), value_style),
        ],
        [
            _paragraph("Tanggal / Periode", label_style),
            _paragraph(date_or_period, value_style),
        ],
        [
            _paragraph("Pemasok", label_style),
            _paragraph(invoice_data.get("supplier_name"), value_style),
        ],
        [
            _paragraph("Nominal", label_style),
            _paragraph(total_amount, value_style),
        ],
    ]

    summary_table = Table(
        summary_rows,
        colWidths=[42 * mm, 128 * mm],
        hAlign="LEFT",
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7deea")),
            ]
        )
    )

    story.extend([summary_table, Spacer(1, 8 * mm)])

    bank_rows = [
        [
            _paragraph("Metode pembayaran", label_style),
            _paragraph(invoice_data.get("payment_method"), value_style),
            _paragraph("Nama bank", label_style),
            _paragraph(invoice_data.get("supplier_bank_name"), value_style),
        ],
        [
            _paragraph("Nomor rekening", label_style),
            _paragraph(
                invoice_data.get("supplier_bank_account_number"),
                value_style,
            ),
            _paragraph("Nama pemilik rekening", label_style),
            _paragraph(
                invoice_data.get("supplier_bank_account_name"),
                value_style,
            ),
        ],
    ]

    bank_table = Table(
        bank_rows,
        colWidths=[35 * mm, 50 * mm, 38 * mm, 47 * mm],
        hAlign="LEFT",
    )
    bank_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f7fb")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7deea")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7deea")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.extend(
        [
            bank_table,
            Spacer(1, 8 * mm),
        ]
    )

    line_items = invoice_data.get("line_items") or []

    table_rows = [
        [
            _paragraph("No.", header_style),
            _paragraph("Tanggal", header_style),
            _paragraph("Keterangan", header_style),
            _paragraph("Jumlah", header_style),
            _paragraph("Harga", header_style),
        ]
    ]

    if line_items:
        for index, item in enumerate(line_items, start=1):
            if not isinstance(item, dict):
                continue

            item_amount = (
                item.get("line_total")
                if item.get("line_total") is not None
                else item.get("unit_price")
            )

            table_rows.append(
                [
                    _paragraph(item.get("line_number") or index, centered_cell_style),
                    _paragraph(invoice_date, centered_cell_style),
                    _paragraph(item.get("description"), cell_style),
                    _paragraph(item.get("quantity"), centered_cell_style),
                    _paragraph(item_amount, right_cell_style),
                ]
            )

    if len(table_rows) == 1:
        table_rows.append(
            [
                _paragraph("1", centered_cell_style),
                _paragraph(invoice_date, centered_cell_style),
                _paragraph(
                    f"Pembayaran invoice {_display(invoice_data.get('invoice_number'))}",
                    cell_style,
                ),
                _paragraph("1", centered_cell_style),
                _paragraph(total_amount, right_cell_style),
            ]
        )

    table_rows.append(
        [
            "",
            "",
            "",
            _paragraph("TOTAL", label_style),
            _paragraph(total_amount, right_cell_style),
        ]
    )

    items_table = Table(
        table_rows,
        colWidths=[12 * mm, 30 * mm, 80 * mm, 20 * mm, 28 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243b5a")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2f8")),
                ("SPAN", (0, -1), (2, -1)),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("ALIGN", (0, 1), (1, -1), "CENTER"),
                ("ALIGN", (3, 1), (4, -1), "RIGHT"),
            ]
        )
    )

    story.extend(
        [
            items_table,
            Spacer(1, 16 * mm),
        ]
    )

    signature_table = Table(
        [
            [
                _paragraph("Diajukan Oleh", centered_cell_style),
                _paragraph("Disetujui Oleh", centered_cell_style),
            ],
            [
                Paragraph("<br/><br/><br/>", centered_cell_style),
                Paragraph("<br/><br/><br/>", centered_cell_style),
            ],
            [
                _paragraph(requester_name, centered_cell_style),
                _paragraph(approver_name, centered_cell_style),
            ],
        ],
        colWidths=[85 * mm, 85 * mm],
        rowHeights=[10 * mm, 25 * mm, 10 * mm],
        hAlign="CENTER",
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, -1), 0.6, colors.HexColor("#9aa8ba")),
                ("BOX", (1, 0), (1, -1), 0.6, colors.HexColor("#9aa8ba")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(signature_table)

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Voucher Pengeluaran {voucher_number}",
    )
    pdf.build(story)

    return output_path