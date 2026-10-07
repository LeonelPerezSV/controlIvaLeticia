import io
import re
import pandas as pd
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

BOOK_NAMES = {
    'COMPRAS': 'LIBRO DE COMPRAS',
    'VENTAS_CCF': 'LIBRO DE VENTAS A CONTRIBUYENTES',
    'VENTAS_CF': 'LIBRO DE VENTAS A CONSUMIDOR FINAL',
}

MONEY_COLS = ('Exento','No sujeto','Gravado','IVA','Ret/Per IVA','Total')


def make_book_df(docs, third_map, kind):
    data=[]
    for d in docs:
        if kind=='COMPRAS' and d.operation!='COMPRA':
            continue
        if kind=='VENTAS_CCF' and not (d.operation=='VENTA' and d.doc_type in ('CCF','NC','ND')):
            continue
        if kind=='VENTAS_CF' and not (d.operation=='VENTA' and d.doc_type in ('CF','FEX')):
            continue
        t=third_map.get(d.third_party_id)
        data.append({
            'Fecha': d.issue_date,
            'Tipo': d.doc_type,
            'Documento': d.document_no,
            'Tercero': t.name if t else '',
            'NIT/NRC': (t.tax_id or t.nrc) if t else '',
            'Exento': float(d.exempt or 0),
            'No sujeto': float(d.non_taxable or 0),
            'Gravado': float(d.taxable or 0),
            'IVA': float(d.vat or 0),
            'Ret/Per IVA': float((d.iva_withholding or 0)+(d.iva_perception or 0)),
            'Total': float(d.total or 0),
        })
    return pd.DataFrame(data)


def _safe_sheet_name(name):
    name = re.sub(r'[\\/*?:\[\]]', ' ', name or 'Libro IVA').strip()
    return (name or 'Libro IVA')[:31]


def df_to_xlsx(df, company_name, nrc, nit, period_label, book_name):
    """Genera el libro IVA con encabezado fiscal y detalle tabular."""
    bio=io.BytesIO()
    sheet_name=_safe_sheet_name(book_name.title())
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        # La tabla comienza debajo del encabezado fiscal.
        df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=6)
        ws=writer.book[sheet_name]

        ws.merge_cells('A1:K1')
        ws['A1']=book_name
        ws['A1'].font=Font(bold=True, size=14)
        ws['A1'].alignment=Alignment(horizontal='center')

        ws.merge_cells('A2:K2')
        ws['A2']=f'Nombre o Razón Social: {company_name or ""}'
        ws['A2'].font=Font(bold=True)

        ws.merge_cells('A3:E3')
        ws['A3']=f'NRC / Número de IVA (RUC): {nrc or ""}'
        ws.merge_cells('F3:K3')
        ws['F3']=f'NIT: {nit or ""}'

        ws.merge_cells('A4:K4')
        ws['A4']=f'Período: {period_label}'
        ws['A4'].font=Font(bold=True)

        # Formato de tabla.
        thin=Side(style='thin', color='808080')
        for cell in ws[7]:
            cell.font=Font(bold=True)
            cell.alignment=Alignment(horizontal='center', vertical='center')
            cell.border=Border(top=thin,bottom=thin,left=thin,right=thin)

        for row in ws.iter_rows(min_row=8, max_row=ws.max_row, min_col=1, max_col=11):
            for cell in row:
                cell.border=Border(top=thin,bottom=thin,left=thin,right=thin)

        # Formato monetario y anchos útiles.
        headers={cell.value: cell.column for cell in ws[7]}
        for col_name in MONEY_COLS:
            col=headers.get(col_name)
            if col:
                for r in range(8, ws.max_row+1):
                    ws.cell(r,col).number_format='#,##0.00'

        widths={1:12,2:10,3:24,4:36,5:22,6:14,7:14,8:14,9:14,10:14,11:14}
        for col_idx,width in widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width=width

        ws.freeze_panes='A8'
        ws.sheet_view.showGridLines=False
        ws.print_title_rows='1:7'
        ws.page_setup.orientation='landscape'
        ws.page_setup.fitToWidth=1
        ws.page_margins.left=0.25
        ws.page_margins.right=0.25
        ws.page_margins.top=0.4
        ws.page_margins.bottom=0.4

    return bio.getvalue()


def df_to_pdf(df, company_name, nrc, nit, period_label, book_name):
    """Genera PDF del libro IVA con encabezado fiscal repetible en la primera página."""
    bio=io.BytesIO()
    styles=getSampleStyleSheet()
    centered=ParagraphStyle(
        'CenteredBookTitle', parent=styles['Heading2'], alignment=TA_CENTER,
        fontName='Helvetica-Bold', fontSize=12, leading=14
    )
    meta=ParagraphStyle(
        'BookMeta', parent=styles['BodyText'], fontSize=8.5, leading=11
    )
    doc=SimpleDocTemplate(
        bio, pagesize=landscape(letter), leftMargin=18, rightMargin=18,
        topMargin=20, bottomMargin=20
    )
    elements=[
        Paragraph(book_name, centered),
        Spacer(1,5),
        Paragraph(f'<b>Nombre o Razón Social:</b> {company_name or ""}', meta),
        Paragraph(f'<b>NRC / Número de IVA (RUC):</b> {nrc or ""} &nbsp;&nbsp;&nbsp;&nbsp; <b>NIT:</b> {nit or ""}', meta),
        Paragraph(f'<b>Período:</b> {period_label}', meta),
        Spacer(1,8),
    ]

    if df.empty:
        elements.append(Paragraph('Sin registros para el período seleccionado.', styles['BodyText']))
    else:
        printable=df.copy()
        for c in printable.columns:
            if c in MONEY_COLS:
                printable[c]=printable[c].map(lambda x:f'{x:,.2f}')
        values=[list(printable.columns)]+printable.astype(str).values.tolist()
        col_widths=[48,38,90,145,85,58,58,58,58,62,62]
        table=Table(values, repeatRows=1, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.3,colors.grey),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),5.8),
            ('ALIGN',(5,1),(-1,-1),'RIGHT'),
            ('VALIGN',(0,0),(-1,-1),'TOP'),
            ('TOPPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ]))
        elements.append(table)
    doc.build(elements)
    return bio.getvalue()
