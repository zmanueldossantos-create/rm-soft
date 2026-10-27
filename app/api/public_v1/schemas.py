"""The public API's answers and requests: field names in English, descriptions (shown in the documentation) in PT."""
import uuid
from datetime import date, datetime
from datetime import date as Day  # a field is called «date» below
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.customer import _validate_email, _validate_name, _validate_nif, _validate_phone


class Page(BaseModel):
    page: int = Field(description="Página pedida (a primeira é 1)")
    page_size: int = Field(description="Linhas por página (máximo 200)")
    total: int = Field(description="Total de linhas que correspondem ao filtro")


class SaleUnit(BaseModel):
    id: str
    unit: str = Field(description="Unidade de venda (ex.: CX, PAC)")
    factor: float = Field(description="Quantas unidades base contém")
    price: float | None = Field(description="Preço sem IVA desta unidade")
    barcode: str | None


class WarehouseStock(BaseModel):
    warehouse_id: str
    warehouse: str
    quantity: float


class Product(BaseModel):
    id: str
    code: str
    name: str
    brand: str | None
    barcode: str | None
    category: str | None
    unit: str | None = Field(description="Unidade base (ex.: UN, KG)")
    price: float | None = Field(description="Preço sem IVA, em Kz")
    vat_rate: float = Field(description="Taxa de IVA em % (0, 5 ou 14)")
    vat_category: str | None = Field(description="NOR, RED, ISE...")
    price_with_vat: float | None = Field(description="Preço com IVA, o que o cliente paga")
    status: str = Field(description="ACTIVO ou ESGOTADO")
    stock: float | None = Field(description="Quantidade em stock (todos os armazéns); null: sem controlo de stock")
    sale_units: list[SaleUnit] = Field(description="Outras unidades de venda (caixa, pacote...)")
    image: str | None = Field(description="Caminho da imagem, a juntar ao endereço do servidor")
    updated_at: datetime | None
    stock_by_warehouse: list[WarehouseStock] | None = Field(default=None, description="Só no detalhe de um produto")


class ProductPage(Page):
    items: list[Product]


class Category(BaseModel):
    id: str
    name: str


class Service(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    type: str | None = Field(description="Tipo de serviço")
    unit: str | None
    duration_minutes: int | None
    price: float | None = Field(description="Preço sem IVA, em Kz")
    vat_rate: float
    vat_category: str | None
    price_with_vat: float | None
    status: str
    updated_at: datetime | None


class ServicePage(Page):
    items: list[Service]


class Customer(BaseModel):
    id: str
    code: str | None
    name: str
    nif: str
    person_type: str = Field(description="FISICA (particular) ou JURIDICA (empresa)")
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None


class CustomerPage(Page):
    items: list[Customer]


class CustomerCreate(BaseModel):
    name: str = Field(description="Nome do cliente", examples=["Maria Domingos"])
    nif: str = Field(description="NIF (empresa) ou n.º do BI (particular), pelo menos 9 caracteres",
                     examples=["004567890LA041"])
    person_type: str = Field(default="FISICA", description="FISICA (particular) ou JURIDICA (empresa)")
    phone: str | None = Field(default=None, description="Formato internacional", examples=["+244923456789"])
    email: str | None = None
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)

    _name = field_validator("name")(lambda cls, v: _validate_name(v))
    _nif = field_validator("nif")(lambda cls, v: _validate_nif(v))
    _phone = field_validator("phone")(lambda cls, v: _validate_phone(v))
    _email = field_validator("email")(lambda cls, v: _validate_email(v))

    @field_validator("person_type")
    @classmethod
    def _person_type(cls, v: str) -> str:
        v = (v or "FISICA").strip().upper()
        if v not in ("FISICA", "JURIDICA"):
            raise ValueError("person_type: FISICA ou JURIDICA")
        return v


class AlreadyExists(BaseModel):
    detail: str
    id: str = Field(description="O cliente que já existe com este NIF")


# -------------------------------------------------------------------------------------------------------- documents

class Activity(BaseModel):
    id: str
    name: str


class DocumentLineIn(BaseModel):
    product_id: uuid.UUID | None = Field(default=None, description="Um produto do catálogo...")
    service_id: uuid.UUID | None = Field(default=None, description="...ou um serviço (só um dos dois)")
    quantity: float = Field(gt=0, le=1_000_000, examples=[2])
    sale_unit_id: uuid.UUID | None = Field(default=None, description="Vender noutra unidade (caixa...): sale_units[].id")
    discount_percent: float = Field(default=0, ge=0, le=100, description="Desconto da linha, em %")


class DocumentCreate(BaseModel):
    type: Literal["FT", "FR", "FP"] = Field(description="FT Fatura (paga depois), FR Fatura/Recibo (paga já), "
                                                         "FP Fatura Pro-forma (orçamento, não fiscal)")
    lines: list[DocumentLineIn] = Field(min_length=1, max_length=200)
    customer_id: uuid.UUID | None = Field(default=None, description="Sem cliente: consumidor final")
    activity_id: uuid.UUID | None = Field(default=None, description="Só se a empresa tiver várias atividades")
    payment_method: str | None = Field(default=None, max_length=4,
                                       description="Código AGT do meio de pagamento: obrigatório numa FR "
                                                   "(MB Multicaixa, TB transferência, CC/CD cartão, DE dinheiro "
                                                   "eletrónico). Numerário não: só na caixa.")
    due_date: date | None = Field(default=None, description="Vencimento de uma FT")
    document_reference: str | None = Field(default=None, max_length=100,
                                           description="A sua referência (n.º da encomenda no site)")
    observations: str | None = Field(default=None, max_length=500)


class DocumentCustomer(BaseModel):
    id: str
    name: str
    nif: str


class DocumentAgt(BaseModel):
    status: str = Field(description="PENDENTE, POR_ENVIAR, ENVIADA ou ERRO")
    label: str
    atcud: str | None


class DocumentLine(BaseModel):
    product_id: str | None
    service_id: str | None
    name: str
    quantity: float
    unit: str | None
    unit_price: float | None = Field(description="Preço unitário sem IVA")
    discount_percent: float
    vat_rate: float
    subtotal: float | None = Field(description="Sem IVA, desconto deduzido")
    vat: float | None
    total: float | None


class Document(BaseModel):
    id: str
    type: str = Field(description="FT, FR, FP, NC, ND, RC ou OR")
    number: str = Field(description="Ex.: FT A2026/15")
    date: Day
    activity_id: str
    customer: DocumentCustomer | None
    document_reference: str | None
    observations: str | None
    subtotal: float | None
    vat_total: float | None
    retention_total: float | None
    total: float | None = Field(description="Total com IVA")
    amount_due: float | None = Field(description="Ainda por pagar (FT)")
    due_date: Day | None
    status: str = Field(description="EMITIDO, ANULADO, RECTIFICADO...")
    converted_to_invoice_id: str | None = Field(description="FP já faturada: a fatura")
    agt: DocumentAgt | None = Field(description="Estado na AGT (null: documento não fiscal, ou emitido em modo manual - comunicado pelo SAF-T)")
    pdf: str = Field(description="Caminho do PDF")
    created_at: datetime | None
    updated_at: datetime | None
    lines: list[DocumentLine] | None = Field(default=None, description="Só no detalhe e na criação")


class DocumentPage(Page):
    items: list[Document]
