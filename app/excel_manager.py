import io
import csv
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.models import Sale, SaleItem, Expense, Product, Category, Account
from app import crud

# Estilos corporativos para los reportes de Excel
HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid") # Dark Slate
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=15, bold=True, color="0F172A")
SUBTITLE_FONT = Font(name="Calibri", size=10, italic=True, color="64748B")
KPI_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
TOTAL_FILL = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
TOTAL_FONT = Font(name="Calibri", size=11, bold=True, color="0F172A")
BORDER_THIN = Border(
    left=Side(style='thin', color='CBD5E1'),
    right=Side(style='thin', color='CBD5E1'),
    top=Side(style='thin', color='CBD5E1'),
    bottom=Side(style='thin', color='CBD5E1')
)
CURRENCY_FORMAT = '"$"#,##0.00'
PERCENT_FORMAT = '0.0%'
DATE_FORMAT = 'YYYY-MM-DD HH:MM'

def style_header_row(ws, row_idx: int, num_cols: int):
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER_THIN
    ws.row_dimensions[row_idx].height = 28

def auto_fit_columns(ws, max_cols: int = 15):
    for col in range(1, max_cols + 1):
        col_letter = get_column_letter(col)
        max_len = 0
        for cell in ws[col_letter]:
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

def export_sales_to_excel(
    db: Session, 
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None
) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"
    ws.views.sheetView[0].showGridLines = True

    # Título
    ws["A1"] = "productos.bona — Reporte Detallado de Ventas"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A2"].font = SUBTITLE_FONT

    headers = [
        "ID", "N° Venta", "Fecha", "Cliente", "Canal", 
        "Medio de Pago", "Cuenta Destino", "Productos / Detalle", 
        "Total Cobrado", "Costo Total", "Ganancia Bruta", "Margen %", "Estado", "Notas"
    ]

    row_idx = 4
    for col_idx, h in enumerate(headers, 1):
        ws.cell(row=row_idx, column=col_idx, value=h)
    style_header_row(ws, row_idx, len(headers))

    sales = crud.get_sales(db, start_date=start_date, end_date=end_date, limit=5000)
    current_row = 5

    for s in sales:
        items_desc = ", ".join([f"{it.product_name} (x{it.quantity})" for it in s.items])
        acc_name = s.account.name if s.account else "Sin asignar"

        row_data = [
            s.id,
            s.sale_number,
            s.date.strftime("%Y-%m-%d %H:%M"),
            s.customer_name,
            s.channel,
            s.payment_method,
            acc_name,
            items_desc,
            s.total_amount,
            s.total_cost,
            s.gross_margin,
            (s.margin_percentage / 100) if s.margin_percentage else 0.0,
            s.status,
            s.notes or ""
        ]

        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.border = BORDER_THIN

            # Formatos numéricos
            if col_idx in [9, 10, 11]: # Total, Costo, Ganancia
                cell.number_format = CURRENCY_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx == 12: # Margen %
                cell.number_format = PERCENT_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in [1, 2, 3, 13]:
                cell.alignment = Alignment(horizontal="center")

        current_row += 1

    # Fila de Totales
    if len(sales) > 0:
        total_row = current_row
        ws.cell(row=total_row, column=1, value="TOTALES").font = TOTAL_FONT
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row, column=col_idx)
            cell.fill = TOTAL_FILL
            cell.border = BORDER_THIN
            if col_idx == 9:
                cell.value = f"=SUM(I5:I{total_row-1})"
                cell.number_format = CURRENCY_FORMAT
                cell.font = TOTAL_FONT
            elif col_idx == 10:
                cell.value = f"=SUM(J5:J{total_row-1})"
                cell.number_format = CURRENCY_FORMAT
                cell.font = TOTAL_FONT
            elif col_idx == 11:
                cell.value = f"=SUM(K5:K{total_row-1})"
                cell.number_format = CURRENCY_FORMAT
                cell.font = TOTAL_FONT

    auto_fit_columns(ws, len(headers))

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def export_expenses_to_excel(
    db: Session, 
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None
) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Gastos y Egresos"
    ws.views.sheetView[0].showGridLines = True

    ws["A1"] = "productos.bona — Flujo de Gastos y Egresos"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A2"].font = SUBTITLE_FONT

    headers = ["ID", "Fecha", "Categoría", "Descripción", "Cuenta Origen", "Monto", "Estado", "Notas"]
    row_idx = 4
    for col_idx, h in enumerate(headers, 1):
        ws.cell(row=row_idx, column=col_idx, value=h)
    style_header_row(ws, row_idx, len(headers))

    expenses = crud.get_expenses(db, start_date=start_date, end_date=end_date, limit=5000)
    current_row = 5

    for e in expenses:
        acc_name = e.account.name if e.account else "Sin cuenta"
        row_data = [
            e.id,
            e.date.strftime("%Y-%m-%d %H:%M"),
            e.category,
            e.description,
            acc_name,
            e.amount,
            e.status,
            e.notes or ""
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.border = BORDER_THIN
            if col_idx == 6:
                cell.number_format = CURRENCY_FORMAT
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in [1, 2, 7]:
                cell.alignment = Alignment(horizontal="center")
        current_row += 1

    if len(expenses) > 0:
        total_row = current_row
        ws.cell(row=total_row, column=1, value="TOTAL GASTOS").font = TOTAL_FONT
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row, column=col_idx)
            cell.fill = TOTAL_FILL
            cell.border = BORDER_THIN
            if col_idx == 6:
                cell.value = f"=SUM(F5:F{total_row-1})"
                cell.number_format = CURRENCY_FORMAT
                cell.font = TOTAL_FONT

    auto_fit_columns(ws, len(headers))

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def export_full_financial_report(
    db: Session, 
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None
) -> io.BytesIO:
    """Genera un libro contable completo multidestino: Resumen Ejecutivo + Ventas + Gastos + Inventario"""
    wb = openpyxl.Workbook()

    # Hoja 1: Resumen Ejecutivo
    ws_resumen = wb.active
    ws_resumen.title = "Resumen Ejecutivo"
    ws_resumen.views.sheetView[0].showGridLines = True

    ws_resumen["A1"] = "productos.bona — Balance y Rendimiento Financiero"
    ws_resumen["A1"].font = TITLE_FONT
    ws_resumen["A2"] = f"Reporte generado automáticamente el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws_resumen["A2"].font = SUBTITLE_FONT

    metrics = crud.get_dashboard_metrics(db, period="all", custom_start=start_date, custom_end=end_date)

    summary_items = [
        ("Facturación Total (Ventas)", metrics["total_sales"], CURRENCY_FORMAT),
        ("Costo Mercadería Vendida (CMV)", metrics["total_cost"], CURRENCY_FORMAT),
        ("Ganancia Bruta", metrics["gross_margin"], CURRENCY_FORMAT),
        ("Margen Bruto Promedio", metrics["gross_margin_pct"] / 100, PERCENT_FORMAT),
        ("Gastos Operativos Totales", metrics["total_expenses"], CURRENCY_FORMAT),
        ("Ganancia Neta Real (En Bolsillo)", metrics["net_profit"], CURRENCY_FORMAT),
        ("Margen Neto Real", metrics["net_margin_pct"] / 100, PERCENT_FORMAT),
        ("Cantidad de Ventas", metrics["sales_count"], "#,##0"),
        ("Ticket Promedio", metrics["avg_ticket"], CURRENCY_FORMAT),
        ("Total Disponible en Cuentas", metrics["total_cash"], CURRENCY_FORMAT)
    ]

    ws_resumen.cell(row=4, column=1, value="Métrica Financiera")
    ws_resumen.cell(row=4, column=2, value="Valor Consolidado")
    style_header_row(ws_resumen, 4, 2)

    for idx, (label, val, fmt) in enumerate(summary_items, 5):
        c1 = ws_resumen.cell(row=idx, column=1, value=label)
        c2 = ws_resumen.cell(row=idx, column=2, value=val)
        c1.border = BORDER_THIN
        c2.border = BORDER_THIN
        c2.number_format = fmt
        c2.alignment = Alignment(horizontal="right")
        if "Neta" in label or "Disponible" in label:
            c1.font = TOTAL_FONT
            c2.font = TOTAL_FONT
            c1.fill = TOTAL_FILL
            c2.fill = TOTAL_FILL

    # Saldos por Cuenta
    ws_resumen.cell(row=16, column=1, value="Cuenta Financiera")
    ws_resumen.cell(row=16, column=2, value="Saldo Actual")
    style_header_row(ws_resumen, 16, 2)
    for idx, acc in enumerate(metrics["accounts"], 17):
        c1 = ws_resumen.cell(row=idx, column=1, value=acc["name"])
        c2 = ws_resumen.cell(row=idx, column=2, value=acc["balance"])
        c1.border = BORDER_THIN
        c2.border = BORDER_THIN
        c2.number_format = CURRENCY_FORMAT
        c2.alignment = Alignment(horizontal="right")

    auto_fit_columns(ws_resumen, 3)

    # Hoja 2: Inventario & Stock
    ws_stock = wb.create_sheet(title="Catálogo y Stock")
    ws_stock.views.sheetView[0].showGridLines = True
    ws_stock["A1"] = "productos.bona — Inventario Físico y Valuación"
    ws_stock["A1"].font = TITLE_FONT

    stock_headers = ["ID", "SKU", "Producto", "Rubro / Categoría", "Costo Unit.", "Precio Venta", "Margen Unitario", "Margen %", "Stock Actual", "Valuación Costo", "Valuación Venta"]
    for col_idx, h in enumerate(stock_headers, 1):
        ws_stock.cell(row=3, column=col_idx, value=h)
    style_header_row(ws_stock, 3, len(stock_headers))

    products = crud.get_products(db, active_only=False)
    for r_idx, p in enumerate(products, 4):
        cat_name = p.category.name if p.category else "General"
        cost_val = round(p.cost_price * p.stock_quantity, 2)
        sale_val = round(p.sale_price * p.stock_quantity, 2)
        row_vals = [
            p.id,
            p.sku or "-",
            p.name,
            cat_name,
            p.cost_price,
            p.sale_price,
            p.estimated_unit_margin,
            p.estimated_margin_pct / 100,
            p.stock_quantity,
            cost_val,
            sale_val
        ]
        for c_idx, v in enumerate(row_vals, 1):
            c = ws_stock.cell(row=r_idx, column=c_idx, value=v)
            c.border = BORDER_THIN
            if c_idx in [5, 6, 7, 10, 11]:
                c.number_format = CURRENCY_FORMAT
                c.alignment = Alignment(horizontal="right")
            elif c_idx == 8:
                c.number_format = PERCENT_FORMAT
                c.alignment = Alignment(horizontal="right")
            elif c_idx in [1, 2, 9]:
                c.alignment = Alignment(horizontal="center")

    auto_fit_columns(ws_stock, len(stock_headers))

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def import_products_from_excel(db: Session, file_content: bytes) -> Dict[str, Any]:
    """Importación masiva ágil de catálogo de productos desde Excel (.xlsx o .csv)"""
    created_count = 0
    updated_count = 0
    errors = []

    # Cargar workbook
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as e:
        return {"success": False, "error": f"Formato inválido de Excel: {str(e)}"}

    if not rows or len(rows) < 2:
        return {"success": False, "error": "El archivo no contiene filas de datos."}

    # Mapear encabezados
    header_row = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
    
    col_map = {}
    for idx, name in enumerate(header_row):
        if "producto" in name or "nombre" in name:
            col_map["name"] = idx
        elif "rubro" in name or "categoria" in name or "categoría" in name:
            col_map["category"] = idx
        elif "sku" in name or "código" in name or "codigo" in name:
            col_map["sku"] = idx
        elif "costo" in name:
            col_map["cost"] = idx
        elif "precio" in name or "venta" in name:
            col_map["price"] = idx
        elif "stock" in name or "cantidad" in name:
            col_map["stock"] = idx
        elif "min" in name or "alerta" in name:
            col_map["min_stock"] = idx

    if "name" not in col_map:
        return {"success": False, "error": "No se encontró la columna de 'Producto' o 'Nombre' en el encabezado."}

    # Procesar filas
    for r_num, row in enumerate(rows[1:], 2):
        name_val = row[col_map["name"]]
        if not name_val:
            continue
        prod_name = str(name_val).strip()

        # Categoría
        cat_id = None
        if "category" in col_map and row[col_map["category"]]:
            cat_name = str(row[col_map["category"]]).strip()
            cat = db.query(Category).filter(Category.name.ilike(cat_name)).first()
            if not cat:
                cat = Category(name=cat_name)
                db.add(cat)
                db.flush()
            cat_id = cat.id

        sku_val = str(row[col_map["sku"]]).strip() if "sku" in col_map and row[col_map["sku"]] else None
        
        try:
            cost_val = float(row[col_map["cost"]]) if "cost" in col_map and row[col_map["cost"]] is not None else 0.0
        except (ValueError, TypeError):
            cost_val = 0.0

        try:
            price_val = float(row[col_map["price"]]) if "price" in col_map and row[col_map["price"]] is not None else 0.0
        except (ValueError, TypeError):
            price_val = 0.0

        try:
            stock_val = int(row[col_map["stock"]]) if "stock" in col_map and row[col_map["stock"]] is not None else 0
        except (ValueError, TypeError):
            stock_val = 0

        # Buscar si ya existe por nombre o SKU
        existing = db.query(Product).filter(Product.name.ilike(prod_name)).first()
        if not existing and sku_val:
            existing = db.query(Product).filter(Product.sku == sku_val).first()

        if existing:
            existing.cost_price = cost_val
            existing.sale_price = price_val
            existing.stock_quantity = stock_val
            if cat_id:
                existing.category_id = cat_id
            if sku_val:
                existing.sku = sku_val
            updated_count += 1
        else:
            new_prod = Product(
                name=prod_name,
                sku=sku_val,
                category_id=cat_id,
                cost_price=cost_val,
                sale_price=price_val,
                stock_quantity=stock_val,
                min_stock_alert=5
            )
            db.add(new_prod)
            created_count += 1

    db.commit()
    return {
        "success": True, 
        "created": created_count, 
        "updated": updated_count, 
        "total": created_count + updated_count
    }
