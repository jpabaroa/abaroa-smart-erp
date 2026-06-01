"""
api.py — Abaroa Smart ERP
API REST con FastAPI para aplicaciones móviles (iOS/Android).
Ejecutar: uvicorn api:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
import os
from typing import List, Optional
from database import get_conn, verify_admin_credentials

# CONFIG
app = FastAPI(
    title="Abaroa Smart ERP API",
    description="API REST para aplicaciones móviles (iOS/Android)",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

# SCHEMAS
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str

# JWT FUNCTIONS
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

# ENDPOINTS
@app.get("/", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="online",
        version="2.0.0",
        timestamp=datetime.now().isoformat()
    )

@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    if not verify_admin_credentials(request.username, request.password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": request.username},
        expires_delta=access_token_expires
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"username": request.username, "role": "admin"}
    )

@app.get("/inventory")
async def get_inventory(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    search: Optional[str] = None,
    token: str = None
):
    if token:
        verify_token(token)
    
    conn = get_conn()
    query = "SELECT * FROM inventory WHERE 1=1"
    params = []
    
    if category:
        query += " AND category=?"
        params.append(category)
    if search:
        query += " AND (sku LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    
    query += f" LIMIT ? OFFSET ?"
    params.extend([limit, skip])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/inventory/{sku}")
async def get_inventory_item(sku: str, token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    row = conn.execute("SELECT * FROM inventory WHERE sku=?", (sku,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    return dict(row)

@app.get("/inventory/categories")
async def get_categories(token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT category FROM inventory WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()
    conn.close()
    
    return {"categories": [row[0] for row in rows]}

@app.put("/inventory/{sku}")
async def update_inventory_item(sku: str, updates: dict, token: str = None):
    if token:
        verify_token(token)
    
    allowed_fields = ["is_service", "category", "location", "stock_min", "cost_unit", "margin_pct"]
    
    for field in updates.keys():
        if field not in allowed_fields:
            raise HTTPException(status_code=400, detail=f"Campo no permitido: {field}")
    
    set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
    values = list(updates.values()) + [sku]
    
    conn = get_conn()
    conn.execute(f"UPDATE inventory SET {set_clause} WHERE sku=?", values)
    conn.commit()
    conn.close()
    
    return {"message": f"Producto {sku} actualizado correctamente"}

@app.get("/clients")
async def get_clients(skip: int = 0, limit: int = 100, token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM clients ORDER BY name LIMIT ? OFFSET ?",
        (limit, skip)
    ).fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/quotes")
async def get_quotes(status_filter: Optional[str] = None, skip: int = 0, limit: int = 100, token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    query = "SELECT * FROM quotes WHERE 1=1"
    params = []
    
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    
    query += " ORDER BY quote_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, skip])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/sales")
async def get_sales(skip: int = 0, limit: int = 100, token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sales ORDER BY sale_date DESC LIMIT ? OFFSET ?",
        (limit, skip)
    ).fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/sales/summary")
async def get_sales_summary(token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    summary = conn.execute("""
        SELECT COUNT(*) as total_sales, SUM(total) as total_amount, 
               SUM(gross_margin) as total_margin, AVG(gross_margin_pct) as avg_margin_pct
        FROM sales WHERE sale_date >= date('now', '-30 days')
    """).fetchone()
    conn.close()
    
    return {
        "period": "last_30_days",
        "total_sales": summary[0] or 0,
        "total_amount": summary[1] or 0,
        "total_margin": summary[2] or 0,
        "avg_margin_pct": round(summary[3] or 0, 2)
    }

@app.get("/dashboard/metrics")
async def get_dashboard_metrics(token: str = None):
    if token:
        verify_token(token)
    
    conn = get_conn()
    
    products = conn.execute("SELECT COUNT(*) FROM inventory WHERE is_service=0").fetchone()[0]
    low_stock = conn.execute(
        "SELECT COUNT(*) FROM inventory WHERE stock_current < stock_min AND is_service=0"
    ).fetchone()[0]
    pending_quotes = conn.execute(
        "SELECT COUNT(*) FROM quotes WHERE status='Pendiente'"
    ).fetchone()[0]
    month_sales = conn.execute(
        "SELECT COUNT(*) FROM sales WHERE sale_date >= date('now', 'start of month')"
    ).fetchone()[0]
    
    conn.close()
    
    return {
        "total_products": products,
        "low_stock_items": low_stock,
        "pending_quotes": pending_quotes,
        "sales_this_month": month_sales
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
