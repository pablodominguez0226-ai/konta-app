from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Category
class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "fa-box"

class CategoryCreate(CategoryBase):
    pass

class CategoryResponse(CategoryBase):
    id: int
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

# Product
class ProductBase(BaseModel):
    name: str
    sku: Optional[str] = None
    category_id: Optional[int] = None
    cost_price: float = 0.0
    sale_price: float = 0.0
    stock_quantity: int = 0
    min_stock_alert: int = 5

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    category_id: Optional[int] = None
    cost_price: Optional[float] = None
    sale_price: Optional[float] = None
    stock_quantity: Optional[int] = None
    min_stock_alert: Optional[int] = None
    is_active: Optional[bool] = None

class ProductResponse(ProductBase):
    id: int
    is_active: bool
    created_at: datetime
    estimated_unit_margin: float = 0.0
    estimated_margin_pct: float = 0.0
    class Config:
        from_attributes = True

# Account
class AccountBase(BaseModel):
    name: str
    account_type: str = "cash"
    initial_balance: float = 0.0

class AccountCreate(AccountBase):
    pass

class AccountResponse(AccountBase):
    id: int
    current_balance: float
    is_active: bool
    class Config:
        from_attributes = True

# Sale Items
class SaleItemCreate(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    quantity: int = 1
    unit_cost: float = 0.0
    unit_price: float = 0.0

class SaleItemResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: int
    unit_cost: float
    unit_price: float
    subtotal: float
    cost_subtotal: float
    class Config:
        from_attributes = True

# Sale
class SaleCreate(BaseModel):
    customer_name: Optional[str] = "Consumidor Final"
    customer_phone: Optional[str] = None
    channel: str = "Instagram"
    payment_method: str = "Mercado Pago"
    account_id: Optional[int] = None
    status: str = "Cobrado" # Cobrado, Pendiente
    notes: Optional[str] = None
    items: List[SaleItemCreate]

# Quick Sale (single product shortcut)
class QuickSaleCreate(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    quantity: int = 1
    unit_cost: float = 0.0
    unit_price: float = 0.0
    customer_name: Optional[str] = "Consumidor Final"
    customer_phone: Optional[str] = None
    channel: str = "Instagram"
    payment_method: str = "Mercado Pago"
    account_id: Optional[int] = None
    status: str = "Cobrado"
    notes: Optional[str] = None

class SaleResponse(BaseModel):
    id: int
    sale_number: str
    date: datetime
    customer_name: str
    customer_phone: Optional[str] = None
    channel: str
    payment_method: str
    account_id: Optional[int] = None
    total_amount: float
    total_cost: float
    gross_margin: float
    margin_percentage: float
    status: str
    notes: Optional[str] = None
    items: List[SaleItemResponse] = []
    class Config:
        from_attributes = True

# Expense
class ExpenseCreate(BaseModel):
    category: str
    description: str
    amount: float
    account_id: Optional[int] = None
    status: Optional[str] = "Pagado"
    notes: Optional[str] = None

class ExpenseResponse(BaseModel):
    id: int
    date: datetime
    category: str
    description: str
    amount: float
    account_id: Optional[int] = None
    status: str
    notes: Optional[str] = None
    class Config:
        from_attributes = True

# Cash Movement / Transfer
class CashMovementCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: float
    reason: Optional[str] = "Transferencia entre cuentas"
