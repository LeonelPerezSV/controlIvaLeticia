from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, Boolean, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    nit: Mapped[str] = mapped_column(String(20), default="")
    nrc: Mapped[str] = mapped_column(String(20), default="")
    economic_activity: Mapped[str] = mapped_column(String(250), default="")
    address: Mapped[str] = mapped_column(String(350), default="")
    sector_code: Mapped[int] = mapped_column(Integer, default=4)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"
    __table_args__ = (UniqueConstraint("company_id", "year", "month", name="uq_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="ABIERTO")
    declared_f07: Mapped[bool] = mapped_column(Boolean, default=False)
    declared_f14: Mapped[bool] = mapped_column(Boolean, default=False)
    declared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    f07_declaration_no: Mapped[str] = mapped_column(String(80), default="")
    f14_declaration_no: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

class ThirdParty(Base):
    __tablename__ = "third_parties"
    __table_args__ = (UniqueConstraint("company_id", "tax_id", "name", name="uq_third_party"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(20), default="")
    nrc: Mapped[str] = mapped_column(String(20), default="")
    dui: Mapped[str] = mapped_column(String(12), default="")
    country_code: Mapped[str] = mapped_column(String(4), default="9300")
    domiciled: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class FiscalDocument(Base):
    __tablename__ = "fiscal_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "generation_code", name="uq_generation_code"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    period_id: Mapped[int] = mapped_column(ForeignKey("fiscal_periods.id", ondelete="RESTRICT"))
    third_party_id: Mapped[int | None] = mapped_column(ForeignKey("third_parties.id", ondelete="SET NULL"), nullable=True)
    operation: Mapped[str] = mapped_column(String(10))  # COMPRA / VENTA
    doc_type: Mapped[str] = mapped_column(String(10))   # CCF / CF / NC / ND / FSE / FEX
    doc_class: Mapped[int] = mapped_column(Integer, default=4)  # 1 imprenta, 2 form unico, 3 otros, 4 DTE
    issue_date: Mapped[date] = mapped_column(Date)
    resolution_no: Mapped[str] = mapped_column(String(100), default="0")
    series: Mapped[str] = mapped_column(String(100), default="0")
    document_no: Mapped[str] = mapped_column(String(100), default="")
    internal_control: Mapped[str] = mapped_column(String(100), default="")
    generation_code: Mapped[str] = mapped_column(String(100), default="")
    related_document: Mapped[str] = mapped_column(String(100), default="")
    exempt: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    non_taxable: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    taxable: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    vat: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    iva_withholding: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    iva_perception: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    rent_operation_code: Mapped[int] = mapped_column(Integer, default=1)
    income_type_code: Mapped[int] = mapped_column(Integer, default=2)
    classification_code: Mapped[int] = mapped_column(Integer, default=2)
    sector_code: Mapped[int] = mapped_column(Integer, default=4)
    cost_expense_code: Mapped[int] = mapped_column(Integer, default=2)
    description: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(20), default="MANUAL")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RentWithholding(Base):
    __tablename__ = "rent_withholdings"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    period_id: Mapped[int] = mapped_column(ForeignKey("fiscal_periods.id", ondelete="RESTRICT"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("fiscal_documents.id", ondelete="SET NULL"), nullable=True)
    third_party_id: Mapped[int | None] = mapped_column(ForeignKey("third_parties.id", ondelete="SET NULL"), nullable=True)
    domiciled: Mapped[bool] = mapped_column(Boolean, default=True)
    country_code: Mapped[str] = mapped_column(String(4), default="9300")
    income_code: Mapped[str] = mapped_column(String(10), default="")
    accrued_amount: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    withheld_amount: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    aguinaldo_exempt: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    aguinaldo_taxable: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    afp: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    isss: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    inpep: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    ipsfa: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    cefafa: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    bienestar_magisterial: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    isss_ivm: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0)
    classification_code: Mapped[int] = mapped_column(Integer, default=2)
    sector_code: Mapped[int] = mapped_column(Integer, default=4)
    cost_expense_code: Mapped[int] = mapped_column(Integer, default=2)
    operation_code: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str] = mapped_column(Text, default="")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class FilingAttachment(Base):
    __tablename__ = "filing_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    period_id: Mapped[int] = mapped_column(ForeignKey("fiscal_periods.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30), default="OTRO")
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
