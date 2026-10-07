from datetime import datetime
from sqlalchemy.orm import Session
from iva_core.models import FiscalPeriod, FiscalDocument, RentWithholding

def get_or_create_period(db: Session, company_id: int, year: int, month: int) -> FiscalPeriod:
    p = db.query(FiscalPeriod).filter_by(company_id=company_id, year=year, month=month).first()
    if not p:
        p = FiscalPeriod(company_id=company_id, year=year, month=month)
        db.add(p); db.commit(); db.refresh(p)
    return p

def is_locked(period: FiscalPeriod, module: str = "ANY") -> bool:
    if period.status == "CERRADO":
        return True
    if module == "F07":
        return period.declared_f07
    if module == "F14":
        return period.declared_f14
    return period.declared_f07 or period.declared_f14 or period.status == "DECLARADO"

def set_declared(db: Session, period: FiscalPeriod, f07: bool, f14: bool, no_f07="", no_f14=""):
    if f07:
        period.declared_f07 = True
        period.f07_declaration_no = no_f07
    if f14:
        period.declared_f14 = True
        period.f14_declaration_no = no_f14
    period.declared_at = datetime.utcnow()
    if period.declared_f07 and period.declared_f14:
        period.status = "DECLARADO"
    db.query(FiscalDocument).filter_by(period_id=period.id).update({FiscalDocument.locked: True})
    db.query(RentWithholding).filter_by(period_id=period.id).update({RentWithholding.locked: True})
    db.commit()
