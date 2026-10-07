import json
from decimal import Decimal
from datetime import datetime

D = lambda v: Decimal(str(v or 0))

def _get(d, *paths, default=None):
    for path in paths:
        cur=d
        try:
            for p in path.split('.'):
                cur=cur[p]
            return cur
        except Exception:
            continue
    return default

def parse_dte_bytes(raw: bytes) -> dict:
    data = json.loads(raw.decode('utf-8-sig'))
    ident = data.get('identificacion', {})
    emisor = data.get('emisor', {})
    receptor = data.get('receptor', {}) or {}
    resumen = data.get('resumen', {})
    tipo = str(ident.get('tipoDte', ''))
    map_tipo = {'01':'CF','03':'CCF','05':'NC','06':'ND','11':'FEX','14':'FSE'}
    return {
        'doc_type': map_tipo.get(tipo, tipo or 'OTRO'),
        'doc_class': 4,
        'issue_date': datetime.strptime(ident.get('fecEmi'), '%Y-%m-%d').date(),
        'document_no': ident.get('numeroControl',''),
        'internal_control': ident.get('numeroControl',''),
        'generation_code': ident.get('codigoGeneracion',''),
        'third_name_purchase': emisor.get('nombre',''),
        'third_nit_purchase': emisor.get('nit','') or '',
        'third_nrc_purchase': emisor.get('nrc','') or '',
        'third_name_sale': receptor.get('nombre','') or 'CONSUMIDOR FINAL',
        'third_nit_sale': receptor.get('nit','') or receptor.get('numDocumento','') or '',
        'third_nrc_sale': receptor.get('nrc','') or '',
        'exempt': D(resumen.get('totalExenta')),
        'non_taxable': D(resumen.get('totalNoSuj')),
        'taxable': D(resumen.get('totalGravada')),
        'vat': D(resumen.get('totalIva')) if resumen.get('totalIva') is not None else D(resumen.get('ivaRete1',0))*0,
        'total': D(resumen.get('totalPagar') if resumen.get('totalPagar') is not None else resumen.get('montoTotalOperacion')),
        'iva_withholding': D(resumen.get('ivaRete1')),
        'iva_perception': D(resumen.get('reteRenta'))*0,
        'rent_withholding': D(resumen.get('reteRenta')),
        'raw': data,
    }
