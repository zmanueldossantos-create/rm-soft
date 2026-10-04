"""
Central import point for all SQLAlchemy models.
Ensures every model is registered with SQLAlchemy before use
(avoids NoReferencedTableError on foreign keys).
Import once at application startup (see app/main.py).
"""
from app.models.company import Company
from app.models.user import User
from app.models.vat import VAT
from app.models.product import Product
from app.models.product_sale_unit import ProductSaleUnit
from app.models.customer import Customer, CustomerStatus
from app.models.supplier import Supplier
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.fiscal_year import FiscalYear
from app.models.fiscal_period import FiscalPeriod
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.warehouse import Warehouse
from app.models.stock import Stock
from app.models.stock_movement import StockMovement
from app.models.platform_settings import PlatformSettings
from app.models.fiscal_regime import FiscalRegime
from app.models.module import Module
from app.models.company_module import CompanyModule
from app.models.activity import Activity
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.consumption_reason_catalog import ConsumptionReasonCatalog
from app.models.internal_consumption import InternalConsumption
from app.models.resource import Resource
from app.models.open_account import OpenAccount
from app.models.open_account_line import OpenAccountLine
from app.models.booking import Booking
from app.models.recipe_ingredient import RecipeIngredient
from app.models.cash_session import CashSession
from app.models.payment import Payment
from app.models.country import Country
from app.models.currency import Currency
from app.models.province import Province
from app.models.municipality import Municipality
from app.models.bank import Bank
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.company_payment_method_preference import CompanyPaymentMethodPreference
from app.models.company_document_type_preference import CompanyDocumentTypePreference
from app.models.payment_term import PaymentTerm
from app.models.vat_code import VatCode
from app.models.document_type import DocumentType
from app.models.movement_type import MovementType
from app.models.movement_series import MovementSeries
from app.models.stock_movement_document import StockMovementDocument, StockMovementDocumentLine
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.withholding_tax import WithholdingTax
from app.models.company_bank_account import CompanyBankAccount
from app.models.customer_bank_account_link import CustomerBankAccountLink
from app.models.product_category import ProductCategory
from app.models.service_type import ServiceType
from app.models.service import Service, ProductServiceStatus
from app.models.establishment import Establishment
from app.models.document_series import DocumentSeries, ContingencyIndicator
from app.models.point_of_sale import PointOfSale
from app.models.cash_movement_reason import CashMovementReason
from app.models.cash_movement import CashMovement, CashMovementType
from app.models.user_cash_point_access import UserCashPointAccess
from app.models.denomination import Denomination, DenominationType
from app.models.cash_denomination_count import CashDenominationCount, CashDenominationCountLine, DenominationCountType

__all__ = [
    "Company", "User", "VAT", "Product", "Customer", "CustomerStatus", "Supplier", "Permission", "RolePermission",
    "FiscalYear", "FiscalPeriod", "Invoice", "InvoiceLine",
    "CompanyDocumentTypePreference", "Warehouse", "Stock", "StockMovement", "ResourceTypeCatalog", "ConsumptionReasonCatalog", "InternalConsumption", "Resource", "Booking", "OpenAccount", "OpenAccountLine", "PlatformSettings", "FiscalRegime", "Activity", "RecipeIngredient", "CashSession", "Payment", "Country", "Currency", "Province", "Municipality", "Bank", "PaymentMethodCatalog", "CompanyPaymentMethodPreference", "PaymentTerm", "VatCode", "DocumentType", "UnitOfMeasureCatalog", "WithholdingTax", "CompanyBankAccount", "CustomerBankAccountLink", "ProductCategory", "ServiceType", "Service", "ProductServiceStatus", "Establishment", "DocumentSeries", "ContingencyIndicator", "Module", "CompanyModule", "PointOfSale", "CashMovementReason", "CashMovement", "CashMovementType", "UserCashPointAccess", "Denomination", "DenominationType", "CashDenominationCount", "CashDenominationCountLine", "DenominationCountType",
]
from app.models.company_permission_seed import CompanyPermissionSeed  # noqa: F401
from app.models.open_account_transfer import OpenAccountTransfer  # noqa: F401
from app.models.module_capability import ModuleCapability  # noqa: F401
from app.models.legal_vat_rate import LegalVatRate  # noqa: E402,F401 - legal VAT rates catalog
from app.models.company_fiscal_regime import CompanyFiscalRegime  # noqa: E402,F401 - regime history
