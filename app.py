import os, hashlib
from pathlib import Path
from datetime import date
from decimal import Decimal
import pandas as pd
import streamlit as st
from sqlalchemy.exc import IntegrityError
from iva_core.db import Base, engine, SessionLocal
from iva_core.migrations import ensure_schema
from iva_core.models import Company, FiscalPeriod, ThirdParty, FiscalDocument, RentWithholding, FilingAttachment
from iva_core.services.periods import get_or_create_period, is_locked, set_declared
from iva_core.services.dte import parse_dte_bytes
from iva_core.services.exports import annex1_sales_taxpayers, annex2_sales_consumer, annex3_purchases, annex5_excluded, f14_withholdings
from iva_core.services.books import make_book_df, df_to_xlsx, df_to_pdf

Base.metadata.create_all(engine)
ensure_schema(engine)
st.set_page_config(page_title='IVA SV', page_icon='🧾', layout='wide')

MONTHS={1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
DOCS=['CCF','CF','NC','ND','FSE','FEX']

APP_DIR=Path(__file__).resolve().parent
LOGO_PATH=APP_DIR / 'assets' / 'logo_plataforma_de_control_de_iva.png'

def money(x): return f"${float(x or 0):,.2f}"
def dec(x): return Decimal(str(x or 0)).quantize(Decimal('0.01'))

def render_brand_block(centered=False, width=520):
    if LOGO_PATH.exists():
        if centered:
            left, mid, right = st.columns([1,2,1])
            with mid:
                st.image(str(LOGO_PATH), width=width)
        else:
            st.image(str(LOGO_PATH), width=width)

def render_system_header(company, period):
    box = st.container()
    with box:
        c0,c1,c2=st.columns([1.2,3,1.2])
        with c0:
            if LOGO_PATH.exists():
                st.image(str(LOGO_PATH), width=260)
        with c1:
            st.markdown(f'### 🏢 {company.name}')
            meta=[]
            if company.nit: meta.append(f'**NIT:** {company.nit}')
            if company.nrc: meta.append(f'**NRC:** {company.nrc}')
            meta.append('**Sistema:** Plataforma de Control de IVA de Lecitia')
            st.caption('  |  '.join(meta))
        with c2:
            st.markdown(f'### {MONTHS[period.month]} {period.year}')
            st.caption(f'Período: {period.status}')
    st.divider()

def login():
    expected_user=os.getenv('APP_USER','admin')
    expected_hash=os.getenv('APP_PASSWORD_SHA256')
    if 'auth' not in st.session_state: st.session_state.auth=False
    if st.session_state.auth: return True
    render_brand_block(centered=True, width=560)
    st.title('IVA SV')
    st.caption('Sistema fiscal multiempresa — El Salvador')
    u=st.text_input('Usuario'); p=st.text_input('Contraseña', type='password')
    if st.button('Ingresar', type='primary'):
        ok_user=(u==expected_user)
        ok_pass=(hashlib.sha256(p.encode()).hexdigest()==expected_hash) if expected_hash else (p==os.getenv('APP_PASSWORD','cambiarme'))
        if ok_user and ok_pass:
            st.session_state.auth=True; st.rerun()
        st.error('Credenciales inválidas.')
    st.info('En producción configure APP_USER y APP_PASSWORD_SHA256 en los secrets del hosting.')
    return False

if not login(): st.stop()

db=SessionLocal()

# --- Selección / creación inicial de empresa ---
# La empresa activa se elige SIEMPRE antes de cargar el menú funcional.
companies=db.query(Company).filter_by(active=True).order_by(Company.name).all()
company_ids=[c.id for c in companies]
company_names={c.id:c.name for c in companies}

# Si la empresa seleccionada fue desactivada/eliminada, limpiar la selección.
if st.session_state.get('active_company_id') not in company_ids:
    st.session_state.pop('active_company_id',None)

# Después del login, obligar a seleccionar una empresa existente o crear una nueva.
if not st.session_state.get('active_company_id'):
    render_brand_block(centered=True, width=560)
    st.title('IVA SV')
    st.caption('Sistema fiscal multiempresa — El Salvador')
    st.subheader('Selecciona o crea la empresa con la que vas a trabajar')

    tab_existing, tab_new = st.tabs(['Seleccionar empresa', 'Crear nueva empresa'])

    with tab_existing:
        if companies:
            selected_id=st.selectbox(
                'Empresa',
                company_ids,
                format_func=lambda cid: company_names.get(cid,'Empresa'),
                key='startup_company_selector'
            )
            selected_company=db.get(Company,int(selected_id))
            if selected_company:
                details=[]
                if selected_company.nit: details.append(f'NIT: {selected_company.nit}')
                if selected_company.nrc: details.append(f'NRC: {selected_company.nrc}')
                if details: st.caption(' · '.join(details))
            if st.button('Ingresar a la empresa',type='primary',width='stretch',key='startup_enter_company'):
                st.session_state.active_company_id=int(selected_id)
                st.session_state.pop('startup_company_selector',None)
                st.rerun()
        else:
            st.info('Todavía no hay empresas registradas. Créala en la pestaña “Crear nueva empresa”.')

    with tab_new:
        with st.form('startup_new_company', clear_on_submit=False):
            name=st.text_input('Razón social *',key='startup_name')
            c1,c2=st.columns(2)
            nit=c1.text_input('NIT',key='startup_nit')
            nrc=c2.text_input('NRC',key='startup_nrc')
            act=st.text_input('Actividad económica',key='startup_activity')
            addr=st.text_input('Dirección',key='startup_address')
            sector=st.selectbox(
                'Sector renta',
                [(1,'Industria'),(2,'Comercio'),(3,'Agropecuaria'),(4,'Servicios, profesiones, artes y oficios')],
                format_func=lambda x:x[1],
                index=3,
                key='startup_sector'
            )
            create=st.form_submit_button('Crear empresa e ingresar',type='primary',width='stretch')
            if create:
                if not name.strip():
                    st.error('La razón social es obligatoria.')
                else:
                    try:
                        new_company=Company(
                            name=name.strip(),
                            nit=nit.strip(),
                            nrc=nrc.strip(),
                            economic_activity=act.strip(),
                            address=addr.strip(),
                            sector_code=sector[0]
                        )
                        db.add(new_company)
                        db.commit()
                        db.refresh(new_company)
                        st.session_state.active_company_id=int(new_company.id)
                        st.success('Empresa creada correctamente.')
                        st.rerun()
                    except IntegrityError:
                        db.rollback()
                        st.error('Ya existe una empresa con esa razón social.')
    st.stop()

# Solo después de tener empresa activa se construye el menú.
if LOGO_PATH.exists():
    st.sidebar.image(str(LOGO_PATH), width=220)
st.sidebar.title('IVA SV')
page=st.sidebar.radio('Módulo',['Inicio','Empresas','Terceros','Documentos','Retenciones F14','Importar DTE','Libros IVA','Anexos Hacienda','Declaraciones'])

active_id=int(st.session_state.active_company_id)
company=db.get(Company,active_id)
if company is None or not company.active:
    st.session_state.pop('active_company_id',None)
    st.rerun()

# Selector lateral de empresa y opción de volver a la pantalla de selección.
selected_sidebar_id=st.sidebar.selectbox(
    'Empresa activa',
    company_ids,
    index=company_ids.index(active_id),
    format_func=lambda cid: company_names.get(cid,'Empresa'),
    key='sidebar_company_selector'
)
if int(selected_sidebar_id)!=active_id:
    st.session_state.active_company_id=int(selected_sidebar_id)
    st.rerun()

if st.sidebar.button('Cambiar / crear empresa',width='stretch'):
    st.session_state.pop('active_company_id',None)
    st.session_state.pop('sidebar_company_selector',None)
    st.rerun()

c1,c2=st.sidebar.columns(2)
month=c1.selectbox('Mes',list(MONTHS),index=date.today().month-1,format_func=lambda x:MONTHS[x])
year=c2.number_input('Año',min_value=2024,max_value=2100,value=date.today().year,step=1)
period=get_or_create_period(db,company.id,int(year),int(month))
st.sidebar.caption(f'Estado: **{period.status}** | F07: {"Declarado" if period.declared_f07 else "Pendiente"} | F14: {"Declarado" if period.declared_f14 else "Pendiente"}')

# Encabezado permanente para evitar registrar movimientos en la empresa equivocada.
render_system_header(company, period)

if page=='Empresas':
    st.header('Empresas')
    with st.expander('Nueva empresa', expanded=not bool(companies)):
        with st.form('new_company'):
            name=st.text_input('Razón social *'); nit=st.text_input('NIT'); nrc=st.text_input('NRC'); act=st.text_input('Actividad económica'); addr=st.text_input('Dirección')
            sector=st.selectbox('Sector renta',[(1,'Industria'),(2,'Comercio'),(3,'Agropecuaria'),(4,'Servicios, profesiones, artes y oficios')],format_func=lambda x:x[1])
            if st.form_submit_button('Crear empresa',type='primary'):
                if not name.strip(): st.error('La razón social es obligatoria.')
                else:
                    db.add(Company(name=name.strip(),nit=nit.strip(),nrc=nrc.strip(),economic_activity=act.strip(),address=addr.strip(),sector_code=sector[0])); db.commit(); st.success('Empresa creada.'); st.rerun()
    for c in db.query(Company).order_by(Company.name).all():
        with st.expander(c.name):
            with st.form(f'edit_company_{c.id}'):
                c.name=st.text_input('Razón social',c.name,key=f'n{c.id}'); c.nit=st.text_input('NIT',c.nit,key=f'nit{c.id}'); c.nrc=st.text_input('NRC',c.nrc,key=f'nrc{c.id}')
                c.economic_activity=st.text_input('Actividad',c.economic_activity,key=f'a{c.id}'); c.address=st.text_input('Dirección',c.address,key=f'd{c.id}')
                col1,col2=st.columns(2)
                if col1.form_submit_button('Guardar'): db.commit(); st.success('Guardado.')
                deactivate=col2.form_submit_button('Desactivar')
                if deactivate: c.active=False; db.commit(); st.rerun()

elif page=='Terceros':
    st.header(f'Terceros — {company.name}')
    with st.expander('Nuevo tercero',expanded=True):
        with st.form('third_new'):
            name=st.text_input('Nombre / razón social *'); tax=st.text_input('NIT'); nrc=st.text_input('NRC'); dui=st.text_input('DUI'); domic=st.checkbox('Domiciliado',True); country=st.text_input('Código país Hacienda (4 dígitos)','9300',help='Ej.: 9300 = El Salvador. Para no domiciliados use el código oficial del país del manual F-14.')
            if st.form_submit_button('Guardar',type='primary'):
                if name.strip():
                    db.add(ThirdParty(company_id=company.id,name=name.strip(),tax_id=tax.strip(),nrc=nrc.strip(),dui=dui.strip(),domiciled=domic,country_code=country.strip().upper())); db.commit(); st.rerun()
    thirds=db.query(ThirdParty).filter_by(company_id=company.id).order_by(ThirdParty.name).all()
    for t in thirds:
        with st.expander(t.name):
            with st.form(f'th_{t.id}'):
                t.name=st.text_input('Nombre',t.name,key=f'tn{t.id}'); t.tax_id=st.text_input('NIT',t.tax_id,key=f'ti{t.id}'); t.nrc=st.text_input('NRC',t.nrc,key=f'tr{t.id}'); t.dui=st.text_input('DUI',t.dui,key=f'td{t.id}')
                c1,c2=st.columns(2)
                if c1.form_submit_button('Actualizar'): db.commit(); st.success('Actualizado.')
                if c2.form_submit_button('Eliminar'):
                    if db.query(FiscalDocument).filter_by(third_party_id=t.id).first() or db.query(RentWithholding).filter_by(third_party_id=t.id).first(): st.error('No puede eliminarse porque tiene movimientos.')
                    else: db.delete(t); db.commit(); st.rerun()

elif page=='Inicio':
    st.header(f'{company.name} — {MONTHS[period.month]} {period.year}')
    docs=db.query(FiscalDocument).filter_by(company_id=company.id,period_id=period.id).all(); wh=db.query(RentWithholding).filter_by(company_id=company.id,period_id=period.id).all()
    sales=[d for d in docs if d.operation=='VENTA']; buys=[d for d in docs if d.operation=='COMPRA']
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Ventas',money(sum(dec(d.total) for d in sales))); c2.metric('Débito IVA',money(sum(dec(d.vat) for d in sales)))
    c3.metric('Compras',money(sum(dec(d.total) for d in buys))); c4.metric('Crédito IVA',money(sum(dec(d.vat) for d in buys)))
    st.subheader('F14')
    st.metric('ISR retenido',money(sum(dec(r.withheld_amount) for r in wh)))
    st.caption('CRUD habilitado únicamente mientras el período no haya sido declarado/cerrado.')

elif page=='Documentos':
    st.header('Compras y ventas')
    locked=is_locked(period,'F07')
    if locked: st.error('Este período F-07 ya fue declarado/cerrado. Los movimientos están bloqueados.')
    thirds=db.query(ThirdParty).filter_by(company_id=company.id,active=True).order_by(ThirdParty.name).all()
    with st.expander('Registrar documento', expanded=not locked):
        with st.form('doc_new'):
            c1,c2,c3=st.columns(3); op=c1.selectbox('Operación',['COMPRA','VENTA']); dtype=c2.selectbox('Tipo',DOCS); dclass=c3.selectbox('Clase',[(4,'DTE'),(1,'Impreso'),(2,'Formulario único'),(3,'Otros')],format_func=lambda x:x[1])
            c1,c2=st.columns(2); issue=c1.date_input('Fecha',date(period.year,period.month,1)); third=c2.selectbox('Tercero',[None]+thirds,format_func=lambda x:'—' if x is None else x.name)
            c1,c2,c3=st.columns(3); docno=c1.text_input('Número documento/control'); gen=c2.text_input('Código generación'); related=c3.text_input('Documento relacionado (NC/ND)')
            desc=st.text_input('Concepto')
            c1,c2,c3,c4,c5=st.columns(5); exempt=c1.number_input('Exento',0.0,step=0.01); non=c2.number_input('No sujeto',0.0,step=0.01); taxable=c3.number_input('Gravado',0.0,step=0.01); vat=c4.number_input('IVA',0.0,step=0.01); total=c5.number_input('Total',0.0,step=0.01)
            c1,c2=st.columns(2); ivaret=c1.number_input('Retención IVA',0.0,step=0.01); ivaper=c2.number_input('Percepción IVA',0.0,step=0.01)
            st.markdown('**Clasificación renta/costo-gasto**')
            c1,c2,c3,c4=st.columns(4); rop=c1.selectbox('Tipo operación',[1,2,3,4],format_func=lambda x:{1:'Gravada',2:'No gravada/exenta',3:'Excluida/no renta',4:'Mixta'}[x]); clas=c2.selectbox('Clasificación',[1,2],format_func=lambda x:{1:'Costo',2:'Gasto'}[x]); sec=c3.selectbox('Sector',[1,2,3,4],index=max(0,company.sector_code-1),format_func=lambda x:{1:'Industria',2:'Comercio',3:'Agropecuaria',4:'Servicios'}[x]); cg=c4.selectbox('Tipo costo/gasto',[1,2,3,4,5,6,7],format_func=lambda x:{1:'Venta',2:'Administración',3:'Financiero',4:'Costo importado',5:'Costo interno',6:'CIF',7:'Mano de obra'}[x])
            income=st.number_input('Tipo de ingreso renta (ventas)',min_value=1,max_value=13,value=2,step=1)
            if st.form_submit_button('Guardar documento',type='primary',disabled=locked):
                if dtype in ('NC','ND') and not related.strip(): st.error('NC/ND requiere documento relacionado.')
                else:
                    d=FiscalDocument(company_id=company.id,period_id=period.id,third_party_id=third.id if third else None,operation=op,doc_type=dtype,doc_class=dclass[0],issue_date=issue,document_no=docno.strip(),internal_control=docno.strip(),generation_code=gen.strip(),related_document=related.strip(),exempt=dec(exempt),non_taxable=dec(non),taxable=dec(taxable),vat=dec(vat),total=dec(total),iva_withholding=dec(ivaret),iva_perception=dec(ivaper),rent_operation_code=rop,income_type_code=int(income),classification_code=clas,sector_code=sec,cost_expense_code=cg,description=desc.strip())
                    db.add(d)
                    try: db.commit(); st.success('Documento guardado.'); st.rerun()
                    except IntegrityError: db.rollback(); st.error('Documento duplicado: revise el código de generación.')
    docs=db.query(FiscalDocument).filter_by(company_id=company.id,period_id=period.id).order_by(FiscalDocument.issue_date.desc(),FiscalDocument.id.desc()).all()
    for d in docs:
        with st.expander(f'{d.issue_date} | {d.operation} | {d.doc_type} | {d.document_no} | {money(d.total)}'):
            with st.form(f'edit_doc_{d.id}'):
                e1,e2,e3=st.columns(3)
                d.issue_date=e1.date_input('Fecha',d.issue_date,key=f'edate{d.id}',disabled=locked or d.locked)
                d.document_no=e2.text_input('Documento',d.document_no,key=f'eno{d.id}',disabled=locked or d.locked)
                d.generation_code=e3.text_input('Código generación',d.generation_code,key=f'egen{d.id}',disabled=locked or d.locked)
                d.description=st.text_input('Concepto',d.description,key=f'edesc{d.id}',disabled=locked or d.locked)
                e1,e2,e3,e4,e5=st.columns(5)
                ex=e1.number_input('Exento',0.0,value=float(d.exempt or 0),step=0.01,key=f'eex{d.id}',disabled=locked or d.locked)
                ns=e2.number_input('No sujeto',0.0,value=float(d.non_taxable or 0),step=0.01,key=f'ens{d.id}',disabled=locked or d.locked)
                gr=e3.number_input('Gravado',0.0,value=float(d.taxable or 0),step=0.01,key=f'egr{d.id}',disabled=locked or d.locked)
                iv=e4.number_input('IVA',0.0,value=float(d.vat or 0),step=0.01,key=f'eiv{d.id}',disabled=locked or d.locked)
                tt=e5.number_input('Total',0.0,value=float(d.total or 0),step=0.01,key=f'ett{d.id}',disabled=locked or d.locked)
                c1,c2=st.columns(2)
                if c1.form_submit_button('Actualizar',disabled=locked or d.locked):
                    d.exempt=dec(ex); d.non_taxable=dec(ns); d.taxable=dec(gr); d.vat=dec(iv); d.total=dec(tt)
                    try: db.commit(); st.success('Documento actualizado.'); st.rerun()
                    except IntegrityError: db.rollback(); st.error('Código de generación duplicado.')
                if c2.form_submit_button('Eliminar',disabled=locked or d.locked):
                    db.delete(d); db.commit(); st.rerun()

elif page=='Retenciones F14':
    st.header('Retenciones de renta — F14')
    locked=is_locked(period,'F14')
    if locked: st.error('F-14 ya declarado/cerrado. Registros bloqueados.')
    thirds=db.query(ThirdParty).filter_by(company_id=company.id,active=True).order_by(ThirdParty.name).all()
    docs=db.query(FiscalDocument).filter_by(company_id=company.id,period_id=period.id,operation='COMPRA').all()
    with st.expander('Registrar retención',expanded=not locked):
        with st.form('f14new'):
            third=st.selectbox('Sujeto retenido',[None]+thirds,format_func=lambda x:'—' if x is None else x.name); doc=st.selectbox('Documento relacionado',[None]+docs,format_func=lambda x:'—' if x is None else f'{x.doc_type} {x.document_no}')
            c1,c2,c3=st.columns(3); code=c1.text_input('Código de ingreso','11'); accrued=c2.number_input('Monto devengado',0.0,step=0.01); withheld=c3.number_input('ISR retenido',0.0,step=0.01)
            c1,c2,c3,c4=st.columns(4); domic=c1.checkbox('Domiciliado',True); country=c2.text_input('Código país','9300',help='Código de 4 dígitos según catálogo oficial F-14'); op=c3.selectbox('Tipo operación',[1,2,3,4],format_func=lambda x:{1:'Gravada',2:'No gravada',3:'Excluida/no renta',4:'Mixta'}[x]); clas=c4.selectbox('Clasificación',[1,2],index=1,format_func=lambda x:{1:'Costo',2:'Gasto'}[x])
            c1,c2=st.columns(2); sec=c1.selectbox('Sector',[1,2,3,4],index=max(0,company.sector_code-1),format_func=lambda x:{1:'Industria',2:'Comercio',3:'Agropecuaria',4:'Servicios, profesiones, artes y oficios'}[x]); cg=c2.selectbox('Costo/Gasto',[1,2,3,4,5,6,7],index=1,format_func=lambda x:{1:'Gastos de venta sin donación',2:'Gastos de administración sin donación',3:'Gastos financieros sin donación',4:'Costo artículos producidos/comprados importaciones',5:'Costo artículos producidos/comprados interno',6:'Costos indirectos de fabricación',7:'Mano de obra'}[x])
            st.markdown('**Campos adicionales F-14 V16**')
            a1,a2,a3=st.columns(3); bonus=a1.number_input('Bonificaciones/gratificaciones',0.0,step=0.01); agex=a2.number_input('Aguinaldo exento',0.0,step=0.01); aggr=a3.number_input('Aguinaldo gravado',0.0,step=0.01)
            b1,b2,b3,b4=st.columns(4); afp=b1.number_input('AFP',0.0,step=0.01); isss=b2.number_input('ISSS',0.0,step=0.01); inpep=b3.number_input('INPEP',0.0,step=0.01); ipsfa=b4.number_input('IPSFA',0.0,step=0.01)
            c1,c2,c3=st.columns(3); cefafa=c1.number_input('CEFAFA',0.0,step=0.01); bienestar=c2.number_input('Bienestar Magisterial',0.0,step=0.01); isssivm=c3.number_input('ISSS IVM',0.0,step=0.01)
            if st.form_submit_button('Guardar retención',type='primary',disabled=locked):
                if not code.strip().isdigit() or len(code.strip())>2:
                    st.error('El código de ingreso F-14 debe ser numérico de hasta 2 caracteres.')
                elif not country.strip().isdigit() or len(country.strip())>4:
                    st.error('El código de país debe ser numérico de hasta 4 caracteres.')
                else:
                    r=RentWithholding(company_id=company.id,period_id=period.id,document_id=doc.id if doc else None,third_party_id=third.id if third else None,domiciled=domic,country_code=country.strip(),income_code=code.strip().zfill(2),accrued_amount=dec(accrued),bonus_amount=dec(bonus),withheld_amount=dec(withheld),aguinaldo_exempt=dec(agex),aguinaldo_taxable=dec(aggr),afp=dec(afp),isss=dec(isss),inpep=dec(inpep),ipsfa=dec(ipsfa),cefafa=dec(cefafa),bienestar_magisterial=dec(bienestar),isss_ivm=dec(isssivm),operation_code=op,classification_code=clas,sector_code=sec,cost_expense_code=cg)
                    db.add(r); db.commit(); st.rerun()
                    r=None
    items=db.query(RentWithholding).filter_by(company_id=company.id,period_id=period.id).all()
    for r in items:
        t=db.get(ThirdParty,r.third_party_id) if r.third_party_id else None
        with st.expander(f'{t.name if t else "Sin tercero"} | Cód. {r.income_code} | {money(r.withheld_amount)}'):
            with st.form(f'edit_r_{r.id}'):
                c1,c2,c3=st.columns(3)
                r.income_code=c1.text_input('Código ingreso',r.income_code,key=f'ric{r.id}',disabled=locked or r.locked)
                acc=c2.number_input('Monto devengado',0.0,value=float(r.accrued_amount or 0),step=0.01,key=f'rac{r.id}',disabled=locked or r.locked)
                whv=c3.number_input('ISR retenido',0.0,value=float(r.withheld_amount or 0),step=0.01,key=f'rwh{r.id}',disabled=locked or r.locked)
                x1,x2,x3=st.columns(3)
                bonus=x1.number_input('Bonificaciones',0.0,value=float(r.bonus_amount or 0),step=0.01,key=f'rbo{r.id}',disabled=locked or r.locked)
                agex=x2.number_input('Aguinaldo exento',0.0,value=float(r.aguinaldo_exempt or 0),step=0.01,key=f'rae{r.id}',disabled=locked or r.locked)
                aggr=x3.number_input('Aguinaldo gravado',0.0,value=float(r.aguinaldo_taxable or 0),step=0.01,key=f'rag{r.id}',disabled=locked or r.locked)
                y1,y2,y3,y4=st.columns(4)
                afp=y1.number_input('AFP',0.0,value=float(r.afp or 0),step=0.01,key=f'rafp{r.id}',disabled=locked or r.locked)
                isss=y2.number_input('ISSS',0.0,value=float(r.isss or 0),step=0.01,key=f'risss{r.id}',disabled=locked or r.locked)
                inpep=y3.number_input('INPEP',0.0,value=float(r.inpep or 0),step=0.01,key=f'rinp{r.id}',disabled=locked or r.locked)
                ipsfa=y4.number_input('IPSFA',0.0,value=float(r.ipsfa or 0),step=0.01,key=f'rips{r.id}',disabled=locked or r.locked)
                z1,z2,z3=st.columns(3)
                cefafa=z1.number_input('CEFAFA',0.0,value=float(r.cefafa or 0),step=0.01,key=f'rcef{r.id}',disabled=locked or r.locked)
                bienestar=z2.number_input('Bienestar Magisterial',0.0,value=float(r.bienestar_magisterial or 0),step=0.01,key=f'rbie{r.id}',disabled=locked or r.locked)
                isssivm=z3.number_input('ISSS IVM',0.0,value=float(r.isss_ivm or 0),step=0.01,key=f'rivm{r.id}',disabled=locked or r.locked)
                b1,b2=st.columns(2)
                if b1.form_submit_button('Actualizar',disabled=locked or r.locked):
                    r.accrued_amount=dec(acc); r.withheld_amount=dec(whv); r.bonus_amount=dec(bonus); r.aguinaldo_exempt=dec(agex); r.aguinaldo_taxable=dec(aggr); r.afp=dec(afp); r.isss=dec(isss); r.inpep=dec(inpep); r.ipsfa=dec(ipsfa); r.cefafa=dec(cefafa); r.bienestar_magisterial=dec(bienestar); r.isss_ivm=dec(isssivm); db.commit(); st.rerun()
                if b2.form_submit_button('Eliminar',disabled=locked or r.locked):
                    db.delete(r); db.commit(); st.rerun()

elif page=='Importar DTE':
    st.header('Importar DTE JSON')
    locked=is_locked(period,'F07')
    files=st.file_uploader('Arrastre archivos JSON',type=['json'],accept_multiple_files=True,disabled=locked)
    op=st.radio('Interpretar como',['COMPRA','VENTA'],horizontal=True,disabled=locked)
    if files and st.button('Analizar',disabled=locked):
        parsed=[]
        for f in files:
            try:
                p=parse_dte_bytes(f.getvalue()); p['filename']=f.name; parsed.append(p)
            except Exception as e: st.error(f'{f.name}: {e}')
        st.session_state['parsed_dtes']=parsed
    parsed=st.session_state.get('parsed_dtes',[])
    if parsed:
        st.dataframe(pd.DataFrame([{k:v for k,v in p.items() if k not in ('raw',)} for p in parsed]),width='stretch')
        if st.button(f'Importar {len(parsed)} DTE',type='primary',disabled=locked):
            imported=0; skipped=0
            for p in parsed:
                name=p['third_name_purchase'] if op=='COMPRA' else p['third_name_sale']; tax=p['third_nit_purchase'] if op=='COMPRA' else p['third_nit_sale']; nrc=p['third_nrc_purchase'] if op=='COMPRA' else p['third_nrc_sale']
                t=db.query(ThirdParty).filter_by(company_id=company.id,tax_id=tax,name=name).first()
                if not t:
                    t=ThirdParty(company_id=company.id,name=name or 'SIN IDENTIFICAR',tax_id=tax,nrc=nrc); db.add(t); db.flush()
                exists=db.query(FiscalDocument).filter_by(company_id=company.id,generation_code=p['generation_code']).first()
                if exists: skipped+=1; continue
                d=FiscalDocument(company_id=company.id,period_id=period.id,third_party_id=t.id,operation=op,doc_type=p['doc_type'],doc_class=4,issue_date=p['issue_date'],document_no=p['document_no'],internal_control=p['internal_control'],generation_code=p['generation_code'],exempt=p['exempt'],non_taxable=p['non_taxable'],taxable=p['taxable'],vat=p['vat'],total=p['total'],iva_withholding=p['iva_withholding'],description=f'Importado de {p["filename"]}',source='JSON')
                db.add(d); imported+=1
                if p['rent_withholding']>0 and op=='COMPRA': db.add(RentWithholding(company_id=company.id,period_id=period.id,document_id=None,third_party_id=t.id,domiciled=t.domiciled,country_code=t.country_code or '9300',income_code='11',accrued_amount=p['taxable'],withheld_amount=p['rent_withholding'],classification_code=2,sector_code=company.sector_code,cost_expense_code=2))
            db.commit(); st.success(f'Importados: {imported}. Omitidos por duplicado: {skipped}.'); del st.session_state['parsed_dtes']; st.rerun()

elif page=='Libros IVA':
    st.header('Libros IVA')
    st.caption('Seleccione el período que desea consultar y generar. Este selector no modifica el período activo de captura.')

    sel1,sel2=st.columns(2)
    book_month=sel1.selectbox('Mes del libro',list(MONTHS),index=period.month-1,format_func=lambda x:MONTHS[x],key='book_month')
    book_year=int(sel2.number_input('Año del libro',min_value=2024,max_value=2100,value=int(period.year),step=1,key='book_year'))

    book_period=get_or_create_period(db,company.id,book_year,int(book_month))
    docs=db.query(FiscalDocument).filter_by(company_id=company.id,period_id=book_period.id).order_by(FiscalDocument.issue_date,FiscalDocument.id).all()
    thirds={t.id:t for t in db.query(ThirdParty).filter_by(company_id=company.id).all()}

    book_options={
        'COMPRAS':'Libro de Compras',
        'VENTAS_CCF':'Libro de Ventas a Contribuyentes',
        'VENTAS_CF':'Libro de Ventas a Consumidor Final'
    }
    kind=st.selectbox('Libro a generar',list(book_options),format_func=lambda x:book_options[x])
    df=make_book_df(docs,thirds,kind)
    period_label=f'{MONTHS[int(book_month)]} {book_year}'
    book_name=book_options[kind].upper()

    st.markdown(f'**Nombre o Razón Social:** {company.name}')
    info1,info2,info3=st.columns(3)
    info1.write(f'**NRC / Número de IVA (RUC):** {company.nrc or "—"}')
    info2.write(f'**NIT:** {company.nit or "—"}')
    info3.write(f'**Período:** {period_label}')
    st.dataframe(df,width='stretch')

    excel_bytes=df_to_xlsx(df,company.name,company.nrc,company.nit,period_label,book_name)
    pdf_bytes=df_to_pdf(df,company.name,company.nrc,company.nit,period_label,book_name)
    safe_company=''.join(ch if ch.isalnum() or ch in (' ','-','_') else '_' for ch in company.name).strip().replace(' ','_')
    c1,c2=st.columns(2)
    c1.download_button('Descargar Excel',excel_bytes,f'{safe_company}_{book_year}_{int(book_month):02d}_{kind}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',width='stretch')
    c2.download_button('Descargar PDF',pdf_bytes,f'{safe_company}_{book_year}_{int(book_month):02d}_{kind}.pdf',mime='application/pdf',width='stretch')

elif page=='Anexos Hacienda':
    st.header('Anexos para Hacienda')
    docs=db.query(FiscalDocument).filter_by(company_id=company.id,period_id=period.id).order_by(FiscalDocument.issue_date).all(); thirds={t.id:t for t in db.query(ThirdParty).filter_by(company_id=company.id).all()}; wh=db.query(RentWithholding).filter_by(company_id=company.id,period_id=period.id).all()
    st.info('Los CSV se generan sin encabezados y con estructura de columnas según los manuales oficiales F-07 V14 (enero 2025) y F-14 V16 (octubre 2025).')
    exports=[('Anexo 1 - Ventas contribuyentes',annex1_sales_taxpayers(docs,thirds),'anexo1.csv'),('Anexo 2 - Ventas consumidor final',annex2_sales_consumer(docs),'anexo2.csv'),('Anexo 3 - Compras contribuyentes',annex3_purchases(docs,thirds),'anexo3.csv'),('Anexo 5 - Sujetos excluidos',annex5_excluded(docs,thirds),'anexo5.csv'),('Anexo retenciones F14 V16',f14_withholdings(wh,thirds,f'{period.month:02d}{period.year}'),f'F14_{period.month:02d}{period.year}.csv')]
    for label,data,name in exports: st.download_button(label,data,name,mime='text/csv',width='stretch')
    st.success('F-14 alineado al Manual de Usuario V16 (octubre 2025): 23 columnas A-W, sin encabezados, incluyendo CEFAFA, Bienestar Magisterial, ISSS IVM y período MMYYYY.')

elif page=='Declaraciones':
    st.header('Declaraciones y cierre')
    st.write(f'**Período:** {MONTHS[period.month]} {period.year}')
    c1,c2=st.columns(2); c1.metric('F-07','DECLARADO' if period.declared_f07 else 'PENDIENTE'); c2.metric('F-14','DECLARADO' if period.declared_f14 else 'PENDIENTE')
    with st.form('declare'):
        f07=st.checkbox('Marcar F-07 como declarado',value=period.declared_f07,disabled=period.declared_f07); no7=st.text_input('N.º declaración F-07',period.f07_declaration_no,disabled=period.declared_f07)
        f14=st.checkbox('Marcar F-14 como declarado',value=period.declared_f14,disabled=period.declared_f14); no14=st.text_input('N.º declaración F-14',period.f14_declaration_no,disabled=period.declared_f14)
        confirm=st.checkbox('Confirmo que deseo bloquear los movimientos declarados')
        if st.form_submit_button('Guardar declaración / bloquear',type='primary'):
            if not confirm: st.error('Debe confirmar el bloqueo.')
            else: set_declared(db,period,f07,f14,no7,no14); st.success('Declaración registrada. Los movimientos quedaron bloqueados.'); st.rerun()
    st.subheader('Expediente')
    uploads=st.file_uploader('Adjuntar declaración, NPE o comprobante',accept_multiple_files=True)
    if uploads and st.button('Guardar adjuntos'):
        for f in uploads: db.add(FilingAttachment(company_id=company.id,period_id=period.id,kind='DECLARACION',filename=f.name,content=f.getvalue()))
        db.commit(); st.success('Adjuntos guardados.')

