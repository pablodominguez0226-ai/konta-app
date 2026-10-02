# 🌿 productos.bona — Gestión Ágil de Ventas y Flujo Financiero

> **Aplicación web completa inspirada en el flujo ágil de Lumelí**, diseñada para el negocio multirrubro **"productos.bona"**. Reemplaza definitivamente las planillas de Excel mediante un sistema rápido, intuitivo y responsivo (diseñado para operar desde el celular en 10 segundos o desde la PC), corriendo en **Docker** y expuesta a través de **Ngrok**.

---

## 🚀 Pilares y Funcionalidades Principales

### 1. ⚡ Punto de Venta Ágil (Modo Lumelí 10s)
* **Búsqueda predictiva instantánea:** Filtrado en tiempo real por nombre, SKU o píldoras de categorías multirrubro (Pisos, Mopas, Limpiadores, Fragancias, Cuidado Personal).
* **Cálculo de márgenes en vivo:** Al seleccionar productos, calcula al instante:
  * Total a cobrar
  * Costo real de reposición (CMV)
  * Ganancia Bruta en pesos ($) y Margen porcentual (%)
* **Precios unitarios editables al vuelo:** Permite aplicar descuentos personalizados por cliente sin alterar el catálogo maestro.
* **Integración con WhatsApp:** Envío con 1 clic de un comprobante / ticket digital estilizado y formateado directo al WhatsApp del cliente.
* **Descuento automático de inventario:** Sincronización en tiempo real del stock físico.

### 2. 📊 Dashboard de Rentabilidad y Métricas Reales
* **Píldoras de períodos ágiles:** Hoy, Ayer, Últimos 7 Días, Este Mes, Histórico completo.
* **Métricas clave:**
  * Facturación Bruta ($) y Cantidad de órdenes
  * Costo de Mercadería Vendida (CMV)
  * Ganancia Bruta y Margen Bruto (%)
  * Gastos Operativos totales
  * **Ganancia Neta Real (En el bolsillo)** y Margen Neto (%)
* **Gráficos interactivos (Chart.js):**
  * Evolución diaria de Ingresos vs Egresos vs Ganancia neta.
  * Distribución de ventas por canal (Instagram, WhatsApp, Local, Mercado Libre).
  * Distribución de gastos por categoría operativa.
* **Top 5 productos más rentables:** Identificación de productos estrella por volumen y margen.
* **Alertas Lumelí:** Detección de productos en stock crítico (< 5 unidades) y ventas pendientes de cobro.

### 3. 💸 Flujo de Fondos & Conciliación de Cajas
* **Saldos en tiempo real por cuenta:**
  * 💵 Caja Efectivo
  * 💳 Mercado Pago
  * 🏦 Cuenta Bancaria
* **Transferencias internas entre cuentas:** Movimientos de fondos (ej: transferir de Mercado Pago al Banco o retiro de Efectivo) con registro de motivo.
* **Control de gastos operativos:** Carga rápida categorizada (Mercadería, Envíos, Publicidad Meta Ads, Packaging, Servicios, Sueldos) con impacto directo en el saldo de la cuenta elegida.
* **Reversión segura:** Si se anula una venta o se elimina un gasto, el saldo de la caja y el stock se reintegran automáticamente.

### 4. 📑 Reemplazo Definitivo de Excel
* **Exportación oficial en `.xlsx`:**
  * *Libro Contable Integral:* Resumen Ejecutivo + Ventas + Gastos + Valuación de Inventario.
  * *Planilla de Ventas:* Con fórmulas `=SUM(...)` automáticas para totales y costos.
  * *Planilla de Gastos:* Historial detallado por categoría.
* **Importación Masiva de Productos:** Subí cualquier archivo `.xlsx` o `.csv` con tu catálogo previo y el sistema actualizará o creará los productos automáticamente.

---

## 🛠️ Arquitectura y Tecnologías

* **Backend:** FastAPI (Python 3.12) con concurrencia asíncrona.
* **Base de Datos:** SQLite con modo **WAL (Write-Ahead Logging)** habilitado y claves foráneas activas para máxima velocidad y cero bloqueos de concurrencia.
* **Frontend:** HTML5 semántico, Tailwind CSS, FontAwesome 6, Chart.js y Vanilla JS táctil (ultra liviano para redes móviles 4G/5G).
* **Contenedores:** Docker + Docker Compose.
* **Exposición y Túnel:** Ngrok oficial (`ngrok/ngrok:latest`).

---

## 📁 Estructura del Proyecto

```text
bona-app/
├── docker-compose.yml          # Orquestación de App + Ngrok
├── Dockerfile                  # Imagen optimizada Python 3.12-slim
├── requirements.txt            # Dependencias (FastAPI, SQLAlchemy, openpyxl, etc.)
├── .env                        # Variables de entorno y token de Ngrok
├── data/                       # Volumen persistente para la BD SQLite
│   └── bona.db
├── app/
│   ├── main.py                 # Enrutamiento, APIs REST y vistas Jinja2
│   ├── database.py             # Configuración SQLite con modo WAL
│   ├── models.py               # Modelos SQLAlchemy (Productos, Ventas, Gastos, Cuentas)
│   ├── schemas.py              # Esquemas Pydantic
│   ├── crud.py                 # Lógica de negocio y cálculo de métricas financieras
│   ├── seed.py                 # Datos semilla iniciales para productos.bona
│   ├── excel_manager.py        # Generador de reportes Excel (.xlsx) e importador
│   ├── static/
│   │   └── js/app.js           # Lógica frontend, toasts y modales
│   └── templates/
│       ├── base.html           # Layout responsivo (Bottom bar mobile + Sidebar desktop)
│       ├── dashboard.html      # Panel financiero en vivo
│       ├── pos.html            # Punto de Venta Ágil en 10s
│       ├── sales.html          # Historial de ventas y comprobantes
│       ├── expenses.html       # Control de gastos y cajas
│       ├── inventory.html      # Catálogo y control de stock
│       └── excel_tools.html    # Centro de importación y exportación Excel
```

---

## ⚙️ Despliegue y Ejecución

### 1. Variables de Entorno (`.env`)
Crear o editar el archivo `.env`:
```bash
NGROK_AUTHTOKEN=<TU_TOKEN_DE_NGROK_DONDE_RESERVASTE_EL_DOMINIO>
NGROK_DOMAIN=surcharge-subtract-footer.ngrok-free.dev
PORT=8005
```

> ⚠️ **Nota Importante sobre Ngrok (`ERR_NGROK_320`):**
> El dominio estático gratuito `surcharge-subtract-footer.ngrok-free.dev` está asociado a una cuenta específica de Ngrok. Para que el túnel inicie sin errores, el valor de `NGROK_AUTHTOKEN` en el archivo `.env` debe corresponder a la cuenta donde se reservó ese subdominio. Puedes obtener el token en [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken).

### 2. Iniciar con Docker Compose
```bash
cd ~/bona-app
docker compose up -d --build
```

### 3. Accesos Disponibles
* **En la Red Local / Servidor:** `http://localhost:8005` (o `http://192.168.100.95:8005`)
* **Acceso Remoto por Ngrok:** `https://surcharge-subtract-footer.ngrok-free.dev`
