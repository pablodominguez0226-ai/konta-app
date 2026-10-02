from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_

from app.models import Category, Product, Customer, Account, Sale, SaleItem, Expense, CashMovement
from app.schemas import (
    CategoryCreate, ProductCreate, ProductUpdate, SaleCreate, QuickSaleCreate,
    ExpenseCreate, AccountCreate, CashMovementCreate
)

# ==========================================
# ACCOUNT OPERATIONS & BALANCE MANAGEMENT
# ==========================================

def get_accounts(db: Session, active_only: bool = True) -> List[Account]:
    q = db.query(Account)
    if active_only:
        q = q.filter(Account.is_active == True)
    return q.order_by(Account.id.asc()).all()

def get_account_by_id(db: Session, account_id: int) -> Optional[Account]:
    return db.query(Account).filter(Account.id == account_id).first()

def get_default_account_for_payment(db: Session, payment_method: str) -> Optional[Account]:
    """Sugerir cuenta contable según el medio de pago"""
    pm_lower = payment_method.lower()
    if "efectivo" in pm_lower:
        acc = db.query(Account).filter(Account.name.ilike("%efectivo%")).first()
        if acc:
            return acc
    elif "mercado" in pm_lower or "mp" in pm_lower:
        acc = db.query(Account).filter(Account.name.ilike("%mercado%")).first()
        if acc:
            return acc
    elif "banco" in pm_lower or "transfer" in pm_lower or "débito" in pm_lower or "credito" in pm_lower:
        acc = db.query(Account).filter(or_(Account.name.ilike("%banco%"), Account.name.ilike("%transfer%"))).first()
        if acc:
            return acc
    return db.query(Account).filter(Account.is_active == True).first()

def recalculate_account_balances(db: Session):
    """Garantiza la consistencia matemática absoluta de los saldos de cada cuenta."""
    accounts = db.query(Account).all()
    for acc in accounts:
        # 1. Ventas cobradas en esta cuenta
        sales_sum = db.query(func.coalesce(func.sum(Sale.total_amount), 0.0))\
            .filter(Sale.account_id == acc.id, Sale.status == "Cobrado").scalar()
        
        # 2. Gastos pagados desde esta cuenta
        expenses_sum = db.query(func.coalesce(func.sum(Expense.amount), 0.0))\
            .filter(Expense.account_id == acc.id, Expense.status == "Pagado").scalar()
        
        # 3. Transferencias entrantes
        in_transfers = db.query(func.coalesce(func.sum(CashMovement.amount), 0.0))\
            .filter(CashMovement.to_account_id == acc.id).scalar()

        # 4. Transferencias salientes
        out_transfers = db.query(func.coalesce(func.sum(CashMovement.amount), 0.0))\
            .filter(CashMovement.from_account_id == acc.id).scalar()

        acc.current_balance = round(acc.initial_balance + sales_sum - expenses_sum + in_transfers - out_transfers, 2)
    db.commit()

def create_account(db: Session, account_in: AccountCreate) -> Account:
    acc = Account(
        name=account_in.name,
        account_type=account_in.account_type,
        initial_balance=account_in.initial_balance,
        current_balance=account_in.initial_balance,
        is_active=True
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc

# ==========================================
# CATEGORIES & PRODUCTS (CATÁLOGO MULTIRRUBRO)
# ==========================================

def get_categories(db: Session) -> List[Category]:
    return db.query(Category).filter(Category.is_active == True).order_by(Category.name.asc()).all()

def create_category(db: Session, cat_in: CategoryCreate) -> Category:
    cat = Category(name=cat_in.name, description=cat_in.description, icon=cat_in.icon)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat

def get_products(
    db: Session, 
    category_id: Optional[int] = None, 
    search: Optional[str] = None, 
    active_only: bool = True
) -> List[Product]:
    q = db.query(Product)
    if active_only:
        q = q.filter(Product.is_active == True)
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if search:
        search_term = f"%{search}%"
        q = q.filter(or_(Product.name.ilike(search_term), Product.sku.ilike(search_term)))
    return q.order_by(Product.name.asc()).all()

def get_product(db: Session, product_id: int) -> Optional[Product]:
    return db.query(Product).filter(Product.id == product_id).first()

def create_product(db: Session, prod_in: ProductCreate) -> Product:
    prod = Product(
        name=prod_in.name,
        sku=prod_in.sku,
        category_id=prod_in.category_id,
        cost_price=prod_in.cost_price,
        sale_price=prod_in.sale_price,
        stock_quantity=prod_in.stock_quantity,
        min_stock_alert=prod_in.min_stock_alert,
        is_active=True
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod

def update_product(db: Session, product_id: int, prod_update: ProductUpdate) -> Optional[Product]:
    prod = get_product(db, product_id)
    if not prod:
        return None
    data = prod_update.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(prod, key, value)
    db.commit()
    db.refresh(prod)
    return prod

def adjust_stock(db: Session, product_id: int, quantity_diff: int) -> Optional[Product]:
    prod = get_product(db, product_id)
    if not prod:
        return None
    prod.stock_quantity += quantity_diff
    db.commit()
    db.refresh(prod)
    return prod

def get_low_stock_products(db: Session) -> List[Product]:
    return db.query(Product).filter(
        Product.is_active == True,
        Product.stock_quantity <= Product.min_stock_alert
    ).order_by(Product.stock_quantity.asc()).all()

# ==========================================
# SALES OPERATIONS (FLUJO ÁGIL LUMELÍ)
# ==========================================

def generate_sale_number(db: Session) -> str:
    count = db.query(Sale).count()
    return f"VTA-{(count + 1):04d}"

def create_sale(db: Session, sale_in: SaleCreate) -> Sale:
    # 1. Resolver cuenta contable destino si no se indicó
    account_id = sale_in.account_id
    if not account_id:
        acc = get_default_account_for_payment(db, sale_in.payment_method)
        if acc:
            account_id = acc.id

    # 2. Calcular totales
    total_amount = 0.0
    total_cost = 0.0

    items_to_create = []
    for item_data in sale_in.items:
        qty = max(1, item_data.quantity)
        u_cost = float(item_data.unit_cost)
        u_price = float(item_data.unit_price)

        # Si el item tiene product_id, intentar tomar o sincronizar costo y descontar stock
        prod = None
        if item_data.product_id:
            prod = get_product(db, item_data.product_id)
            if prod:
                if u_cost == 0.0 and prod.cost_price > 0.0:
                    u_cost = prod.cost_price
                # Descontar stock automáticamente
                prod.stock_quantity -= qty

        item_subtotal = round(u_price * qty, 2)
        item_cost_subtotal = round(u_cost * qty, 2)

        total_amount += item_subtotal
        total_cost += item_cost_subtotal

        items_to_create.append({
            "product_id": item_data.product_id,
            "product_name": item_data.product_name,
            "quantity": qty,
            "unit_cost": u_cost,
            "unit_price": u_price,
            "subtotal": item_subtotal,
            "cost_subtotal": item_cost_subtotal
        })

    gross_margin = round(total_amount - total_cost, 2)
    margin_percentage = round((gross_margin / total_amount * 100), 1) if total_amount > 0 else 0.0

    sale = Sale(
        sale_number=generate_sale_number(db),
        date=datetime.now(),
        customer_name=sale_in.customer_name or "Consumidor Final",
        customer_phone=sale_in.customer_phone,
        channel=sale_in.channel or "Instagram",
        payment_method=sale_in.payment_method or "Mercado Pago",
        account_id=account_id,
        total_amount=round(total_amount, 2),
        total_cost=round(total_cost, 2),
        gross_margin=gross_margin,
        margin_percentage=margin_percentage,
        status=sale_in.status or "Cobrado",
        notes=sale_in.notes
    )
    db.add(sale)
    db.flush()

    for it in items_to_create:
        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=it["product_id"],
            product_name=it["product_name"],
            quantity=it["quantity"],
            unit_cost=it["unit_cost"],
            unit_price=it["unit_price"],
            subtotal=it["subtotal"],
            cost_subtotal=it["cost_subtotal"]
        )
        db.add(sale_item)

    # 3. Si está cobrada, impactar de inmediato en el saldo de la cuenta
    if sale.status == "Cobrado" and account_id:
        acc = get_account_by_id(db, account_id)
        if acc:
            acc.current_balance = round(acc.current_balance + total_amount, 2)

    db.commit()
    db.refresh(sale)
    return sale

def create_quick_sale(db: Session, q_sale: QuickSaleCreate) -> Sale:
    """Atajo ultrarrápido estilo Lumelí para venta de 1 producto en 1 clic"""
    sale_in = SaleCreate(
        customer_name=q_sale.customer_name,
        customer_phone=q_sale.customer_phone,
        channel=q_sale.channel,
        payment_method=q_sale.payment_method,
        account_id=q_sale.account_id,
        status=q_sale.status,
        notes=q_sale.notes,
        items=[
            {
                "product_id": q_sale.product_id,
                "product_name": q_sale.product_name,
                "quantity": q_sale.quantity,
                "unit_cost": q_sale.unit_cost,
                "unit_price": q_sale.unit_price
            }
        ]
    )
    return create_sale(db, sale_in)

def annul_sale(db: Session, sale_id: int) -> Optional[Sale]:
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale or sale.status == "Anulado":
        return sale
    
    # 1. Si estaba cobrada, restar monto de la cuenta
    if sale.status == "Cobrado" and sale.account_id:
        acc = get_account_by_id(db, sale.account_id)
        if acc:
            acc.current_balance = round(acc.current_balance - sale.total_amount, 2)

    # 2. Devolver stock a los productos
    for item in sale.items:
        if item.product_id:
            prod = get_product(db, item.product_id)
            if prod:
                prod.stock_quantity += item.quantity

    sale.status = "Anulado"
    db.commit()
    db.refresh(sale)
    return sale

def update_sale_status(db: Session, sale_id: int, new_status: str, account_id: Optional[int] = None) -> Optional[Sale]:
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale or sale.status == new_status:
        return sale
    
    old_status = sale.status
    if account_id:
        sale.account_id = account_id

    # Si pasa a Cobrado desde Pendiente
    if old_status == "Pendiente" and new_status == "Cobrado":
        if sale.account_id:
            acc = get_account_by_id(db, sale.account_id)
            if acc:
                acc.current_balance = round(acc.current_balance + sale.total_amount, 2)
    # Si pasa de Cobrado a Pendiente
    elif old_status == "Cobrado" and new_status == "Pendiente":
        if sale.account_id:
            acc = get_account_by_id(db, sale.account_id)
            if acc:
                acc.current_balance = round(acc.current_balance - sale.total_amount, 2)

    sale.status = new_status
    db.commit()
    db.refresh(sale)
    return sale

def get_sales(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    channel: Optional[str] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200
) -> List[Sale]:
    q = db.query(Sale)
    if start_date:
        q = q.filter(Sale.date >= start_date)
    if end_date:
        q = q.filter(Sale.date <= end_date)
    if channel:
        q = q.filter(Sale.channel == channel)
    if status:
        q = q.filter(Sale.status == status)
    if payment_method:
        q = q.filter(Sale.payment_method == payment_method)
    if search:
        s_term = f"%{search}%"
        q = q.filter(or_(
            Sale.customer_name.ilike(s_term),
            Sale.sale_number.ilike(s_term),
            Sale.notes.ilike(s_term)
        ))
    return q.order_by(desc(Sale.date)).limit(limit).all()

def get_sale(db: Session, sale_id: int) -> Optional[Sale]:
    return db.query(Sale).filter(Sale.id == sale_id).first()

# ==========================================
# EXPENSES & CASH FLOW (FLUJO DE FONDOS)
# ==========================================

def create_expense(db: Session, exp_in: ExpenseCreate) -> Expense:
    amount = float(exp_in.amount)
    exp = Expense(
        date=datetime.now(),
        category=exp_in.category,
        description=exp_in.description,
        amount=round(amount, 2),
        account_id=exp_in.account_id,
        status=exp_in.status or "Pagado",
        notes=exp_in.notes
    )
    db.add(exp)

    # Restar de la cuenta si está pagado
    if exp.status == "Pagado" and exp.account_id:
        acc = get_account_by_id(db, exp.account_id)
        if acc:
            acc.current_balance = round(acc.current_balance - amount, 2)

    db.commit()
    db.refresh(exp)
    return exp

def delete_expense(db: Session, expense_id: int) -> bool:
    exp = db.query(Expense).filter(Expense.id == expense_id).first()
    if not exp:
        return False
    
    # Reintegrar saldo si estaba pagado
    if exp.status == "Pagado" and exp.account_id:
        acc = get_account_by_id(db, exp.account_id)
        if acc:
            acc.current_balance = round(acc.current_balance + exp.amount, 2)

    db.delete(exp)
    db.commit()
    return True

def get_expenses(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    category: Optional[str] = None,
    account_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 200
) -> List[Expense]:
    q = db.query(Expense)
    if start_date:
        q = q.filter(Expense.date >= start_date)
    if end_date:
        q = q.filter(Expense.date <= end_date)
    if category:
        q = q.filter(Expense.category == category)
    if account_id:
        q = q.filter(Expense.account_id == account_id)
    if search:
        s_term = f"%{search}%"
        q = q.filter(or_(
            Expense.description.ilike(s_term),
            Expense.category.ilike(s_term),
            Expense.notes.ilike(s_term)
        ))
    return q.order_by(desc(Expense.date)).limit(limit).all()

def create_cash_movement(db: Session, mov_in: CashMovementCreate) -> CashMovement:
    if mov_in.from_account_id == mov_in.to_account_id:
        raise ValueError("La cuenta de origen y destino deben ser distintas")
    
    from_acc = get_account_by_id(db, mov_in.from_account_id)
    to_acc = get_account_by_id(db, mov_in.to_account_id)
    if not from_acc or not to_acc:
        raise ValueError("Cuenta no encontrada")

    amount = float(mov_in.amount)
    from_acc.current_balance = round(from_acc.current_balance - amount, 2)
    to_acc.current_balance = round(to_acc.current_balance + amount, 2)

    mov = CashMovement(
        date=datetime.now(),
        from_account_id=from_acc.id,
        to_account_id=to_acc.id,
        amount=amount,
        reason=mov_in.reason
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return mov

# ==========================================
# DASHBOARD FINANCIAL METRICS (LUMELÍ STYLE)
# ==========================================

def get_period_dates(period: str) -> tuple[datetime, datetime]:
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    today_end = datetime(now.year, now.month, now.day, 23, 59, 59)

    if period == "today":
        return today_start, today_end
    elif period == "yesterday":
        y_start = today_start - timedelta(days=1)
        y_end = today_end - timedelta(days=1)
        return y_start, y_end
    elif period == "week":
        # Últimos 7 días
        w_start = today_start - timedelta(days=6)
        return w_start, today_end
    elif period == "month":
        # Mes en curso
        m_start = datetime(now.year, now.month, 1, 0, 0, 0)
        return m_start, today_end
    elif period == "last_month":
        first_this_month = datetime(now.year, now.month, 1)
        last_day_prev = first_this_month - timedelta(days=1)
        first_prev = datetime(last_day_prev.year, last_day_prev.month, 1, 0, 0, 0)
        end_prev = datetime(last_day_prev.year, last_day_prev.month, last_day_prev.day, 23, 59, 59)
        return first_prev, end_prev
    elif period == "all":
        return datetime(2020, 1, 1, 0, 0, 0), today_end
    else:
        # Default mes en curso
        return datetime(now.year, now.month, 1, 0, 0, 0), today_end

def get_dashboard_metrics(
    db: Session, 
    period: str = "month", 
    custom_start: Optional[datetime] = None, 
    custom_end: Optional[datetime] = None
) -> Dict[str, Any]:
    if custom_start and custom_end:
        start_dt = custom_start
        end_dt = custom_end
    else:
        start_dt, end_dt = get_period_dates(period)

    # 1. Ventas válidas (excluir anuladas)
    sales = db.query(Sale).filter(
        Sale.date >= start_dt,
        Sale.date <= end_dt,
        Sale.status.in_(["Cobrado", "Pendiente"])
    ).all()

    total_sales_amount = sum(s.total_amount for s in sales)
    total_sales_cost = sum(s.total_cost for s in sales)
    gross_margin = total_sales_amount - total_sales_cost
    gross_margin_pct = round((gross_margin / total_sales_amount * 100), 1) if total_sales_amount > 0 else 0.0
    sales_count = len(sales)
    avg_ticket = round(total_sales_amount / sales_count, 2) if sales_count > 0 else 0.0

    # 2. Gastos operativos del período
    expenses = db.query(Expense).filter(
        Expense.date >= start_dt,
        Expense.date <= end_dt,
        Expense.status == "Pagado"
    ).all()

    total_expenses = sum(e.amount for e in expenses)

    # 3. Ganancia Neta Real (En el bolsillo)
    net_profit = gross_margin - total_expenses
    net_margin_pct = round((net_profit / total_sales_amount * 100), 1) if total_sales_amount > 0 else 0.0

    # 4. Saldos por Cuenta
    accounts = db.query(Account).filter(Account.is_active == True).all()
    accounts_data = [
        {
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "balance": round(a.current_balance, 2)
        }
        for a in accounts
    ]
    total_cash_available = sum(a.current_balance for a in accounts)

    # 5. Ventas por Canal
    channel_counts: Dict[str, float] = {}
    for s in sales:
        channel_counts[s.channel] = channel_counts.get(s.channel, 0.0) + s.total_amount
    channels_chart = [{"channel": k, "total": round(v, 2)} for k, v in channel_counts.items()]

    # 6. Gastos por Categoría
    expense_category_counts: Dict[str, float] = {}
    for e in expenses:
        expense_category_counts[e.category] = expense_category_counts.get(e.category, 0.0) + e.amount
    expenses_chart = [{"category": k, "total": round(v, 2)} for k, v in expense_category_counts.items()]

    # 7. Tendencia diaria (últimos 7 o 15 días dentro del rango)
    # Generar días en el rango
    days_diff = (end_dt.date() - start_dt.date()).days + 1
    if days_diff > 31:
        # limitar visualización diaria a los últimos 30 días
        trend_start = end_dt.date() - timedelta(days=29)
    else:
        trend_start = start_dt.date()
    
    daily_trend = []
    curr = trend_start
    while curr <= end_dt.date():
        day_str = curr.strftime("%d/%m")
        day_start = datetime(curr.year, curr.month, curr.day, 0, 0, 0)
        day_end = datetime(curr.year, curr.month, curr.day, 23, 59, 59)

        day_sales = sum(s.total_amount for s in sales if day_start <= s.date <= day_end)
        day_cmv = sum(s.total_cost for s in sales if day_start <= s.date <= day_end)
        day_exp = sum(e.amount for e in expenses if day_start <= e.date <= day_end)
        day_gross = day_sales - day_cmv
        day_net = day_gross - day_exp

        daily_trend.append({
            "date": day_str,
            "sales": round(day_sales, 2),
            "expenses": round(day_exp, 2),
            "net_profit": round(day_net, 2)
        })
        curr += timedelta(days=1)

    # 8. Top Productos vendidos en el período
    top_items = db.query(
        SaleItem.product_name,
        func.sum(SaleItem.quantity).label("units_sold"),
        func.sum(SaleItem.subtotal).label("total_revenue"),
        func.sum(SaleItem.subtotal - SaleItem.cost_subtotal).label("profit_generated")
    ).join(Sale, SaleItem.sale_id == Sale.id)\
     .filter(Sale.date >= start_dt, Sale.date <= end_dt, Sale.status.in_(["Cobrado", "Pendiente"]))\
     .group_by(SaleItem.product_name)\
     .order_by(desc("units_sold"))\
     .limit(5).all()

    top_products_data = [
        {
            "name": row[0],
            "units": row[1],
            "revenue": round(row[2], 2),
            "profit": round(row[3], 2)
        }
        for row in top_items
    ]

    # 9. Alertas de Negocio (Lumelí Alerts)
    low_stock = get_low_stock_products(db)
    pending_sales = db.query(Sale).filter(Sale.status == "Pendiente").all()
    pending_amount = sum(s.total_amount for s in pending_sales)

    return {
        "period": period,
        "start_date": start_dt.strftime("%d/%m/%Y"),
        "end_date": end_dt.strftime("%d/%m/%Y"),
        "total_sales": round(total_sales_amount, 2),
        "total_cost": round(total_sales_cost, 2),
        "gross_margin": round(gross_margin, 2),
        "gross_margin_pct": gross_margin_pct,
        "total_expenses": round(total_expenses, 2),
        "net_profit": round(net_profit, 2),
        "net_margin_pct": net_margin_pct,
        "sales_count": sales_count,
        "avg_ticket": avg_ticket,
        "accounts": accounts_data,
        "total_cash": round(total_cash_available, 2),
        "channels_chart": channels_chart,
        "expenses_chart": expenses_chart,
        "daily_trend": daily_trend,
        "top_products": top_products_data,
        "low_stock_count": len(low_stock),
        "low_stock_items": [{"id": p.id, "name": p.name, "stock": p.stock_quantity, "min": p.min_stock_alert} for p in low_stock[:5]],
        "pending_sales_count": len(pending_sales),
        "pending_sales_amount": round(pending_amount, 2)
    }
