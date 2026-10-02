import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    icon = Column(String(50), default="fa-box")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    sku = Column(String(50), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    cost_price = Column(Float, default=0.0)      # Costo unitario
    sale_price = Column(Float, default=0.0)      # Precio de venta sugerido
    stock_quantity = Column(Integer, default=0)  # Stock físico actual
    min_stock_alert = Column(Integer, default=5) # Nivel de alerta stock crítico
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    category = relationship("Category", back_populates="products")
    sale_items = relationship("SaleItem", back_populates="product")

    @property
    def estimated_unit_margin(self):
        return round(self.sale_price - self.cost_price, 2)

    @property
    def estimated_margin_pct(self):
        if self.sale_price > 0:
            return round(((self.sale_price - self.cost_price) / self.sale_price) * 100, 1)
        return 0.0


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False) # e.g. "Caja Efectivo", "Mercado Pago", "Banco"
    account_type = Column(String(50), default="cash")        # cash, digital_wallet, bank
    initial_balance = Column(Float, default=0.0)
    current_balance = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    sales = relationship("Sale", back_populates="account")
    expenses = relationship("Expense", back_populates="account")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    channel_preference = Column(String(50), default="Instagram")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    sale_number = Column(String(50), unique=True, index=True) # e.g. "VTA-0001"
    date = Column(DateTime, default=datetime.datetime.now, index=True)
    customer_name = Column(String(150), default="Consumidor Final", index=True)
    customer_phone = Column(String(50), nullable=True)
    channel = Column(String(50), default="Instagram", index=True) # Instagram, WhatsApp, Mercado Libre, Local / Mostrador, Web
    payment_method = Column(String(50), default="Mercado Pago")   # Mercado Pago, Efectivo, Transferencia, Débito, Crédito
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    
    total_amount = Column(Float, default=0.0)       # Facturación total
    total_cost = Column(Float, default=0.0)         # Costo total CMV
    gross_margin = Column(Float, default=0.0)       # Ganancia bruta en $
    margin_percentage = Column(Float, default=0.0)  # Margen bruto en %
    
    status = Column(String(50), default="Cobrado", index=True) # Cobrado, Pendiente, Anulado
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    account = relationship("Account", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(150), nullable=False)
    quantity = Column(Integer, default=1)
    unit_cost = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    subtotal = Column(Float, default=0.0)
    cost_subtotal = Column(Float, default=0.0)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.datetime.now, index=True)
    category = Column(String(100), nullable=False, index=True) # Mercadería, Envíos, Publicidad, Packaging, Servicios, Sueldos, Otros
    description = Column(String(255), nullable=False)
    amount = Column(Float, default=0.0)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    status = Column(String(50), default="Pagado") # Pagado, Pendiente
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    account = relationship("Account", back_populates="expenses")


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.datetime.now, index=True)
    from_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    to_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    from_account = relationship("Account", foreign_keys=[from_account_id])
    to_account = relationship("Account", foreign_keys=[to_account_id])
