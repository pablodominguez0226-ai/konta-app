import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response, Depends, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext

# Configuración de Timezone
TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")

# Configuración de Base de Datos SQLite
DEFAULT_DB = "/app/data/bona.db" if os.path.exists("/app/data") else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "bona.db"))
DB_PATH = os.getenv("DATABASE_PATH", DEFAULT_DB)
if DB_PATH.startswith("/app/") and not os.path.exists("/app"):
    local_data = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    chosen_name = os.path.basename(DB_PATH)
    DB_PATH = os.path.join(local_data, chosen_name)

# Configuración de Seguridad y JWT
SECRET_KEY = os.getenv("SECRET_KEY", "konta-enterprise-secure-jwt-key-2026-production-ready-93f8e1")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
COOKIE_NAME = "access_token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Tabla usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nombre TEXT NOT NULL,
        rol TEXT DEFAULT 'user',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Verificar o crear cuenta de Administrador principal
    admin_email = os.getenv("ADMIN_EMAIL", "admin@konta.app").strip().lower()
    admin_pass = os.getenv("ADMIN_PASSWORD", "Admin1234!")

    cursor.execute("SELECT id FROM usuarios WHERE rol = 'admin' LIMIT 1;")
    admin_row = cursor.fetchone()

    if not admin_row:
        cursor.execute("SELECT id FROM usuarios WHERE email = ? LIMIT 1;", (admin_email,))
        existing_user = cursor.fetchone()
        if existing_user:
            cursor.execute(
                "UPDATE usuarios SET rol = 'admin', password_hash = ? WHERE id = ?;",
                (get_password_hash(admin_pass), existing_user["id"])
            )
            admin_id = existing_user["id"]
        else:
            admin_hash = get_password_hash(admin_pass)
            cursor.execute("""
            INSERT INTO usuarios (email, password_hash, nombre, rol)
            VALUES (?, ?, ?, 'admin');
            """, (admin_email, admin_hash, "Admin Konta"))
            admin_id = cursor.lastrowid
    else:
        admin_id = admin_row["id"]
        # Asegurar credencial default en la cuenta admin@konta.app
        cursor.execute("SELECT id, password_hash FROM usuarios WHERE email = ?;", (admin_email,))
        default_admin = cursor.fetchone()
        if default_admin:
            if not verify_password(admin_pass, default_admin["password_hash"]):
                cursor.execute(
                    "UPDATE usuarios SET password_hash = ?, rol = 'admin' WHERE id = ?;",
                    (get_password_hash(admin_pass), default_admin["id"])
                )

    # 2. Tabla ventas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
        fecha DATETIME NOT NULL,
        cliente TEXT DEFAULT 'Consumidor Final',
        canal TEXT NOT NULL,
        producto TEXT NOT NULL,
        cantidad INTEGER NOT NULL CHECK (cantidad >= 1),
        costo_unitario REAL NOT NULL,
        precio_unitario REAL NOT NULL,
        total_cobrado REAL NOT NULL,
        costo_reposicion REAL NOT NULL,
        margen_neto REAL NOT NULL,
        medio_pago TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'Cobrado'
    );
    """)

    # Migración: Verificar si la columna usuario_id existe en ventas
    cursor.execute("PRAGMA table_info(ventas);")
    columnas_ventas = [col["name"] for col in cursor.fetchall()]
    if "usuario_id" not in columnas_ventas:
        cursor.execute("ALTER TABLE ventas ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id);")
        cursor.execute("UPDATE ventas SET usuario_id = ? WHERE usuario_id IS NULL;", (admin_id,))

    # 3. Tabla gastos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
        fecha DATETIME NOT NULL,
        categoria TEXT NOT NULL,
        monto REAL NOT NULL,
        descripcion TEXT NOT NULL
    );
    """)

    # Migración: Verificar si la columna usuario_id existe en gastos
    cursor.execute("PRAGMA table_info(gastos);")
    columnas_gastos = [col["name"] for col in cursor.fetchall()]
    if "usuario_id" not in columnas_gastos:
        cursor.execute("ALTER TABLE gastos ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id);")
        cursor.execute("UPDATE gastos SET usuario_id = ? WHERE usuario_id IS NULL;", (admin_id,))

    # 4. Índices para acelerar el filtrado por usuario_id y búsquedas
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_usuario ON ventas(usuario_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_usuario ON gastos(usuario_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios(rol);")

    # 5. Semilla inicial demostrativa asignada únicamente al admin si no tiene ventas
    cursor.execute("SELECT COUNT(*) FROM ventas WHERE usuario_id = ?;", (admin_id,))
    count_ventas = cursor.fetchone()[0]
    if count_ventas == 0:
        ahora = datetime.now(TZ_AR)
        ventas_demo = [
            (admin_id, ahora - timedelta(days=2, hours=3), "Camila Fernández", "Instagram", "Mochila Urbana Impermeable", 2, 12500.0, 24500.0, 49000.0, 25000.0, 24000.0, "Mercado Pago", "Cobrado"),
            (admin_id, ahora - timedelta(days=1, hours=5), "Marcos Rossi", "WhatsApp", "Auriculares Inalámbricos Pro", 1, 18500.0, 36000.0, 36000.0, 18500.0, 17500.0, "Transferencia Bancaria", "Cobrado"),
            (admin_id, ahora - timedelta(hours=6), "Consumidor Final", "Venta Directa", "Termo Acero Inoxidable 1L", 3, 7200.0, 14900.0, 44700.0, 21600.0, 23100.0, "Efectivo", "Cobrado"),
            (admin_id, ahora - timedelta(hours=2), "Lucía Morales", "Mercado Libre", "Cargador Rápido 30W USB-C", 1, 6200.0, 13500.0, 13500.0, 6200.0, 7300.0, "Mercado Pago", "Pendiente"),
        ]
        cursor.executemany("""
        INSERT INTO ventas (usuario_id, fecha, cliente, canal, producto, cantidad, costo_unitario, precio_unitario, total_cobrado, costo_reposicion, margen_neto, medio_pago, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [(v[0], v[1].strftime("%Y-%m-%d %H:%M:%S"), *v[2:]) for v in ventas_demo])

        gastos_demo = [
            (admin_id, (ahora - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), "Publicidad Meta/Ads", 15000.0, "Campaña Ads Lanzamiento Konta"),
            (admin_id, (ahora - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), "Packaging", 8500.0, "Cajas y cinta de embalar"),
        ]
        cursor.executemany("""
        INSERT INTO gastos (usuario_id, fecha, categoria, monto, descripcion)
        VALUES (?, ?, ?, ?, ?);
        """, gastos_demo)

    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Konta — Gestión de Ventas & Flujo Financiero",
    description="Sistema multiusuario independiente, ágil y seguro para el control de ventas, egresos y caja bajo metodología Lumelí.",
    version="2.0.0",
    lifespan=lifespan
)

# Configuración de templates Jinja2
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Montar archivos estáticos si la carpeta existe
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ==========================================================
# ESQUEMAS PYDANTIC
# ==========================================================

class UserRegister(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=128)

class UserLogin(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=1)

class ResetPasswordRequest(BaseModel):
    usuario_id: int
    nueva_password: str = Field(min_length=6, max_length=128)

class CambiarRolRequest(BaseModel):
    usuario_id: int
    nuevo_rol: str = Field(pattern="^(admin|user)$")

class VentaCreate(BaseModel):
    cliente: Optional[str] = "Consumidor Final"
    canal: str
    producto: str
    cantidad: int = Field(ge=1)
    costo_unitario: float = Field(ge=0)
    precio_unitario: float = Field(ge=0)
    medio_pago: str
    estado: Optional[str] = "Cobrado"

class GastoCreate(BaseModel):
    categoria: str
    monto: float = Field(gt=0)
    descripcion: str

class EstadoUpdate(BaseModel):
    estado: str

# ==========================================================
# DEPENDENCIAS DE AUTENTICACIÓN Y ROLES
# ==========================================================

async def get_current_user_optional(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, nombre, rol, created_at FROM usuarios WHERE id = ?;", (int(user_id),))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "email": row["email"],
        "nombre": row["nombre"],
        "rol": row["rol"],
        "created_at": str(row["created_at"])
    }

async def get_current_user(request: Request) -> dict:
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Por favor inicie sesión en Konta."
        )
    return user

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. Se requiere rol de Super-Administrador para realizar esta acción."
        )
    return current_user

# ==========================================================
# RUTAS DE INTERFAZ HTML
# ==========================================================

@app.get("/", response_class=HTMLResponse)
async def vista_principal(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "user": user}
    )

@app.get("/login", response_class=HTMLResponse)
async def vista_login(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request}
    )

@app.get("/admin", response_class=HTMLResponse)
async def vista_admin(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.get("rol") != "admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"request": request, "user": user}
    )

@app.get("/logout")
async def logout_redirect(response: Response):
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp

# ==========================================================
# REST API: AUTENTICACIÓN & SESIONES
# ==========================================================

@app.post("/api/auth/register")
async def register_user(payload: UserRegister, response: Response):
    email = payload.email.strip().lower()
    nombre = payload.nombre.strip()
    password = payload.password

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Formato de email inválido.")
    if len(nombre) < 2:
        raise HTTPException(status_code=400, detail="El nombre debe tener al menos 2 caracteres.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener un mínimo de 6 caracteres.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE email = ?;", (email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Este correo ya se encuentra registrado.")

    password_hash = get_password_hash(password)
    cursor.execute("""
    INSERT INTO usuarios (email, password_hash, nombre, rol)
    VALUES (?, ?, ?, 'user');
    """, (email, password_hash, nombre))
    new_user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Generar token JWT y fijar cookie HTTP-Only
    token = create_access_token(data={"sub": str(new_user_id), "email": email, "nombre": nombre, "rol": "user"})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * ACCESS_TOKEN_EXPIRE_DAYS,
        expires=60 * 60 * 24 * ACCESS_TOKEN_EXPIRE_DAYS,
        samesite="lax",
        path="/"
    )

    return {
        "status": "success",
        "message": "Cuenta creada exitosamente en Konta.",
        "user": {
            "id": new_user_id,
            "email": email,
            "nombre": nombre,
            "rol": "user"
        }
    }

@app.post("/api/auth/login")
async def login_user(payload: UserLogin, response: Response):
    email = payload.email.strip().lower()
    password = payload.password

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, password_hash, nombre, rol FROM usuarios WHERE email = ?;", (email,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Correo electrónico o contraseña incorrectos.")

    token = create_access_token(data={"sub": str(user["id"]), "email": user["email"], "nombre": user["nombre"], "rol": user["rol"]})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * ACCESS_TOKEN_EXPIRE_DAYS,
        expires=60 * 60 * 24 * ACCESS_TOKEN_EXPIRE_DAYS,
        samesite="lax",
        path="/"
    )

    return {
        "status": "success",
        "message": "Inicio de sesión exitoso.",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "nombre": user["nombre"],
            "rol": user["rol"]
        }
    }

@app.post("/api/auth/logout")
async def logout_user(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "success", "message": "Sesión cerrada correctamente."}

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": "Konta",
        "version": "2.0.0",
        "timestamp": datetime.now(TZ_AR).isoformat()
    }

# ==========================================================
# REST API: PANEL DE SUPER-ADMINISTRADOR (EXCLUSIVO ADMIN)
# ==========================================================

@app.get("/api/admin/stats")
async def admin_stats(admin_user: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()

    # Total usuarios
    cursor.execute("SELECT COUNT(*) AS total_usuarios FROM usuarios;")
    total_usuarios = cursor.fetchone()["total_usuarios"]

    # Ventas totales y cobradas
    cursor.execute("""
    SELECT 
        COUNT(id) AS total_ventas_count,
        COALESCE(SUM(CASE WHEN estado = 'Cobrado' THEN total_cobrado ELSE 0 END), 0) AS facturacion_global,
        COALESCE(SUM(CASE WHEN estado = 'Cobrado' THEN costo_reposicion ELSE 0 END), 0) AS fondo_reposicion_global,
        COALESCE(SUM(CASE WHEN estado = 'Cobrado' THEN margen_neto ELSE 0 END), 0) AS ganancia_bruta_global
    FROM ventas;
    """)
    row_v = cursor.fetchone()
    total_ventas_count = row_v["total_ventas_count"]
    facturacion_global = round(row_v["facturacion_global"], 2)
    fondo_reposicion_global = round(row_v["fondo_reposicion_global"], 2)
    ganancia_bruta_global = round(row_v["ganancia_bruta_global"], 2)

    # Gastos totales del sistema
    cursor.execute("SELECT COALESCE(SUM(monto), 0) AS gastos_globales FROM gastos;")
    gastos_globales = round(cursor.fetchone()["gastos_globales"], 2)
    ganancia_limpia_global = round(ganancia_bruta_global - gastos_globales, 2)

    conn.close()

    return {
        "total_usuarios": total_usuarios,
        "total_ventas_count": total_ventas_count,
        "facturacion_global": facturacion_global,
        "fondo_reposicion_global": fondo_reposicion_global,
        "gastos_globales": gastos_globales,
        "ganancia_limpia_global": ganancia_limpia_global
    }

@app.get("/api/admin/usuarios")
async def admin_listar_usuarios(admin_user: dict = Depends(require_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        u.id,
        u.nombre,
        u.email,
        u.rol,
        u.created_at,
        COUNT(v.id) AS ventas_count,
        COALESCE(SUM(CASE WHEN v.estado = 'Cobrado' THEN v.total_cobrado ELSE 0 END), 0) AS total_facturado,
        COALESCE(SUM(CASE WHEN v.estado = 'Cobrado' THEN v.margen_neto ELSE 0 END), 0) AS total_margen
    FROM usuarios u
    LEFT JOIN ventas v ON v.usuario_id = u.id
    GROUP BY u.id
    ORDER BY u.id ASC;
    """)
    rows = cursor.fetchall()
    usuarios = []
    for r in rows:
        usuarios.append({
            "id": r["id"],
            "nombre": r["nombre"],
            "email": r["email"],
            "rol": r["rol"],
            "created_at": str(r["created_at"]),
            "ventas_count": r["ventas_count"],
            "total_facturado": round(r["total_facturado"], 2),
            "total_margen": round(r["total_margen"], 2)
        })
    conn.close()
    return usuarios

@app.post("/api/admin/reset-password")
async def admin_reset_password(payload: ResetPasswordRequest, admin_user: dict = Depends(require_admin)):
    new_password = payload.nueva_password.strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe contener al menos 6 caracteres.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, nombre FROM usuarios WHERE id = ?;", (payload.usuario_id,))
    target_user = cursor.fetchone()
    if not target_user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    new_hash = get_password_hash(new_password)
    cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?;", (new_hash, payload.usuario_id))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Contraseña restablecida con éxito para {target_user['nombre']} ({target_user['email']}).",
        "usuario_id": payload.usuario_id
    }

@app.post("/api/admin/cambiar-rol")
async def admin_cambiar_rol(payload: CambiarRolRequest, admin_user: dict = Depends(require_admin)):
    if payload.nuevo_rol not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Rol inválido. Debe ser 'admin' o 'user'.")

    # Si el admin se degrada a sí mismo, verificar que quede al menos otro admin
    if payload.usuario_id == admin_user["id"] and payload.nuevo_rol != "admin":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS c FROM usuarios WHERE rol = 'admin';")
        count_admins = cursor.fetchone()["c"]
        conn.close()
        if count_admins <= 1:
            raise HTTPException(
                status_code=400,
                detail="Operación bloqueada: no puedes revocar tu rol de administrador siendo el único admin del sistema."
            )

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, nombre FROM usuarios WHERE id = ?;", (payload.usuario_id,))
    target_user = cursor.fetchone()
    if not target_user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    cursor.execute("UPDATE usuarios SET rol = ? WHERE id = ?;", (payload.nuevo_rol, payload.usuario_id))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Rol de {target_user['nombre']} modificado a '{payload.nuevo_rol}'.",
        "usuario_id": payload.usuario_id,
        "nuevo_rol": payload.nuevo_rol
    }

@app.delete("/api/admin/usuarios/{usuario_id}")
async def admin_eliminar_usuario(usuario_id: int, admin_user: dict = Depends(require_admin)):
    if usuario_id == admin_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operación inválida: no puedes eliminar tu propia cuenta de administrador en sesión."
        )

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, nombre FROM usuarios WHERE id = ?;", (usuario_id,))
    target_user = cursor.fetchone()
    if not target_user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Eliminar ventas y gastos en cascada del usuario a eliminar
    cursor.execute("DELETE FROM ventas WHERE usuario_id = ?;", (usuario_id,))
    cursor.execute("DELETE FROM gastos WHERE usuario_id = ?;", (usuario_id,))
    cursor.execute("DELETE FROM usuarios WHERE id = ?;", (usuario_id,))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Usuario {target_user['nombre']} y todos sus registros han sido eliminados de Konta.",
        "usuario_id": usuario_id
    }

# ==========================================================
# REST API: VENTAS & GASTOS (AISLAMIENTO ESTRICTO POR USUARIO)
# ==========================================================

@app.post("/api/venta")
async def registrar_venta(v: VentaCreate, current_user: dict = Depends(get_current_user)):
    usuario_id = current_user["id"]
    cantidad = max(1, v.cantidad)
    costo_u = float(v.costo_unitario)
    precio_u = float(v.precio_unitario)
    total_cobrado = round(cantidad * precio_u, 2)
    costo_reposicion = round(cantidad * costo_u, 2)
    margen_neto = round(total_cobrado - costo_reposicion, 2)
    fecha_ar = datetime.now(TZ_AR).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO ventas (usuario_id, fecha, cliente, canal, producto, cantidad, costo_unitario, precio_unitario, total_cobrado, costo_reposicion, margen_neto, medio_pago, estado)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        usuario_id,
        fecha_ar,
        v.cliente.strip() if v.cliente else "Consumidor Final",
        v.canal,
        v.producto.strip(),
        cantidad,
        costo_u,
        precio_u,
        total_cobrado,
        costo_reposicion,
        margen_neto,
        v.medio_pago,
        v.estado or "Cobrado"
    ))
    venta_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": venta_id,
        "usuario_id": usuario_id,
        "fecha": fecha_ar,
        "total_cobrado": total_cobrado,
        "costo_reposicion": costo_reposicion,
        "margen_neto": margen_neto,
        "estado": v.estado
    }

@app.post("/api/gasto")
async def registrar_gasto(g: GastoCreate, current_user: dict = Depends(get_current_user)):
    usuario_id = current_user["id"]
    fecha_ar = datetime.now(TZ_AR).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO gastos (usuario_id, fecha, categoria, monto, descripcion)
    VALUES (?, ?, ?, ?, ?);
    """, (usuario_id, fecha_ar, g.categoria, round(g.monto, 2), g.descripcion.strip()))
    gasto_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": gasto_id,
        "usuario_id": usuario_id,
        "fecha": fecha_ar,
        "monto": g.monto
    }

# ==========================================================
# REST API: MÉTRICAS Y FLUJO LUMELÍ (FILTRADO POR USUARIO)
# ==========================================================

@app.get("/api/metricas")
async def obtener_metricas(current_user: dict = Depends(get_current_user)):
    usuario_id = current_user["id"]
    conn = get_db()
    cursor = conn.cursor()

    # 1. Facturación Total, Fondo de Reposición y Margen de ventas Cobradas
    cursor.execute("""
    SELECT 
        COALESCE(SUM(total_cobrado), 0) AS facturacion_total,
        COALESCE(SUM(costo_reposicion), 0) AS fondo_reposicion,
        COALESCE(SUM(margen_neto), 0) AS ganancia_bruta,
        COUNT(id) AS ventas_cobradas_count
    FROM ventas
    WHERE usuario_id = ? AND estado = 'Cobrado';
    """, (usuario_id,))
    row_ventas = cursor.fetchone()
    facturacion_total = round(row_ventas["facturacion_total"], 2)
    fondo_reposicion = round(row_ventas["fondo_reposicion"], 2)
    ganancia_bruta = round(row_ventas["ganancia_bruta"], 2)
    ventas_count = row_ventas["ventas_cobradas_count"]

    # 2. Gastos Totales del usuario
    cursor.execute("""
    SELECT COALESCE(SUM(monto), 0) AS gastos_totales 
    FROM gastos 
    WHERE usuario_id = ?;
    """, (usuario_id,))
    row_gastos = cursor.fetchone()
    gastos_totales = round(row_gastos["gastos_totales"], 2)

    # 3. Ganancia Limpia Acumulada
    ganancia_limpia = round(ganancia_bruta - gastos_totales, 2)

    # 4. Distribución por Canal
    cursor.execute("""
    SELECT canal, COALESCE(SUM(total_cobrado), 0) AS total
    FROM ventas
    WHERE usuario_id = ? AND estado = 'Cobrado'
    GROUP BY canal;
    """, (usuario_id,))
    canales_db = {r["canal"]: round(r["total"], 2) for r in cursor.fetchall()}
    canales_ordenados = ["Mercado Libre", "Instagram", "WhatsApp", "TikTok", "Venta Directa"]
    distribucion_canal = {c: canales_db.get(c, 0.0) for c in canales_ordenados}

    # 5. Facturación acumulada reciente (últimos 7 días)
    ahora = datetime.now(TZ_AR)
    facturacion_reciente = []
    for i in range(6, -1, -1):
        dia = ahora - timedelta(days=i)
        dia_str = dia.strftime("%Y-%m-%d")
        dia_label = dia.strftime("%d/%m")
        cursor.execute("""
        SELECT COALESCE(SUM(total_cobrado), 0) as total
        FROM ventas
        WHERE usuario_id = ? AND estado = 'Cobrado' AND date(fecha) = date(?);
        """, (usuario_id, dia_str))
        tot_dia = round(cursor.fetchone()["total"], 2)
        facturacion_reciente.append({"fecha": dia_label, "total": tot_dia})

    conn.close()

    return {
        "facturacion_total": facturacion_total,
        "fondo_reposicion": fondo_reposicion,
        "ganancia_limpia": ganancia_limpia,
        "gastos_totales": gastos_totales,
        "ventas_count": ventas_count,
        "distribucion_canal": distribucion_canal,
        "facturacion_reciente": facturacion_reciente
    }

# ==========================================================
# REST API: HISTORIAL Y GESTIÓN DE ÓRDENES (FILTRADO POR USUARIO)
# ==========================================================

@app.get("/api/ordenes")
async def listar_ordenes(limit: int = 50, current_user: dict = Depends(get_current_user)):
    usuario_id = current_user["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, fecha, cliente, canal, producto, cantidad, costo_unitario, precio_unitario,
           total_cobrado, costo_reposicion, margen_neto, medio_pago, estado
    FROM ventas
    WHERE usuario_id = ?
    ORDER BY id DESC
    LIMIT ?;
    """, (usuario_id, limit))
    rows = cursor.fetchall()
    ordenes = [dict(r) for r in rows]
    conn.close()
    return ordenes

@app.patch("/api/ordenes/{orden_id}/estado")
@app.post("/api/ordenes/{orden_id}/estado")
async def cambiar_estado_orden(orden_id: int, payload: EstadoUpdate, current_user: dict = Depends(get_current_user)):
    usuario_id = current_user["id"]
    nuevo_estado = payload.estado
    if nuevo_estado not in ["Cobrado", "Pendiente", "Cancelado"]:
        raise HTTPException(status_code=400, detail="Estado inválido. Debe ser Cobrado, Pendiente o Cancelado.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE ventas 
    SET estado = ? 
    WHERE id = ? AND usuario_id = ?;
    """, (nuevo_estado, orden_id, usuario_id))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Orden no encontrada o no pertenece a tu cuenta.")

    conn.commit()
    conn.close()
    return {"success": True, "id": orden_id, "estado": nuevo_estado}

@app.delete("/api/ordenes/{orden_id}")
async def eliminar_orden(orden_id: int, current_user: dict = Depends(get_current_user)):
    usuario_id = current_user["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    DELETE FROM ventas 
    WHERE id = ? AND usuario_id = ?;
    """, (orden_id, usuario_id))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Orden no encontrada o no pertenece a tu cuenta.")

    conn.commit()
    conn.close()
    return {"success": True, "id": orden_id}
