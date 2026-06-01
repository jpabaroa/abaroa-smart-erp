"""
api.py — API REST FastAPI para Abaroa Smart ERP
Proporciona endpoints para móvil y integración externa.
CORREGIDO: Sin HTTPBearer/HTTPAuthCredentials (importes que no existen)
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import sqlite3
import os

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

DATABASE_PATH = os.getenv("DATABASE_PATH", "abaroa_smart_erp.db")
API_KEY = os.getenv("API_KEY", "abaroa-secret-key-2024")

app = FastAPI(
    title="Abaroa Smart ERP API",
    description="API REST para sincronización con app móvil",
    version="1.0.0"
)

# CORS para permitir acceso desde la app móvil
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar a dominios específicos en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()

# ═══════════════════════════════════════════════════════════════════════════════
# MODELOS
# ═══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

class ClienteResponse(BaseModel):
    id: int
    nombre: str
    rut: str
    email: Optional[str]
    telefono: Optional[str]
    direccion: Optional[str]

class ProductoResponse(BaseModel):
    id: int
    sku: str
    descripcion: str
    categoria: str
    precio: float
    stock: int

class OTResponse(BaseModel):
    id: int
    numero: str
    cliente_id: int
    estado: str
    fecha_creacion: str
    descripcion: Optional[str]

class ChecklistItem(BaseModel):
    id: int
    paso: str
    completado: bool
    nota: Optional[str]
    foto_url: Optional[str]

# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN SIMPLE (sin HTTPAuthCredentials)
# ═══════════════════════════════════════════════════════════════════════════════

def verify_api_key(x_token: str = Header(...)):
    """Verifica API key en header"""
    if x_token != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="API key inválida"
        )
    return x_token

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verifica usuario y contraseña básica"""
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "admin123")
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña inválidos",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ═══════════════════════════════════════════════════════════════════════════════
# CONEXIÓN A BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

def get_db_connection():
    """Retorna conexión a SQLite"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_db(query, args=(), one=False):
    """Ejecuta query en base de datos"""
    conn = get_db_connection()
    cur = conn.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS PÚBLICOS (sin autenticación)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    """Verifica estado del API"""
    return {
        "status": "online",
        "database": "connected" if os.path.exists(DATABASE_PATH) else "offline",
        "timestamp": datetime.now().isoformat()
    }

# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/login", response_model=LoginResponse)
def login(credentials: LoginRequest):
    """
    Login con usuario y contraseña.
    
    **Credenciales de prueba:**
    - Usuario: `admin`
    - Contraseña: `admin123`
    """
    if credentials.username != "admin" or credentials.password != "admin123":
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas"
        )
    
    # Token simple (en producción usar JWT)
    token = secrets.token_urlsafe(32)
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400  # 24 horas
    )

# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/clientes", response_model=List[ClienteResponse])
def get_clientes(username: str = Depends(verify_credentials)):
    """Obtiene lista de clientes"""
    results = query_db(
        "SELECT id, nombre, rut, email, telefono, direccion FROM clientes LIMIT 100"
    )
    return [dict(r) for r in results]

@app.get("/clientes/{cliente_id}", response_model=ClienteResponse)
def get_cliente(cliente_id: int, username: str = Depends(verify_credentials)):
    """Obtiene un cliente por ID"""
    result = query_db(
        "SELECT id, nombre, rut, email, telefono, direccion FROM clientes WHERE id = ?",
        (cliente_id,),
        one=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return dict(result)

# ═══════════════════════════════════════════════════════════════════════════════
# INVENTARIO
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/inventario", response_model=List[ProductoResponse])
def get_inventario(username: str = Depends(verify_credentials)):
    """Obtiene lista de productos"""
    results = query_db(
        """SELECT id, sku, descripcion, categoria, sale_price as precio, 
                  stock_current as stock 
           FROM inventory LIMIT 500"""
    )
    return [dict(r) for r in results]

@app.get("/inventario/buscar")
def buscar_inventario(q: str, username: str = Depends(verify_credentials)):
    """Busca productos por SKU o descripción"""
    query = f"%{q}%"
    results = query_db(
        """SELECT id, sku, descripcion, categoria, sale_price, stock_current 
           FROM inventory 
           WHERE sku LIKE ? OR descripcion LIKE ? 
           LIMIT 50""",
        (query, query)
    )
    return [dict(r) for r in results]

# ═══════════════════════════════════════════════════════════════════════════════
# ÓRDENES DE TRABAJO (OT)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/ot")
def get_ot_list(username: str = Depends(verify_credentials)):
    """Obtiene OT activas"""
    results = query_db(
        """SELECT id, numero, cliente_id, estado, fecha_creacion, descripcion 
           FROM trabajo 
           WHERE estado IN ('pendiente', 'en_progreso')
           ORDER BY fecha_creacion DESC LIMIT 50"""
    )
    return [dict(r) for r in results]

@app.get("/ot/{ot_id}")
def get_ot_detail(ot_id: int, username: str = Depends(verify_credentials)):
    """Obtiene detalles de una OT"""
    ot = query_db(
        """SELECT id, numero, cliente_id, estado, fecha_creacion, descripcion 
           FROM trabajo WHERE id = ?""",
        (ot_id,),
        one=True
    )
    if not ot:
        raise HTTPException(status_code=404, detail="OT no encontrada")
    
    ot_dict = dict(ot)
    
    # Agregar cliente
    cliente = query_db(
        "SELECT nombre, rut, email, telefono, direccion FROM clientes WHERE id = ?",
        (ot_dict["cliente_id"],),
        one=True
    )
    if cliente:
        ot_dict["cliente"] = dict(cliente)
    
    # Agregar items
    items = query_db(
        """SELECT id, sku, descripcion, cantidad, item_type 
           FROM project_items WHERE project_id = ?""",
        (ot_id,)
    )
    ot_dict["items"] = [dict(i) for i in items]
    
    return ot_dict

@app.post("/ot/{ot_id}/completar")
def completar_ot(ot_id: int, username: str = Depends(verify_credentials)):
    """Marca una OT como completada"""
    conn = get_db_connection()
    conn.execute(
        "UPDATE trabajo SET estado = ? WHERE id = ?",
        ("completada", ot_id)
    )
    conn.commit()
    conn.close()
    
    return {"success": True, "ot_id": ot_id, "estado": "completada"}

# ═══════════════════════════════════════════════════════════════════════════════
# CHECKLIST
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/checklist/{ot_id}")
def get_checklist(ot_id: int, username: str = Depends(verify_credentials)):
    """Obtiene checklist de una OT"""
    results = query_db(
        """SELECT id, paso, completado, nota, foto_url 
           FROM checklist WHERE ot_id = ?
           ORDER BY orden ASC""",
        (ot_id,)
    )
    return [dict(r) for r in results]

@app.post("/checklist/{item_id}/completar")
def completar_checklist_item(
    item_id: int,
    nota: Optional[str] = None,
    username: str = Depends(verify_credentials)
):
    """Marca un item del checklist como completado"""
    conn = get_db_connection()
    conn.execute(
        "UPDATE checklist SET completado = 1, nota = ? WHERE id = ?",
        (nota, item_id)
    )
    conn.commit()
    conn.close()
    
    return {"success": True, "item_id": item_id, "completado": True}

# ═══════════════════════════════════════════════════════════════════════════════
# ESTADO DEL SERVIDOR
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/status")
def api_status(username: str = Depends(verify_credentials)):
    """Estado general del API y datos"""
    try:
        clientes = query_db("SELECT COUNT(*) as count FROM clientes", one=True)
        productos = query_db("SELECT COUNT(*) as count FROM inventory", one=True)
        ot = query_db("SELECT COUNT(*) as count FROM trabajo", one=True)
        
        return {
            "api": "online",
            "database": "connected",
            "datos": {
                "clientes": clientes["count"] if clientes else 0,
                "productos": productos["count"] if productos else 0,
                "ot": ot["count"] if ot else 0,
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════════════════════
# RAÍZ
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    """Raíz del API - redirige a docs"""
    return {
        "message": "Abaroa Smart ERP API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
