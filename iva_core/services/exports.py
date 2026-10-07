import csv, io
from decimal import Decimal
from iva_core.models import FiscalDocument, ThirdParty, RentWithholding

DOC_CODE = {'CF':'01','CCF':'03','NC':'05','ND':'06','FEX':'11','FSE':'14'}

def n(v):
    return f"{Decimal(v or 0):.2f}"

def txt(v, default='0'):
    s = str(v or '').strip()
    return s if s else default

def csv_bytes(rows):
    out = io.StringIO(newline='')
    w = csv.writer(out, delimiter=';', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
    w.writerows(rows)
    return out.getvalue().encode('utf-8-sig')

def annex1_sales_taxpayers(docs, third_map):
    rows=[]
    for d in docs:
        if d.operation!='VENTA' or d.doc_type not in ('CCF','NC','ND'): continue
        t=third_map.get(d.third_party_id)
        rows.append([
            d.issue_date.strftime('%d/%m/%Y'), d.doc_class, DOC_CODE.get(d.doc_type,'03'), txt(d.resolution_no), txt(d.series),
            txt(d.document_no), txt(d.internal_control), txt((t.tax_id or t.nrc) if t else ''), txt(t.name if t else 'SIN IDENTIFICAR'),
            n(d.exempt), n(d.non_taxable), n(d.taxable), n(d.vat), '0.00','0.00', n(d.total), txt(t.dui if t else ''),
            d.rent_operation_code, d.income_type_code, 1
        ])
    return csv_bytes(rows)

def annex2_sales_consumer(docs):
    rows=[]
    for d in docs:
        if d.operation!='VENTA' or d.doc_type not in ('CF','FEX'): continue
        rows.append([
            d.issue_date.strftime('%d/%m/%Y'), d.doc_class, DOC_CODE.get(d.doc_type,'01'), txt(d.resolution_no), txt(d.series),
            txt(d.internal_control), txt(d.internal_control), txt(d.document_no), txt(d.document_no), '0',
            n(d.exempt), '0.00', n(d.non_taxable), n(d.taxable), '0.00','0.00','0.00','0.00','0.00', n(d.total),
            d.rent_operation_code, d.income_type_code, 2
        ])
    return csv_bytes(rows)

def annex3_purchases(docs, third_map):
    rows=[]
    for d in docs:
        if d.operation!='COMPRA' or d.doc_type=='FSE': continue
        t=third_map.get(d.third_party_id)
        rows.append([
            d.issue_date.strftime('%d/%m/%Y'), d.doc_class, DOC_CODE.get(d.doc_type,'03'), txt(d.document_no), txt((t.tax_id or t.nrc) if t else ''),
            txt(t.name if t else 'SIN IDENTIFICAR'), n(Decimal(d.exempt or 0)+Decimal(d.non_taxable or 0)), '0.00','0.00', n(d.taxable),
            '0.00','0.00','0.00', n(d.vat), n(d.total), txt(t.dui if t else ''), d.rent_operation_code, d.classification_code,
            d.sector_code, d.cost_expense_code, 3
        ])
    return csv_bytes(rows)

def annex5_excluded(docs, third_map):
    rows=[]
    for d in docs:
        if d.operation!='COMPRA' or d.doc_type!='FSE': continue
        t=third_map.get(d.third_party_id)
        id_type='1' if t and t.dui else '2'
        ident=(t.dui or t.tax_id) if t else '0'
        rows.append([
            id_type, txt(ident), txt(t.name if t else 'SIN IDENTIFICAR'), d.issue_date.strftime('%d/%m/%Y'), txt(d.series), txt(d.document_no),
            n(d.total), n(d.iva_withholding), d.rent_operation_code, d.classification_code, d.sector_code, d.cost_expense_code, 5
        ])
    return csv_bytes(rows)

def f14_withholdings(items, third_map, period_code):
    """CSV oficial F-14 V16 (octubre 2025), 23 columnas A-W, sin encabezados.

    period_code debe venir como MMYYYY, por ejemplo 102026.
    """
    rows=[]
    for r in items:
        t=third_map.get(r.third_party_id)
        domic_code='1' if r.domiciled else '2'
        # Para no domiciliados Hacienda exige código de país de 4 dígitos.
        country = txt(r.country_code, '9300') if not r.domiciled else txt(r.country_code, '9300')
        rows.append([
            domic_code,                                      # A DOMICILIADO
            country,                                         # B CODIGO DE PAIS
            txt(t.name if t else 'SIN IDENTIFICAR'),         # C APELLIDOS/NOMBRES O RAZON SOCIAL
            txt(t.tax_id if t else '', ''),                  # D NIT/NIF
            txt(t.dui if t else '', ''),                     # E DUI
            txt(r.income_code, ''),                          # F CODIGO DE INGRESO
            n(r.accrued_amount),                             # G MONTO DEVENGADO
            n(r.bonus_amount),                               # H BONIFICACIONES/GRATIFICACIONES
            n(r.withheld_amount),                            # I IMPUESTO RETENIDO
            n(r.aguinaldo_exempt),                           # J AGUINALDO EXENTO
            n(r.aguinaldo_taxable),                          # K AGUINALDO GRAVADO
            n(r.afp),                                        # L AFP
            n(r.isss),                                       # M ISSS
            n(r.inpep),                                      # N INPEP
            n(r.ipsfa),                                      # O IPSFA
            n(r.cefafa),                                     # P CEFAFA
            n(r.bienestar_magisterial),                      # Q BIENESTAR MAGISTERIAL
            n(r.isss_ivm),                                   # R ISSS IVM
            r.operation_code,                                # S TIPO DE OPERACION
            r.classification_code,                           # T CLASIFICACION
            r.sector_code,                                   # U SECTOR
            r.cost_expense_code,                             # V TIPO DE COSTO/GASTO
            period_code,                                     # W PERIODO MMYYYY
        ])
    return csv_bytes(rows)
