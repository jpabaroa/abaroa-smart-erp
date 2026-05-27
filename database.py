"""
database.py — Abaroa Smart ERP
Capa de acceso a datos: SQLite con Row factory, inicialización de esquema,
helpers de negocio y funciones de soporte para todas las vistas.

Módulos cubiertos:
  Inventario · Herramientas · Insumos · Kits · Proveedores
  Clientes · Vendedores · Cotizaciones · Ventas · Facturación
  Proyectos · OT (Órdenes de Trabajo) · Garantías
  Respaldo / Restauración · Administración · Alertas
"""

import sqlite3
import hashlib
import os
from datetime import date, datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent / "erp_abaroa.db"


def get_conn() -> sqlite3.Connection:
    """Devuelve una conexión con Row factory habilitado."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# init_db — esquema completo
# ─────────────────────────────────────────────────────────────────────────────
_SCHEMA = """
-- ══════════════════════════════════════════
--  CONFIGURACIÓN DEL SISTEMA
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS app_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL DEFAULT ''
);

-- ══════════════════════════════════════════
--  PROVEEDORES
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS suppliers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    contact     TEXT    DEFAULT '',
    phone       TEXT    DEFAULT '',
    email       TEXT    DEFAULT '',
    address     TEXT    DEFAULT '',
    notes       TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  CLIENTES
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    rut         TEXT    DEFAULT '',
    phone       TEXT    DEFAULT '',
    email       TEXT    DEFAULT '',
    address     TEXT    DEFAULT '',
    commune     TEXT    DEFAULT '',
    region      TEXT    DEFAULT '',
    notes       TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  VENDEDORES
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS vendors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    DEFAULT '',
    email       TEXT    DEFAULT '',
    commission  REAL    DEFAULT 0.0,
    active      INTEGER DEFAULT 1,
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  INVENTARIO (Productos)
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT    UNIQUE NOT NULL,
    name            TEXT    NOT NULL,
    description     TEXT    DEFAULT '',
    category        TEXT    DEFAULT '',
    brand           TEXT    DEFAULT '',
    model           TEXT    DEFAULT '',
    unit            TEXT    DEFAULT 'un',
    cost_price      REAL    DEFAULT 0.0,
    margin          REAL    DEFAULT 30.0,   -- porcentaje
    sale_price      REAL    DEFAULT 0.0,    -- calculado
    stock           REAL    DEFAULT 0.0,
    stock_min       REAL    DEFAULT 0.0,
    stock_max       REAL    DEFAULT 0.0,
    location        TEXT    DEFAULT '',
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    vat_exempt      INTEGER DEFAULT 0,      -- 1 = exento IVA
    active          INTEGER DEFAULT 1,
    image_url       TEXT    DEFAULT '',
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  MOVIMIENTOS DE STOCK
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stock_movements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    movement_type   TEXT    NOT NULL,   -- 'entrada','salida','ajuste','uso_ot','uso_proyecto'
    quantity        REAL    NOT NULL,
    reference_type  TEXT    DEFAULT '', -- 'compra','venta','ot','proyecto','ajuste_manual'
    reference_id    INTEGER DEFAULT NULL,
    cost_unit       REAL    DEFAULT 0.0,
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  HERRAMIENTAS
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tools (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    serial          TEXT    DEFAULT '',
    brand           TEXT    DEFAULT '',
    model           TEXT    DEFAULT '',
    category        TEXT    DEFAULT '',
    condition       TEXT    DEFAULT 'bueno',  -- bueno, regular, malo, baja
    location        TEXT    DEFAULT '',
    purchase_date   TEXT    DEFAULT '',
    purchase_price  REAL    DEFAULT 0.0,
    assigned_to     TEXT    DEFAULT '',
    notes           TEXT    DEFAULT '',
    active          INTEGER DEFAULT 1,
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  INSUMOS (materiales menores / consumibles)
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS supplies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    sku             TEXT    DEFAULT '',
    category        TEXT    DEFAULT '',
    unit            TEXT    DEFAULT 'un',
    cost_price      REAL    DEFAULT 0.0,
    sale_price      REAL    DEFAULT 0.0,
    stock           REAL    DEFAULT 0.0,
    stock_min       REAL    DEFAULT 0.0,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    notes           TEXT    DEFAULT '',
    active          INTEGER DEFAULT 1,
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  KITS (bundles de productos)
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS kits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    description     TEXT    DEFAULT '',
    category        TEXT    DEFAULT '',
    sale_price      REAL    DEFAULT 0.0,  -- precio fijo manual (0 = calculado)
    margin          REAL    DEFAULT 30.0,
    active          INTEGER DEFAULT 1,
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS kit_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_id      INTEGER NOT NULL REFERENCES kits(id) ON DELETE CASCADE,
    product_id  INTEGER REFERENCES products(id) ON DELETE SET NULL,
    supply_id   INTEGER REFERENCES supplies(id) ON DELETE SET NULL,
    description TEXT    DEFAULT '',
    quantity    REAL    NOT NULL DEFAULT 1,
    unit_price  REAL    DEFAULT 0.0,
    line_total  REAL    DEFAULT 0.0
);

-- ══════════════════════════════════════════
--  COTIZACIONES
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS quotes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number    TEXT    UNIQUE NOT NULL,
    client_id       INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    vendor_id       INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    quote_date      TEXT    DEFAULT (date('now','localtime')),
    valid_until     TEXT    DEFAULT '',
    status          TEXT    DEFAULT 'borrador',  -- borrador, enviada, aprobada, rechazada, vencida
    subtotal        REAL    DEFAULT 0.0,
    vat_amount      REAL    DEFAULT 0.0,
    total           REAL    DEFAULT 0.0,
    notes           TEXT    DEFAULT '',
    terms           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS quote_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id        INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    item_type       TEXT    NOT NULL DEFAULT 'producto',  -- producto, kit, servicio, insumo
    product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
    kit_id          INTEGER REFERENCES kits(id) ON DELETE SET NULL,
    supply_id       INTEGER REFERENCES supplies(id) ON DELETE SET NULL,
    description     TEXT    NOT NULL DEFAULT '',
    quantity        REAL    DEFAULT 1,
    unit_price      REAL    DEFAULT 0.0,
    discount        REAL    DEFAULT 0.0,  -- porcentaje
    line_total      REAL    DEFAULT 0.0,
    vat_exempt      INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0
);

-- ══════════════════════════════════════════
--  VENTAS
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_number     TEXT    UNIQUE NOT NULL,
    quote_id        INTEGER REFERENCES quotes(id) ON DELETE SET NULL,
    client_id       INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    vendor_id       INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    sale_date       TEXT    DEFAULT (date('now','localtime')),
    payment_method  TEXT    DEFAULT 'efectivo',  -- efectivo, transferencia, cheque, tarjeta, mixto
    payment_status  TEXT    DEFAULT 'pendiente', -- pendiente, parcial, pagado
    subtotal        REAL    DEFAULT 0.0,
    vat_amount      REAL    DEFAULT 0.0,
    total           REAL    DEFAULT 0.0,
    amount_paid     REAL    DEFAULT 0.0,
    balance_due     REAL    DEFAULT 0.0,
    material_cost   REAL    DEFAULT 0.0,
    gross_margin    REAL    DEFAULT 0.0,
    gross_margin_pct REAL   DEFAULT 0.0,
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sale_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id     INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    item_type   TEXT    DEFAULT 'producto',
    description TEXT    NOT NULL,
    quantity    REAL    DEFAULT 1,
    unit_price  REAL    DEFAULT 0.0,
    line_total  REAL    DEFAULT 0.0,
    vat_exempt  INTEGER DEFAULT 0
);

-- ══════════════════════════════════════════
--  FACTURACIÓN
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number  TEXT    UNIQUE NOT NULL,
    sale_id         INTEGER REFERENCES sales(id) ON DELETE SET NULL,
    client_id       INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    invoice_date    TEXT    DEFAULT (date('now','localtime')),
    due_date        TEXT    DEFAULT '',
    type            TEXT    DEFAULT 'boleta',  -- boleta, factura, nota_credito
    status          TEXT    DEFAULT 'emitida', -- emitida, anulada, pagada
    subtotal        REAL    DEFAULT 0.0,
    vat_amount      REAL    DEFAULT 0.0,
    total           REAL    DEFAULT 0.0,
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  PROYECTOS
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number      TEXT    UNIQUE NOT NULL,
    name                TEXT    NOT NULL,
    client_id           INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    vendor_id           INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    quotation_id        INTEGER REFERENCES quotes(id) ON DELETE SET NULL,
    status              TEXT    DEFAULT 'planificado',
    -- planificado, en_progreso, pausado, completado, cancelado
    priority            TEXT    DEFAULT 'normal',  -- baja, normal, alta, urgente
    start_date          TEXT    DEFAULT '',
    installation_date   TEXT    DEFAULT '',
    delivery_date       TEXT    DEFAULT '',
    end_date            TEXT    DEFAULT '',
    address             TEXT    DEFAULT '',
    description         TEXT    DEFAULT '',
    technician          TEXT    DEFAULT '',
    progress_pct        INTEGER DEFAULT 0,
    notes               TEXT    DEFAULT '',
    created_at          TEXT    DEFAULT (datetime('now','localtime')),
    updated_at          TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS project_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    item_type       TEXT    DEFAULT 'producto',  -- producto, kit_component, insumo, servicio
    product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
    supply_id       INTEGER REFERENCES supplies(id) ON DELETE SET NULL,
    sku             TEXT    DEFAULT '',
    description     TEXT    NOT NULL DEFAULT '',
    quantity        REAL    DEFAULT 1,
    used_quantity   REAL    DEFAULT 0,
    unit_price      REAL    DEFAULT 0.0,
    line_total      REAL    DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS project_checklists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL DEFAULT 'Checklist',
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS project_checklist_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_checklist_id    INTEGER NOT NULL REFERENCES project_checklists(id) ON DELETE CASCADE,
    item_text               TEXT    NOT NULL,
    is_checked              INTEGER DEFAULT 0,
    evidence_note           TEXT    DEFAULT '',
    sort_order              INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS project_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    log_type    TEXT    DEFAULT 'nota',  -- nota, estado, foto, documento
    content     TEXT    NOT NULL,
    author      TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  ÓRDENES DE TRABAJO (OT)
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS work_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ot_number       TEXT    UNIQUE NOT NULL,
    client_id       INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    vendor_id       INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    type            TEXT    DEFAULT 'instalación',
    -- instalación, mantención, garantía, diagnóstico, retiro
    status          TEXT    DEFAULT 'abierta',
    -- abierta, en_progreso, pausada, cerrada, cancelada
    priority        TEXT    DEFAULT 'normal',
    scheduled_date  TEXT    DEFAULT '',
    start_date      TEXT    DEFAULT '',
    end_date        TEXT    DEFAULT '',
    description     TEXT    DEFAULT '',
    technician      TEXT    DEFAULT '',
    address         TEXT    DEFAULT '',
    diagnosis       TEXT    DEFAULT '',
    solution        TEXT    DEFAULT '',
    travel_km       REAL    DEFAULT 0,
    labor_hours     REAL    DEFAULT 0,
    labor_rate      REAL    DEFAULT 0,
    parts_cost      REAL    DEFAULT 0,
    total_cost      REAL    DEFAULT 0,
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ot_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ot_id       INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    item_type   TEXT    DEFAULT 'producto',
    product_id  INTEGER REFERENCES products(id) ON DELETE SET NULL,
    supply_id   INTEGER REFERENCES supplies(id) ON DELETE SET NULL,
    description TEXT    NOT NULL DEFAULT '',
    quantity    REAL    DEFAULT 1,
    unit_price  REAL    DEFAULT 0.0,
    line_total  REAL    DEFAULT 0.0
);

-- ══════════════════════════════════════════
--  GARANTÍAS
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS warranties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    warranty_number TEXT    UNIQUE NOT NULL,
    client_id       INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    ot_id           INTEGER REFERENCES work_orders(id) ON DELETE SET NULL,
    product_name    TEXT    DEFAULT '',
    serial_number   TEXT    DEFAULT '',
    issue_date      TEXT    DEFAULT (date('now','localtime')),
    expiry_date     TEXT    DEFAULT '',
    status          TEXT    DEFAULT 'vigente',  -- vigente, vencida, usada, anulada
    description     TEXT    DEFAULT '',
    resolution      TEXT    DEFAULT '',
    technician      TEXT    DEFAULT '',
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

-- ══════════════════════════════════════════
--  COMPRAS / RECEPCIONES
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS purchases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_number TEXT    UNIQUE NOT NULL,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    purchase_date   TEXT    DEFAULT (date('now','localtime')),
    invoice_ref     TEXT    DEFAULT '',
    status          TEXT    DEFAULT 'recibida',  -- pendiente, recibida, parcial
    total           REAL    DEFAULT 0.0,
    notes           TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id  INTEGER REFERENCES products(id) ON DELETE SET NULL,
    supply_id   INTEGER REFERENCES supplies(id) ON DELETE SET NULL,
    description TEXT    NOT NULL DEFAULT '',
    quantity    REAL    DEFAULT 1,
    unit_cost   REAL    DEFAULT 0.0,
    line_total  REAL    DEFAULT 0.0,
    received    REAL    DEFAULT 0.0
);

-- ══════════════════════════════════════════
--  RESPALDO / AUDITORÍA
-- ══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,
    table_name  TEXT    DEFAULT '',
    record_id   INTEGER DEFAULT NULL,
    user        TEXT    DEFAULT 'system',
    detail      TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);
"""


def init_db():
    """Crea todas las tablas si no existen. Idempotente."""
    conn = get_conn()
    conn.executescript(_SCHEMA)
    # Migración segura: agrega columnas faltantes en tablas existentes
    _safe_add_columns(conn, "sales", [
        ("material_cost",    "REAL DEFAULT 0.0"),
        ("gross_margin",     "REAL DEFAULT 0.0"),
        ("gross_margin_pct", "REAL DEFAULT 0.0"),
    ])
    conn.commit()
    conn.close()


def _safe_add_columns(conn, table: str, columns: list[tuple]):
    """Agrega columnas a una tabla si no existen (ALTER TABLE seguro)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for col_name, col_def in columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


# ─────────────────────────────────────────────────────────────────────────────
# Configuración / Settings
# ─────────────────────────────────────────────────────────────────────────────

def _hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


_DEFAULT_SETTINGS = {
    "company_name":     "Abaroa Smart",
    "company_rut":      "",
    "company_phone":    "+56 9 8183 8679",
    "company_email":    "contacto@abaroasmart.com",
    "company_address":  "Osorno, Región de Los Lagos",
    "company_web":      "www.abaroasmart.com",
    "admin_username":   "admin",
    "admin_password":   _hash_password("admin123"),
    "vat_rate":         "19",
    "default_margin":   "30",
    "quote_prefix":     "COT",
    "sale_prefix":      "VTA",
    "ot_prefix":        "OT",
    "project_prefix":   "PRY",
    "warranty_months":  "6",
    "currency":         "CLP",
    "low_stock_alert":  "1",
}


def ensure_app_settings():
    """Inserta valores por defecto solo si la clave no existe."""
    conn = get_conn()
    defaults = dict(_DEFAULT_SETTINGS)
    defaults["admin_password"] = _hash_password("admin123")
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    """Lee un valor de app_settings."""
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """Guarda o actualiza un valor en app_settings."""
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    """Devuelve todos los settings como dict."""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Autenticación admin
# ─────────────────────────────────────────────────────────────────────────────

def verify_admin_credentials(username: str, password: str) -> bool:
    """Verifica usuario y contraseña del administrador."""
    stored_user = get_setting("admin_username", "admin")
    stored_hash = get_setting("admin_password", _hash_password("admin123"))
    return (username.strip() == stored_user.strip() and
            _hash_password(password) == stored_hash)


def admin_logged_in() -> bool:
    """Comprueba el estado de sesión admin en Streamlit session_state."""
    try:
        import streamlit as st
        return bool(st.session_state.get("admin_logged_in", False))
    except Exception:
        return False


def change_admin_password(new_password: str):
    set_setting("admin_password", _hash_password(new_password))


# ─────────────────────────────────────────────────────────────────────────────
# Recálculo de precios de venta
# ─────────────────────────────────────────────────────────────────────────────

def recalc_all_sale_prices():
    """
    Recalcula sale_price de products donde sale_price == 0 o está desactualizado
    usando cost_price * (1 + margin/100).
    Solo actualiza si el precio calculado difiere del almacenado.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, cost_price, margin, sale_price FROM products WHERE active=1"
    ).fetchall()
    for row in rows:
        if row["cost_price"] and row["margin"]:
            calc = round(row["cost_price"] * (1 + row["margin"] / 100), 0)
            if abs(calc - (row["sale_price"] or 0)) > 0.5:
                conn.execute(
                    "UPDATE products SET sale_price=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (calc, row["id"]),
                )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Recálculo de stock desde movimientos
# ─────────────────────────────────────────────────────────────────────────────

def recalc_stock():
    """
    Recalcula el stock de productos a partir de stock_movements.
    Usa SUM(cantidad) con signo: entradas positivas, salidas negativas.
    Solo recalcula si hay movimientos registrados para ese producto;
    si no hay movimientos, mantiene el valor manual.
    """
    conn = get_conn()
    movements = conn.execute("""
        SELECT product_id,
               SUM(CASE WHEN movement_type IN ('entrada') THEN quantity
                        WHEN movement_type IN ('salida','uso_ot','uso_proyecto') THEN -quantity
                        ELSE quantity END) AS net_stock
        FROM stock_movements
        GROUP BY product_id
    """).fetchall()
    for row in movements:
        conn.execute(
            "UPDATE products SET stock=? WHERE id=?",
            (max(0, row["net_stock"] or 0), row["product_id"]),
        )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Eliminar filas duplicadas
# ─────────────────────────────────────────────────────────────────────────────

def remove_duplicate_rows():
    """
    Elimina duplicados en tablas críticas manteniendo el registro con menor id.
    Ejecuta solo las tablas que pueden tener colisiones por UNIQUE constraints.
    """
    conn = get_conn()
    # Productos duplicados por SKU
    conn.execute("""
        DELETE FROM products
        WHERE id NOT IN (
            SELECT MIN(id) FROM products GROUP BY sku
        )
    """)
    # Cotizaciones duplicadas por quote_number
    conn.execute("""
        DELETE FROM quotes
        WHERE id NOT IN (
            SELECT MIN(id) FROM quotes GROUP BY quote_number
        )
    """)
    # Ventas duplicadas por sale_number
    conn.execute("""
        DELETE FROM sales
        WHERE id NOT IN (
            SELECT MIN(id) FROM sales GROUP BY sale_number
        )
    """)
    # OT duplicadas por ot_number
    conn.execute("""
        DELETE FROM work_orders
        WHERE id NOT IN (
            SELECT MIN(id) FROM work_orders GROUP BY ot_number
        )
    """)
    # Proyectos duplicados por project_number
    conn.execute("""
        DELETE FROM projects
        WHERE id NOT IN (
            SELECT MIN(id) FROM projects GROUP BY project_number
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Alertas del sistema
# ─────────────────────────────────────────────────────────────────────────────

def get_alerts_data() -> list[dict]:
    """
    Devuelve lista de alertas activas del sistema.
    Cada alerta es un dict con keys: level, title, detail.
    Niveles: 'warning' (naranja) | 'info' (azul)
    """
    alerts = []
    conn = get_conn()

    # 1. Stock bajo (products)
    low_stock = conn.execute("""
        SELECT name, sku, stock, stock_min
        FROM products
        WHERE active=1 AND stock_min > 0 AND stock <= stock_min
        ORDER BY (stock_min - stock) DESC
        LIMIT 10
    """).fetchall()
    for p in low_stock:
        alerts.append({
            "level": "warning",
            "title": f"Stock bajo: {p['name']}",
            "detail": f"SKU {p['sku']} · Stock actual: {p['stock']} · Mínimo: {p['stock_min']}",
        })

    # 2. Stock bajo (insumos)
    low_supplies = conn.execute("""
        SELECT name, stock, stock_min
        FROM supplies
        WHERE active=1 AND stock_min > 0 AND stock <= stock_min
        LIMIT 5
    """).fetchall()
    for s in low_supplies:
        alerts.append({
            "level": "warning",
            "title": f"Insumo bajo: {s['name']}",
            "detail": f"Stock actual: {s['stock']} · Mínimo: {s['stock_min']}",
        })

    # 3. Cotizaciones vencidas (enviadas con valid_until < hoy)
    today = date.today().isoformat()
    expired_quotes = conn.execute("""
        SELECT q.quote_number, c.name AS client_name, q.valid_until
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id
        WHERE q.status='enviada' AND q.valid_until != '' AND q.valid_until < ?
        ORDER BY q.valid_until ASC
        LIMIT 5
    """, (today,)).fetchall()
    for q in expired_quotes:
        alerts.append({
            "level": "warning",
            "title": f"Cotización vencida: {q['quote_number']}",
            "detail": f"Cliente: {q['client_name'] or '-'} · Venció: {q['valid_until']}",
        })

    # 4. OT vencidas (abiertas con scheduled_date < hoy)
    overdue_ot = conn.execute("""
        SELECT ot_number, scheduled_date
        FROM work_orders
        WHERE status IN ('abierta','en_progreso')
          AND scheduled_date != '' AND scheduled_date < ?
        ORDER BY scheduled_date ASC
        LIMIT 5
    """, (today,)).fetchall()
    for ot in overdue_ot:
        alerts.append({
            "level": "info",
            "title": f"OT vencida: {ot['ot_number']}",
            "detail": f"Programada para: {ot['scheduled_date']}",
        })

    # 5. Garantías por vencer (próximos 30 días)
    warranty_soon = conn.execute("""
        SELECT warranty_number, product_name, expiry_date
        FROM warranties
        WHERE status='vigente' AND expiry_date != ''
          AND expiry_date BETWEEN ? AND date(?, '+30 days')
        ORDER BY expiry_date ASC
        LIMIT 5
    """, (today, today)).fetchall()
    for w in warranty_soon:
        alerts.append({
            "level": "info",
            "title": f"Garantía por vencer: {w['warranty_number']}",
            "detail": f"{w['product_name']} · Vence: {w['expiry_date']}",
        })

    conn.close()
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de correlativo / numeración automática
# ─────────────────────────────────────────────────────────────────────────────

def _next_number(prefix_key: str, table: str, col: str) -> str:
    """Genera el próximo número correlativo del tipo PREFIX-NNNN."""
    prefix = get_setting(prefix_key, prefix_key.upper()[:3])
    conn = get_conn()
    row = conn.execute(
        f"SELECT {col} FROM {table} ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row and row[0]:
        # Extraer la parte numérica del último registro
        parts = str(row[0]).split("-")
        try:
            num = int(parts[-1]) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f"{prefix}-{num:04d}"


def next_quote_number() -> str:
    return _next_number("quote_prefix", "quotes", "quote_number")


def next_sale_number() -> str:
    return _next_number("sale_prefix", "sales", "sale_number")


def next_ot_number() -> str:
    return _next_number("ot_prefix", "work_orders", "ot_number")


def next_project_number() -> str:
    return _next_number("project_prefix", "projects", "project_number")


def next_purchase_number() -> str:
    return _next_number("purchase_prefix", "purchases", "purchase_number")


def next_warranty_number() -> str:
    return _next_number("warranty_prefix", "warranties", "warranty_number")


def next_invoice_number() -> str:
    return _next_number("invoice_prefix", "invoices", "invoice_number")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Clientes
# ─────────────────────────────────────────────────────────────────────────────

def get_clients(search: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    rows = conn.execute(
        "SELECT * FROM clients WHERE name LIKE ? OR rut LIKE ? OR phone LIKE ? OR email LIKE ? ORDER BY name",
        (q, q, q, q),
    ).fetchall()
    conn.close()
    return rows


def get_client(client_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    conn.close()
    return row


def upsert_client(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE clients SET name=?,rut=?,phone=?,email=?,address=?,commune=?,region=?,notes=?
            WHERE id=?
        """, (data["name"], data.get("rut",""), data.get("phone",""), data.get("email",""),
              data.get("address",""), data.get("commune",""), data.get("region",""),
              data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""
            INSERT INTO clients (name,rut,phone,email,address,commune,region,notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (data["name"], data.get("rut",""), data.get("phone",""), data.get("email",""),
              data.get("address",""), data.get("commune",""), data.get("region",""),
              data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def delete_client(client_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Vendedores
# ─────────────────────────────────────────────────────────────────────────────

def get_vendors(active_only: bool = True) -> list:
    conn = get_conn()
    q = "SELECT * FROM vendors"
    q += " WHERE active=1" if active_only else ""
    q += " ORDER BY name"
    rows = conn.execute(q).fetchall()
    conn.close()
    return rows


def get_vendor(vendor_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM vendors WHERE id=?", (vendor_id,)).fetchone()
    conn.close()
    return row


def upsert_vendor(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE vendors SET name=?,phone=?,email=?,commission=?,active=? WHERE id=?
        """, (data["name"], data.get("phone",""), data.get("email",""),
              data.get("commission", 0), int(data.get("active", 1)), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""
            INSERT INTO vendors (name,phone,email,commission,active)
            VALUES (?,?,?,?,?)
        """, (data["name"], data.get("phone",""), data.get("email",""),
              data.get("commission", 0), int(data.get("active", 1))))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Proveedores
# ─────────────────────────────────────────────────────────────────────────────

def get_suppliers(search: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    rows = conn.execute(
        "SELECT * FROM suppliers WHERE name LIKE ? OR email LIKE ? ORDER BY name",
        (q, q),
    ).fetchall()
    conn.close()
    return rows


def get_supplier(supplier_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    conn.close()
    return row


def upsert_supplier(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE suppliers SET name=?,contact=?,phone=?,email=?,address=?,notes=? WHERE id=?
        """, (data["name"], data.get("contact",""), data.get("phone",""),
              data.get("email",""), data.get("address",""), data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""
            INSERT INTO suppliers (name,contact,phone,email,address,notes)
            VALUES (?,?,?,?,?,?)
        """, (data["name"], data.get("contact",""), data.get("phone",""),
              data.get("email",""), data.get("address",""), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def delete_supplier(supplier_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Productos (Inventario)
# ─────────────────────────────────────────────────────────────────────────────

def get_products(search: str = "", active_only: bool = True, category: str = "") -> list:
    conn = get_conn()
    q_like = "%" + search + "%"
    where = "WHERE (p.name LIKE ? OR p.sku LIKE ? OR p.brand LIKE ? OR p.description LIKE ?)"
    params: list = [q_like, q_like, q_like, q_like]
    if active_only:
        where += " AND p.active=1"
    if category:
        where += " AND p.category=?"
        params.append(category)
    rows = conn.execute(f"""
        SELECT p.*, s.name AS supplier_name
        FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id
        {where}
        ORDER BY p.name
    """, params).fetchall()
    conn.close()
    return rows


def get_product(product_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT p.*, s.name AS supplier_name FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?",
        (product_id,),
    ).fetchone()
    conn.close()
    return row


def get_product_by_sku(sku: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE sku=?", (sku,)).fetchone()
    conn.close()
    return row


def upsert_product(data: dict) -> int:
    cost = float(data.get("cost_price", 0))
    margin = float(data.get("margin", 30))
    sale = round(cost * (1 + margin / 100), 0)
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE products SET sku=?,name=?,description=?,category=?,brand=?,model=?,unit=?,
            cost_price=?,margin=?,sale_price=?,stock=?,stock_min=?,stock_max=?,location=?,
            supplier_id=?,vat_exempt=?,active=?,notes=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (data["sku"], data["name"], data.get("description",""), data.get("category",""),
              data.get("brand",""), data.get("model",""), data.get("unit","un"),
              cost, margin, sale, data.get("stock",0), data.get("stock_min",0),
              data.get("stock_max",0), data.get("location",""), data.get("supplier_id"),
              int(data.get("vat_exempt",0)), int(data.get("active",1)), data.get("notes",""),
              data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""
            INSERT INTO products (sku,name,description,category,brand,model,unit,
            cost_price,margin,sale_price,stock,stock_min,stock_max,location,
            supplier_id,vat_exempt,active,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (data["sku"], data["name"], data.get("description",""), data.get("category",""),
              data.get("brand",""), data.get("model",""), data.get("unit","un"),
              cost, margin, sale, data.get("stock",0), data.get("stock_min",0),
              data.get("stock_max",0), data.get("location",""), data.get("supplier_id"),
              int(data.get("vat_exempt",0)), int(data.get("active",1)), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def delete_product(product_id: int):
    conn = get_conn()
    conn.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))
    conn.commit()
    conn.close()


def adjust_stock(product_id: int, quantity: float, movement_type: str = "ajuste",
                 ref_type: str = "", ref_id: int | None = None, notes: str = ""):
    """Registra un movimiento de stock y actualiza el campo stock del producto."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO stock_movements (product_id, movement_type, quantity, reference_type, reference_id, notes)
        VALUES (?,?,?,?,?,?)
    """, (product_id, movement_type, abs(quantity), ref_type, ref_id, notes))
    # Actualizar stock directamente
    sign = -1 if movement_type in ("salida", "uso_ot", "uso_proyecto") else 1
    conn.execute(
        "UPDATE products SET stock = MAX(0, stock + ?) WHERE id=?",
        (sign * abs(quantity), product_id),
    )
    conn.commit()
    conn.close()


def get_product_categories() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT category FROM products WHERE category!='' AND active=1 ORDER BY category"
    ).fetchall()
    conn.close()
    return [r["category"] for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Herramientas
# ─────────────────────────────────────────────────────────────────────────────

def get_tools(search: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    rows = conn.execute(
        "SELECT * FROM tools WHERE (name LIKE ? OR serial LIKE ? OR brand LIKE ?) AND active=1 ORDER BY name",
        (q, q, q),
    ).fetchall()
    conn.close()
    return rows


def upsert_tool(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE tools SET name=?,serial=?,brand=?,model=?,category=?,condition=?,
            location=?,purchase_date=?,purchase_price=?,assigned_to=?,notes=?,active=?
            WHERE id=?
        """, (data["name"], data.get("serial",""), data.get("brand",""), data.get("model",""),
              data.get("category",""), data.get("condition","bueno"), data.get("location",""),
              data.get("purchase_date",""), data.get("purchase_price",0),
              data.get("assigned_to",""), data.get("notes",""), int(data.get("active",1)),
              data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""
            INSERT INTO tools (name,serial,brand,model,category,condition,location,
            purchase_date,purchase_price,assigned_to,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (data["name"], data.get("serial",""), data.get("brand",""), data.get("model",""),
              data.get("category",""), data.get("condition","bueno"), data.get("location",""),
              data.get("purchase_date",""), data.get("purchase_price",0),
              data.get("assigned_to",""), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def delete_tool(tool_id: int):
    conn = get_conn()
    conn.execute("UPDATE tools SET active=0 WHERE id=?", (tool_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Insumos
# ─────────────────────────────────────────────────────────────────────────────

def get_supplies(search: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    rows = conn.execute("""
        SELECT s.*, sup.name AS supplier_name
        FROM supplies s LEFT JOIN suppliers sup ON sup.id=s.supplier_id
        WHERE (s.name LIKE ? OR s.sku LIKE ?) AND s.active=1
        ORDER BY s.name
    """, (q, q)).fetchall()
    conn.close()
    return rows


def upsert_supply(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE supplies SET name=?,sku=?,category=?,unit=?,cost_price=?,sale_price=?,
            stock=?,stock_min=?,supplier_id=?,notes=?,active=? WHERE id=?
        """, (data["name"], data.get("sku",""), data.get("category",""), data.get("unit","un"),
              data.get("cost_price",0), data.get("sale_price",0), data.get("stock",0),
              data.get("stock_min",0), data.get("supplier_id"), data.get("notes",""),
              int(data.get("active",1)), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""
            INSERT INTO supplies (name,sku,category,unit,cost_price,sale_price,stock,stock_min,supplier_id,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (data["name"], data.get("sku",""), data.get("category",""), data.get("unit","un"),
              data.get("cost_price",0), data.get("sale_price",0), data.get("stock",0),
              data.get("stock_min",0), data.get("supplier_id"), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def delete_supply(supply_id: int):
    conn = get_conn()
    conn.execute("UPDATE supplies SET active=0 WHERE id=?", (supply_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Kits
# ─────────────────────────────────────────────────────────────────────────────

def get_kits(search: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    rows = conn.execute(
        "SELECT * FROM kits WHERE (name LIKE ? OR description LIKE ?) AND active=1 ORDER BY name",
        (q, q),
    ).fetchall()
    conn.close()
    return rows


def get_kit(kit_id: int):
    conn = get_conn()
    kit = conn.execute("SELECT * FROM kits WHERE id=?", (kit_id,)).fetchone()
    items = conn.execute("""
        SELECT ki.*, p.name AS product_name, p.sku AS product_sku,
               s.name AS supply_name
        FROM kit_items ki
        LEFT JOIN products p ON p.id=ki.product_id
        LEFT JOIN supplies s ON s.id=ki.supply_id
        WHERE ki.kit_id=?
        ORDER BY ki.id
    """, (kit_id,)).fetchall()
    conn.close()
    return kit, items


def upsert_kit(data: dict, items: list[dict]) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE kits SET name=?,description=?,category=?,sale_price=?,margin=?,active=?,notes=?
            WHERE id=?
        """, (data["name"], data.get("description",""), data.get("category",""),
              data.get("sale_price",0), data.get("margin",30),
              int(data.get("active",1)), data.get("notes",""), data["id"]))
        kit_id = data["id"]
        conn.execute("DELETE FROM kit_items WHERE kit_id=?", (kit_id,))
    else:
        cur = conn.execute("""
            INSERT INTO kits (name,description,category,sale_price,margin,active,notes)
            VALUES (?,?,?,?,?,?,?)
        """, (data["name"], data.get("description",""), data.get("category",""),
              data.get("sale_price",0), data.get("margin",30),
              int(data.get("active",1)), data.get("notes","")))
        kit_id = cur.lastrowid

    for item in items:
        lt = float(item.get("quantity",1)) * float(item.get("unit_price",0))
        conn.execute("""
            INSERT INTO kit_items (kit_id,product_id,supply_id,description,quantity,unit_price,line_total)
            VALUES (?,?,?,?,?,?,?)
        """, (kit_id, item.get("product_id"), item.get("supply_id"),
              item.get("description",""), item.get("quantity",1),
              item.get("unit_price",0), lt))
    conn.commit()
    conn.close()
    return kit_id


def delete_kit(kit_id: int):
    conn = get_conn()
    conn.execute("UPDATE kits SET active=0 WHERE id=?", (kit_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Cotizaciones
# ─────────────────────────────────────────────────────────────────────────────

def get_quotes(search: str = "", status: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    where = "WHERE (qu.quote_number LIKE ? OR c.name LIKE ?)"
    params: list = [q, q]
    if status:
        where += " AND qu.status=?"
        params.append(status)
    rows = conn.execute(f"""
        SELECT qu.*, c.name AS client_name, v.name AS vendor_name
        FROM quotes qu
        LEFT JOIN clients c ON c.id=qu.client_id
        LEFT JOIN vendors v ON v.id=qu.vendor_id
        {where}
        ORDER BY qu.id DESC
    """, params).fetchall()
    conn.close()
    return rows


def get_quote(quote_id: int):
    conn = get_conn()
    quote = conn.execute("""
        SELECT qu.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address, c.rut AS client_rut,
               v.name AS vendor_name
        FROM quotes qu
        LEFT JOIN clients c ON c.id=qu.client_id
        LEFT JOIN vendors v ON v.id=qu.vendor_id
        WHERE qu.id=?
    """, (quote_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM quote_items WHERE quote_id=? ORDER BY sort_order, id",
        (quote_id,),
    ).fetchall()
    conn.close()
    return quote, items


def upsert_quote(data: dict, items: list[dict]) -> int:
    """Crea o actualiza una cotización con sus líneas."""
    vat_rate = float(get_setting("vat_rate", "19")) / 100
    conn = get_conn()

    subtotal = sum(float(i.get("line_total", 0)) for i in items)
    vat = sum(
        float(i.get("line_total", 0)) * vat_rate
        for i in items if not i.get("vat_exempt", 0)
    )
    total = subtotal + vat

    if data.get("id"):
        conn.execute("""
            UPDATE quotes SET client_id=?,vendor_id=?,quote_date=?,valid_until=?,status=?,
            subtotal=?,vat_amount=?,total=?,notes=?,terms=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (data.get("client_id"), data.get("vendor_id"), data.get("quote_date", str(date.today())),
              data.get("valid_until",""), data.get("status","borrador"),
              subtotal, vat, total, data.get("notes",""), data.get("terms",""), data["id"]))
        qid = data["id"]
        conn.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
    else:
        quote_number = data.get("quote_number") or next_quote_number()
        cur = conn.execute("""
            INSERT INTO quotes (quote_number,client_id,vendor_id,quote_date,valid_until,status,
            subtotal,vat_amount,total,notes,terms)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (quote_number, data.get("client_id"), data.get("vendor_id"),
              data.get("quote_date", str(date.today())), data.get("valid_until",""),
              data.get("status","borrador"), subtotal, vat, total,
              data.get("notes",""), data.get("terms","")))
        qid = cur.lastrowid

    for idx, item in enumerate(items):
        lt = float(item.get("quantity",1)) * float(item.get("unit_price",0))
        lt *= (1 - float(item.get("discount",0)) / 100)
        conn.execute("""
            INSERT INTO quote_items (quote_id,item_type,product_id,kit_id,supply_id,description,
            quantity,unit_price,discount,line_total,vat_exempt,sort_order)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (qid, item.get("item_type","producto"), item.get("product_id"),
              item.get("kit_id"), item.get("supply_id"), item.get("description",""),
              item.get("quantity",1), item.get("unit_price",0), item.get("discount",0),
              lt, int(item.get("vat_exempt",0)), idx))
    conn.commit()
    conn.close()
    return qid


def update_quote_status(quote_id: int, status: str):
    conn = get_conn()
    conn.execute(
        "UPDATE quotes SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
        (status, quote_id),
    )
    conn.commit()
    conn.close()


def delete_quote(quote_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM quotes WHERE id=?", (quote_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Ventas
# ─────────────────────────────────────────────────────────────────────────────

def get_sales(search: str = "", status: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    where = "WHERE (s.sale_number LIKE ? OR c.name LIKE ?)"
    params: list = [q, q]
    if status:
        where += " AND s.payment_status=?"
        params.append(status)
    rows = conn.execute(f"""
        SELECT s.*, c.name AS client_name, v.name AS vendor_name
        FROM sales s
        LEFT JOIN clients c ON c.id=s.client_id
        LEFT JOIN vendors v ON v.id=s.vendor_id
        {where}
        ORDER BY s.id DESC
    """, params).fetchall()
    conn.close()
    return rows


def get_sale(sale_id: int):
    conn = get_conn()
    sale = conn.execute("""
        SELECT s.*, c.name AS client_name, v.name AS vendor_name
        FROM sales s
        LEFT JOIN clients c ON c.id=s.client_id
        LEFT JOIN vendors v ON v.id=s.vendor_id
        WHERE s.id=?
    """, (sale_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,)
    ).fetchall()
    conn.close()
    return sale, items


def create_sale_from_quote(quote_id: int, payment_method: str = "transferencia") -> int:
    """Convierte una cotización aprobada en venta."""
    quote, q_items = get_quote(quote_id)
    if not quote:
        raise ValueError(f"Cotización {quote_id} no encontrada")

    sale_number = next_sale_number()
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO sales (sale_number,quote_id,client_id,vendor_id,sale_date,payment_method,
        payment_status,subtotal,vat_amount,total,amount_paid,balance_due)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (sale_number, quote_id, quote["client_id"], quote["vendor_id"],
          str(date.today()), payment_method, "pendiente",
          quote["subtotal"], quote["vat_amount"], quote["total"], 0, quote["total"]))
    sale_id = cur.lastrowid

    for item in q_items:
        conn.execute("""
            INSERT INTO sale_items (sale_id,item_type,description,quantity,unit_price,line_total,vat_exempt)
            VALUES (?,?,?,?,?,?,?)
        """, (sale_id, item["item_type"], item["description"],
              item["quantity"], item["unit_price"], item["line_total"], item["vat_exempt"]))

    # Marcar cotización como aprobada
    conn.execute(
        "UPDATE quotes SET status='aprobada', updated_at=datetime('now','localtime') WHERE id=?",
        (quote_id,),
    )
    conn.commit()
    conn.close()
    return sale_id


def register_payment(sale_id: int, amount: float):
    conn = get_conn()
    conn.execute("""
        UPDATE sales SET
          amount_paid = MIN(total, amount_paid + ?),
          balance_due = MAX(0, total - amount_paid - ?),
          payment_status = CASE
            WHEN (amount_paid + ?) >= total THEN 'pagado'
            WHEN (amount_paid + ?) > 0      THEN 'parcial'
            ELSE 'pendiente' END
        WHERE id=?
    """, (amount, amount, amount, amount, sale_id))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Proyectos
# ─────────────────────────────────────────────────────────────────────────────

def get_projects(search: str = "", status: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    where = "WHERE (p.project_number LIKE ? OR p.name LIKE ? OR c.name LIKE ?)"
    params: list = [q, q, q]
    if status:
        where += " AND p.status=?"
        params.append(status)
    rows = conn.execute(f"""
        SELECT p.*, c.name AS client_name, v.name AS vendor_name
        FROM projects p
        LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN vendors v ON v.id=p.vendor_id
        {where}
        ORDER BY p.id DESC
    """, params).fetchall()
    conn.close()
    return rows


def get_project(project_id: int):
    conn = get_conn()
    project = conn.execute("""
        SELECT p.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address,
               v.name AS vendor_name, q.quote_number
        FROM projects p
        LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN vendors v ON v.id=p.vendor_id
        LEFT JOIN quotes q ON q.id=p.quotation_id
        WHERE p.id=?
    """, (project_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM project_items WHERE project_id=? ORDER BY id", (project_id,)
    ).fetchall()
    conn.close()
    return project, items


def upsert_project(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE projects SET name=?,client_id=?,vendor_id=?,quotation_id=?,status=?,priority=?,
            start_date=?,installation_date=?,delivery_date=?,end_date=?,address=?,description=?,
            technician=?,progress_pct=?,notes=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (data["name"], data.get("client_id"), data.get("vendor_id"), data.get("quotation_id"),
              data.get("status","planificado"), data.get("priority","normal"),
              data.get("start_date",""), data.get("installation_date",""),
              data.get("delivery_date",""), data.get("end_date",""),
              data.get("address",""), data.get("description",""),
              data.get("technician",""), data.get("progress_pct",0),
              data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        project_number = data.get("project_number") or next_project_number()
        cur = conn.execute("""
            INSERT INTO projects (project_number,name,client_id,vendor_id,quotation_id,status,priority,
            start_date,installation_date,delivery_date,end_date,address,description,technician,
            progress_pct,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (project_number, data["name"], data.get("client_id"), data.get("vendor_id"),
              data.get("quotation_id"), data.get("status","planificado"),
              data.get("priority","normal"), data.get("start_date",""),
              data.get("installation_date",""), data.get("delivery_date",""),
              data.get("end_date",""), data.get("address",""), data.get("description",""),
              data.get("technician",""), data.get("progress_pct",0), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def update_project_status(project_id: int, status: str, progress: int | None = None):
    conn = get_conn()
    if progress is not None:
        conn.execute(
            "UPDATE projects SET status=?, progress_pct=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, progress, project_id),
        )
    else:
        conn.execute(
            "UPDATE projects SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, project_id),
        )
    conn.commit()
    conn.close()


def delete_project(project_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()


def add_project_log(project_id: int, content: str, log_type: str = "nota", author: str = ""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO project_logs (project_id, log_type, content, author) VALUES (?,?,?,?)",
        (project_id, log_type, content, author),
    )
    conn.commit()
    conn.close()


def get_project_logs(project_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM project_logs WHERE project_id=? ORDER BY created_at DESC",
        (project_id,),
    ).fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Órdenes de Trabajo (OT)
# ─────────────────────────────────────────────────────────────────────────────

def get_work_orders(search: str = "", status: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    where = "WHERE (wo.ot_number LIKE ? OR c.name LIKE ? OR wo.technician LIKE ?)"
    params: list = [q, q, q]
    if status:
        where += " AND wo.status=?"
        params.append(status)
    rows = conn.execute(f"""
        SELECT wo.*, c.name AS client_name, p.project_number
        FROM work_orders wo
        LEFT JOIN clients c ON c.id=wo.client_id
        LEFT JOIN projects p ON p.id=wo.project_id
        {where}
        ORDER BY wo.id DESC
    """, params).fetchall()
    conn.close()
    return rows


def get_work_order(ot_id: int):
    conn = get_conn()
    ot = conn.execute("""
        SELECT wo.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address,
               p.project_number
        FROM work_orders wo
        LEFT JOIN clients c ON c.id=wo.client_id
        LEFT JOIN projects p ON p.id=wo.project_id
        WHERE wo.id=?
    """, (ot_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM ot_items WHERE ot_id=? ORDER BY id", (ot_id,)
    ).fetchall()
    conn.close()
    return ot, items


def upsert_work_order(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE work_orders SET client_id=?,project_id=?,vendor_id=?,type=?,status=?,priority=?,
            scheduled_date=?,start_date=?,end_date=?,description=?,technician=?,address=?,
            diagnosis=?,solution=?,travel_km=?,labor_hours=?,labor_rate=?,parts_cost=?,total_cost=?,
            notes=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (data.get("client_id"), data.get("project_id"), data.get("vendor_id"),
              data.get("type","instalación"), data.get("status","abierta"),
              data.get("priority","normal"), data.get("scheduled_date",""),
              data.get("start_date",""), data.get("end_date",""),
              data.get("description",""), data.get("technician",""), data.get("address",""),
              data.get("diagnosis",""), data.get("solution",""),
              data.get("travel_km",0), data.get("labor_hours",0), data.get("labor_rate",0),
              data.get("parts_cost",0), data.get("total_cost",0),
              data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        ot_number = data.get("ot_number") or next_ot_number()
        cur = conn.execute("""
            INSERT INTO work_orders (ot_number,client_id,project_id,vendor_id,type,status,priority,
            scheduled_date,start_date,end_date,description,technician,address,
            diagnosis,solution,travel_km,labor_hours,labor_rate,parts_cost,total_cost,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ot_number, data.get("client_id"), data.get("project_id"), data.get("vendor_id"),
              data.get("type","instalación"), data.get("status","abierta"),
              data.get("priority","normal"), data.get("scheduled_date",""),
              data.get("start_date",""), data.get("end_date",""),
              data.get("description",""), data.get("technician",""), data.get("address",""),
              data.get("diagnosis",""), data.get("solution",""),
              data.get("travel_km",0), data.get("labor_hours",0), data.get("labor_rate",0),
              data.get("parts_cost",0), data.get("total_cost",0), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def update_ot_status(ot_id: int, status: str):
    conn = get_conn()
    conn.execute(
        "UPDATE work_orders SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
        (status, ot_id),
    )
    conn.commit()
    conn.close()


def delete_work_order(ot_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM work_orders WHERE id=?", (ot_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Garantías
# ─────────────────────────────────────────────────────────────────────────────

def get_warranties(search: str = "", status: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    where = "WHERE (w.warranty_number LIKE ? OR c.name LIKE ? OR w.product_name LIKE ?)"
    params: list = [q, q, q]
    if status:
        where += " AND w.status=?"
        params.append(status)
    rows = conn.execute(f"""
        SELECT w.*, c.name AS client_name
        FROM warranties w LEFT JOIN clients c ON c.id=w.client_id
        {where}
        ORDER BY w.id DESC
    """, params).fetchall()
    conn.close()
    return rows


def upsert_warranty(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""
            UPDATE warranties SET client_id=?,project_id=?,ot_id=?,product_name=?,serial_number=?,
            issue_date=?,expiry_date=?,status=?,description=?,resolution=?,technician=?,notes=?
            WHERE id=?
        """, (data.get("client_id"), data.get("project_id"), data.get("ot_id"),
              data.get("product_name",""), data.get("serial_number",""),
              data.get("issue_date", str(date.today())), data.get("expiry_date",""),
              data.get("status","vigente"), data.get("description",""),
              data.get("resolution",""), data.get("technician",""), data.get("notes",""),
              data["id"]))
        rid = data["id"]
    else:
        warranty_number = data.get("warranty_number") or next_warranty_number()
        cur = conn.execute("""
            INSERT INTO warranties (warranty_number,client_id,project_id,ot_id,product_name,
            serial_number,issue_date,expiry_date,status,description,resolution,technician,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (warranty_number, data.get("client_id"), data.get("project_id"), data.get("ot_id"),
              data.get("product_name",""), data.get("serial_number",""),
              data.get("issue_date", str(date.today())), data.get("expiry_date",""),
              data.get("status","vigente"), data.get("description",""),
              data.get("resolution",""), data.get("technician",""), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Facturas
# ─────────────────────────────────────────────────────────────────────────────

def get_invoices(search: str = "") -> list:
    conn = get_conn()
    q = "%" + search + "%"
    rows = conn.execute("""
        SELECT i.*, c.name AS client_name
        FROM invoices i LEFT JOIN clients c ON c.id=i.client_id
        WHERE i.invoice_number LIKE ? OR c.name LIKE ?
        ORDER BY i.id DESC
    """, (q, q)).fetchall()
    conn.close()
    return rows


def create_invoice(sale_id: int, inv_type: str = "boleta") -> int:
    sale, _ = get_sale(sale_id)
    if not sale:
        raise ValueError(f"Venta {sale_id} no encontrada")
    invoice_number = next_invoice_number()
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO invoices (invoice_number,sale_id,client_id,invoice_date,type,status,
        subtotal,vat_amount,total)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (invoice_number, sale_id, sale["client_id"], str(date.today()),
          inv_type, "emitida", sale["subtotal"], sale["vat_amount"], sale["total"]))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard / KPIs
# ─────────────────────────────────────────────────────────────────────────────

def get_dashboard_kpis() -> dict:
    """Retorna métricas principales para la vista de Inicio."""
    conn = get_conn()
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    total_clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
    low_stock_count = conn.execute(
        "SELECT COUNT(*) FROM products WHERE active=1 AND stock_min>0 AND stock<=stock_min"
    ).fetchone()[0]

    open_quotes = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total),0) FROM quotes WHERE status IN ('borrador','enviada')"
    ).fetchone()
    month_sales = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM sales WHERE sale_date >= ?", (month_start,)
    ).fetchone()[0]
    pending_balance = conn.execute(
        "SELECT COALESCE(SUM(balance_due),0) FROM sales WHERE payment_status IN ('pendiente','parcial')"
    ).fetchone()[0]

    open_ot = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE status IN ('abierta','en_progreso')"
    ).fetchone()[0]
    active_projects = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE status IN ('planificado','en_progreso')"
    ).fetchone()[0]

    conn.close()
    return {
        "total_clients":    total_clients,
        "total_products":   total_products,
        "low_stock_count":  low_stock_count,
        "open_quotes":      open_quotes[0],
        "open_quotes_value":open_quotes[1],
        "month_sales":      month_sales,
        "pending_balance":  pending_balance,
        "open_ot":          open_ot,
        "active_projects":  active_projects,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Respaldo y Restauración
# ─────────────────────────────────────────────────────────────────────────────

def export_db_bytes() -> bytes:
    """Devuelve el contenido binario de la base de datos para descarga."""
    with open(str(DB_PATH), "rb") as f:
        return f.read()


def restore_db_from_bytes(data: bytes) -> bool:
    """Restaura la base de datos desde bytes. Hace backup previo."""
    backup_path = str(DB_PATH) + ".backup"
    try:
        if DB_PATH.exists():
            import shutil
            shutil.copy2(str(DB_PATH), backup_path)
        with open(str(DB_PATH), "wb") as f:
            f.write(data)
        # Verificar que el archivo es un SQLite válido
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        return True
    except Exception:
        # Revertir al backup
        if os.path.exists(backup_path):
            import shutil
            shutil.copy2(backup_path, str(DB_PATH))
        return False


def get_table_stats() -> dict:
    """Conteo de registros por tabla para panel de administración."""
    tables = [
        "clients", "vendors", "suppliers", "products", "supplies", "tools",
        "kits", "quotes", "quote_items", "sales", "sale_items", "invoices",
        "projects", "project_items", "work_orders", "ot_items",
        "warranties", "purchases", "stock_movements", "audit_log",
    ]
    conn = get_conn()
    stats = {}
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            stats[t] = n
        except Exception:
            stats[t] = "N/A"
    conn.close()
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Auditoría
# ─────────────────────────────────────────────────────────────────────────────

def log_action(action: str, table: str = "", record_id: int | None = None,
               user: str = "system", detail: str = ""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (action, table_name, record_id, user, detail) VALUES (?,?,?,?,?)",
        (action, table, record_id, user, detail),
    )
    conn.commit()
    conn.close()


def get_audit_log(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Helpers pandas — usados por las vistas
# ─────────────────────────────────────────────────────────────────────────────

def get_df(sql: str, params: tuple = ()):
    """
    Ejecuta una consulta SQL y devuelve un pandas DataFrame.
    Las vistas usan get_df() para cargar datos listos para st.dataframe().
    Compatibilidad: acepta tanto nombres de tabla nuevos (products, work_orders)
    como alias legacy (inventory → products, stock_current → stock, etc.)
    mediante una capa de traducción automática.
    """
    import pandas as pd

    # Traducción automática de nombres legacy → nuevo esquema
    _aliases = {
        "inventory":       "products",
        "stock_current":   "stock",
        "cost_unit":       "cost_price",
        "margin_pct":      "margin",
    }
    translated = sql
    for old, new in _aliases.items():
        translated = translated.replace(old, new)

    conn = get_conn()
    try:
        df = pd.read_sql_query(translated, conn, params=params)
    except Exception:
        # Si la traducción falla, intentar con el SQL original
        try:
            df = pd.read_sql_query(sql, conn, params=params)
        except Exception:
            df = pd.DataFrame()
    conn.close()
    return df


def get_dashboard_work_orders_df(limit: int = 8):
    """
    Devuelve un DataFrame con las OT activas para el dashboard de inicio.
    Incluye número, cliente, tipo, estado, fecha programada y técnico.
    """
    import pandas as pd

    conn = get_conn()
    try:
        df = pd.read_sql_query(f"""
            SELECT
                wo.ot_number        AS 'N° OT',
                c.name              AS 'Cliente',
                wo.type             AS 'Tipo',
                wo.status           AS 'Estado',
                wo.scheduled_date   AS 'Fecha',
                wo.technician       AS 'Técnico'
            FROM work_orders wo
            LEFT JOIN clients c ON c.id = wo.client_id
            WHERE wo.status IN ('abierta','en_progreso','Pendiente','Agendada',
                                'En ejecución','Abierta','En proceso')
            ORDER BY wo.scheduled_date ASC
            LIMIT {int(limit)}
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df
