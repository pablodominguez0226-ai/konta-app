from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models import Category, Product, Account, Sale, SaleItem, Expense
from app import crud

def seed_database(db: Session):
    # Verificar si ya existen productos
    if db.query(Product).count() > 0:
        print("[Seed] La base de datos ya contiene datos. Saltando seed inicial.")
        return

    print("[Seed] Inicializando datos maestros para 'productos.bona'...")

    # 1. Cuentas Financieras
    acc_efectivo = Account(name="Caja Efectivo", account_type="cash", initial_balance=45000.0, current_balance=45000.0)
    acc_mp = Account(name="Mercado Pago", account_type="digital_wallet", initial_balance=180000.0, current_balance=180000.0)
    acc_banco = Account(name="Banco / Transferencia", account_type="bank", initial_balance=290000.0, current_balance=290000.0)
    
    db.add_all([acc_efectivo, acc_mp, acc_banco])
    db.commit()
    db.refresh(acc_efectivo)
    db.refresh(acc_mp)
    db.refresh(acc_banco)

    # 2. Categorías Multirrubro
    cat_pisos = Category(name="Cuidado de Pisos y Madera", description="Limpiadores, ceras y renovadores Bona", icon="fa-broom")
    cat_mopas = Category(name="Mopas y Accesorios", description="Sistemas de limpieza con spray y recambios", icon="fa-brush")
    cat_multiuso = Category(name="Limpiadores Multiuso", description="Superficies duras, vidrios y porcelanato", icon="fa-spray-can-sparkles")
    cat_aromas = Category(name="Fragancias y Difusores", description="Aromatizadores de ambiente premium", icon="fa-wind")
    cat_personal = Category(name="Cuidado Personal", description="Jabones y cosmética botánica", icon="fa-pump-soap")

    db.add_all([cat_pisos, cat_mopas, cat_multiuso, cat_aromas, cat_personal])
    db.commit()

    # 3. Catálogo de Productos
    prods = [
        Product(
            name="Limpiador Bona Pisos de Madera Spray 1L",
            sku="BONA-MAD-1L",
            category_id=cat_pisos.id,
            cost_price=9500.0,
            sale_price=16800.0,
            stock_quantity=22,
            min_stock_alert=5
        ),
        Product(
            name="Mopa de Microfibra Premium Bona Spray",
            sku="BONA-MOP-PREM",
            category_id=cat_mopas.id,
            cost_price=27500.0,
            sale_price=48500.0,
            stock_quantity=14,
            min_stock_alert=4
        ),
        Product(
            name="Pad Limpiador Microfibra Bona Repuesto",
            sku="BONA-PAD-LIM",
            category_id=cat_mopas.id,
            cost_price=4800.0,
            sale_price=8900.0,
            stock_quantity=32,
            min_stock_alert=6
        ),
        Product(
            name="Limpiador Bona Superficies Duras 1L",
            sku="BONA-DUR-1L",
            category_id=cat_multiuso.id,
            cost_price=9200.0,
            sale_price=15900.0,
            stock_quantity=19,
            min_stock_alert=5
        ),
        Product(
            name="Renovador Polish Bona Brillo Mate 1L",
            sku="BONA-POL-MATE",
            category_id=cat_pisos.id,
            cost_price=14500.0,
            sale_price=24900.0,
            stock_quantity=9,
            min_stock_alert=3
        ),
        Product(
            name="Difusor Aromático Ambiental 250ml Vainilla & Coco",
            sku="DIF-VC-250",
            category_id=cat_aromas.id,
            cost_price=3200.0,
            sale_price=6800.0,
            stock_quantity=3, # Crítico
            min_stock_alert=5
        ),
        Product(
            name="Jabón Líquido Botánico Manos & Cuerpo 500ml",
            sku="BOT-JAB-500",
            category_id=cat_personal.id,
            cost_price=2300.0,
            sale_price=5200.0,
            stock_quantity=18,
            min_stock_alert=5
        ),
        Product(
            name="Repuesto Recarga Limpiador Bona Madera 4L",
            sku="BONA-MAD-4L",
            category_id=cat_pisos.id,
            cost_price=29000.0,
            sale_price=51000.0,
            stock_quantity=7,
            min_stock_alert=3
        )
    ]
    db.add_all(prods)
    db.commit()

    # 4. Ventas Semilla (Últimos días para poblar métricas en tiempo real)
    now = datetime.now()
    sales_seed = [
        {
            "offset_days": 0, "offset_hours": 2,
            "cliente": "Camila Fernández", "canal": "Instagram", "medio": "Mercado Pago",
            "acc": acc_mp,
            "items": [(prods[0], 1), (prods[2], 2)]
        },
        {
            "offset_days": 0, "offset_hours": 4,
            "cliente": "Marcos Rossi", "canal": "WhatsApp", "medio": "Transferencia",
            "acc": acc_banco,
            "items": [(prods[1], 1)]
        },
        {
            "offset_days": 1, "offset_hours": 3,
            "cliente": "Consumidor Final", "canal": "Local / Mostrador", "medio": "Efectivo",
            "acc": acc_efectivo,
            "items": [(prods[3], 2), (prods[6], 1)]
        },
        {
            "offset_days": 2, "offset_hours": 5,
            "cliente": "Estudio Arquitectura Sur", "canal": "WhatsApp", "medio": "Transferencia",
            "acc": acc_banco,
            "items": [(prods[7], 1), (prods[4], 2)]
        },
        {
            "offset_days": 3, "offset_hours": 1,
            "cliente": "Lucía Morales", "canal": "Mercado Libre", "medio": "Mercado Pago",
            "acc": acc_mp,
            "items": [(prods[0], 2)]
        },
        {
            "offset_days": 4, "offset_hours": 6,
            "cliente": "Esteban Gómez", "canal": "Instagram", "medio": "Mercado Pago",
            "acc": acc_mp,
            "items": [(prods[5], 2)]
        }
    ]

    for idx, s_data in enumerate(sales_seed, 1):
        sale_dt = now - timedelta(days=s_data["offset_days"], hours=s_data["offset_hours"])
        tot_amount = sum(p.sale_price * qty for p, qty in s_data["items"])
        tot_cost = sum(p.cost_price * qty for p, qty in s_data["items"])
        margin = tot_amount - tot_cost
        margin_pct = round((margin / tot_amount * 100), 1) if tot_amount > 0 else 0.0

        sale = Sale(
            sale_number=f"VTA-{idx:04d}",
            date=sale_dt,
            customer_name=s_data["cliente"],
            channel=s_data["canal"],
            payment_method=s_data["medio"],
            account_id=s_data["acc"].id,
            total_amount=tot_amount,
            total_cost=tot_cost,
            gross_margin=margin,
            margin_percentage=margin_pct,
            status="Cobrado",
            notes="Venta inicial precargada"
        )
        db.add(sale)
        db.flush()

        for prod, qty in s_data["items"]:
            s_item = SaleItem(
                sale_id=sale.id,
                product_id=prod.id,
                product_name=prod.name,
                quantity=qty,
                unit_cost=prod.cost_price,
                unit_price=prod.sale_price,
                subtotal=prod.sale_price * qty,
                cost_subtotal=prod.cost_price * qty
            )
            db.add(s_item)

    # 5. Gastos Semilla
    expenses_seed = [
        {"offset_days": 1, "cat": "Publicidad y Ads", "desc": "Campaña Meta Ads Instagram (Septiembre)", "amount": 25000.0, "acc": acc_mp},
        {"offset_days": 3, "cat": "Packaging y Embalaje", "desc": "100 Cajas de cartón y cinta adhesiva reforzada", "amount": 18500.0, "acc": acc_efectivo},
        {"offset_days": 5, "cat": "Logística y Envíos", "desc": "Liquidación envíos a domicilio moto mensajería", "amount": 14200.0, "acc": acc_mp},
    ]

    for e_data in expenses_seed:
        exp_dt = now - timedelta(days=e_data["offset_days"], hours=2)
        exp = Expense(
            date=exp_dt,
            category=e_data["cat"],
            description=e_data["desc"],
            amount=e_data["amount"],
            account_id=e_data["acc"].id,
            status="Pagado",
            notes="Gasto operativo precargado"
        )
        db.add(exp)

    db.commit()

    # Sincronizar saldos de cuentas con base en ventas y gastos
    crud.recalculate_account_balances(db)
    print("[Seed] Inicialización completada exitosamente.")

if __name__ == "__main__":
    db = SessionLocal()
    seed_database(db)
    db.close()
