"""
database.py — Abaroa Smart ERP
Capa de acceso a datos basada en el esquema original de abaroa_smart_erp.db.
Todas las funciones usan los nombres de tabla y columnas originales para que
las vistas funcionen sin modificaciones.
"""

import sqlite3
import hashlib
import os
import shutil
from datetime import date, datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent / "abaroa_smart_erp.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Esquema — idéntico al original
# ─────────────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS clients (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    phone   TEXT,
    email   TEXT,
    address TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    role  TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT UNIQUE NOT NULL,
    phone          TEXT,
    email          TEXT,
    contact_person TEXT,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS inventory (
    sku                  TEXT PRIMARY KEY,
    description          TEXT NOT NULL,
    category             TEXT,
    protocol             TEXT,
    stock_initial        INTEGER,
    stock_current        INTEGER,
    cost_unit            INTEGER,
    margin_pct           INTEGER,
    sale_price           INTEGER,
    provider             TEXT,
    is_service           INTEGER DEFAULT 0,
    stock_min            INTEGER DEFAULT 0,
    image_path           TEXT    DEFAULT '',
    location             TEXT    DEFAULT '',
    stock_reserved       INTEGER DEFAULT 0,
    average_landed_cost  INTEGER DEFAULT 0,
    publish_web          TEXT    DEFAULT 'NO',
    description_web      TEXT,
    source_category      TEXT,
    source_subcategory   TEXT
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sku            TEXT    NOT NULL,
    movement_type  TEXT    NOT NULL,
    quantity       INTEGER DEFAULT 0,
    reference_type TEXT,
    reference_id   INTEGER,
    notes          TEXT,
    created_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    sale_price INTEGER DEFAULT 0,
    notes      TEXT
);

CREATE TABLE IF NOT EXISTS kit_items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_id   INTEGER NOT NULL,
    sku      TEXT    NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number             TEXT    NOT NULL,
    quote_date               TEXT    NOT NULL,
    client_id                INTEGER,
    vendor_id                INTEGER,
    validity_days            INTEGER DEFAULT 10,
    status                   TEXT    DEFAULT 'Pendiente',
    notes                    TEXT,
    subtotal_products        INTEGER DEFAULT 0,
    subtotal_services_exempt INTEGER DEFAULT 0,
    vat_products             INTEGER DEFAULT 0,
    total                    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quote_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id   INTEGER NOT NULL,
    item_type  TEXT    NOT NULL,
    sku        TEXT,
    description TEXT   NOT NULL,
    quantity   INTEGER DEFAULT 1,
    unit_price INTEGER DEFAULT 0,
    line_total INTEGER DEFAULT 0,
    vat_exempt INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date       TEXT    NOT NULL,
    client_id       INTEGER,
    quote_id        INTEGER,
    total           INTEGER DEFAULT 0,
    material_cost   INTEGER DEFAULT 0,
    gross_margin    INTEGER DEFAULT 0,
    gross_margin_pct REAL   DEFAULT 0
);

CREATE TABLE IF NOT EXISTS billing (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id        INTEGER,
    client_id      INTEGER,
    total          INTEGER DEFAULT 0,
    advance_50     INTEGER DEFAULT 0,
    balance_50     INTEGER DEFAULT 0,
    payment_status TEXT    DEFAULT 'Pendiente'
);

CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number      TEXT    NOT NULL,
    quotation_id        INTEGER,
    client_id           INTEGER,
    name                TEXT,
    description         TEXT,
    status              TEXT    DEFAULT 'Pendiente',
    technical_status    TEXT    DEFAULT 'Pendiente',
    installation_date   TEXT,
    delivery_date       TEXT,
    configuration_url   TEXT,
    notes               TEXT,
    checklist_required  INTEGER DEFAULT 1,
    created_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    is_active           INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS project_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER NOT NULL,
    item_type         TEXT    NOT NULL,
    sku               TEXT,
    description       TEXT    NOT NULL,
    quantity          INTEGER DEFAULT 1,
    unit_cost         INTEGER DEFAULT 0,
    unit_price        INTEGER DEFAULT 0,
    total_price       INTEGER DEFAULT 0,
    reserved_quantity INTEGER DEFAULT 0,
    used_quantity     INTEGER DEFAULT 0,
    created_at        TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_checklists (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    template_id  INTEGER,
    status       TEXT    DEFAULT 'Pendiente',
    completed_at TEXT,
    completed_by TEXT,
    notes        TEXT,
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_checklist_items (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_checklist_id INTEGER NOT NULL,
    item_text            TEXT    NOT NULL,
    is_required          INTEGER DEFAULT 1,
    is_checked           INTEGER DEFAULT 0,
    checked_at           TEXT,
    evidence_note        TEXT,
    created_at           TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ot_number           TEXT    NOT NULL,
    client_id           INTEGER,
    vendor_id           INTEGER,
    quote_id            INTEGER,
    status              TEXT    DEFAULT 'Pendiente',
    scheduled_date      TEXT,
    address             TEXT,
    hours_work          REAL    DEFAULT 0,
    labor_cost          INTEGER DEFAULT 0,
    travel_cost         INTEGER DEFAULT 0,
    extra_material_cost INTEGER DEFAULT 0,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS work_order_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id  INTEGER NOT NULL,
    sku            TEXT,
    description    TEXT,
    quantity       INTEGER DEFAULT 1,
    cost_unit      INTEGER DEFAULT 0,
    line_cost      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS warranties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER,
    sale_id         INTEGER UNIQUE,
    install_date    TEXT,
    warranty_months INTEGER DEFAULT 6,
    expiry_date     TEXT,
    status          TEXT    DEFAULT 'Vigente',
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS installations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL,
    install_date    TEXT    NOT NULL,
    sku             TEXT,
    description     TEXT    NOT NULL,
    serial_number   TEXT,
    location        TEXT,
    notes           TEXT,
    warranty_months INTEGER DEFAULT 12
);

CREATE TABLE IF NOT EXISTS tools_assets (
    asset_id           TEXT    PRIMARY KEY,
    tool_name          TEXT    NOT NULL,
    category           TEXT    DEFAULT 'Herramienta',
    provider           TEXT,
    quantity           INTEGER DEFAULT 1,
    cost_unit          INTEGER DEFAULT 0,
    purchase_date      TEXT    DEFAULT '',
    useful_life_months INTEGER DEFAULT 12,
    monthly_cost       INTEGER DEFAULT 0,
    status             TEXT    DEFAULT 'Activa',
    notes              TEXT    DEFAULT '',
    created_at         TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_batches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT,
    purchase_date TEXT,
    shipping_cost INTEGER DEFAULT 0,
    customs_cost  INTEGER DEFAULT 0,
    other_costs   INTEGER DEFAULT 0,
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_batch_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER NOT NULL,
    product_sku TEXT    NOT NULL,
    quantity    INTEGER DEFAULT 1,
    unit_price  INTEGER DEFAULT 0,
    landed_cost INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS supplies_catalog (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    description       TEXT UNIQUE NOT NULL,
    default_unit_price INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS checklist_templates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    description  TEXT,
    service_type TEXT,
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checklist_template_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    item_order  INTEGER DEFAULT 1,
    item_text   TEXT    NOT NULL,
    is_required INTEGER DEFAULT 1,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db():
    """Crea todas las tablas si no existen. Idempotente."""
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def remove_duplicate_rows():
    """Elimina duplicados en tablas con UNIQUE constraints."""
    conn = get_conn()
    conn.execute("DELETE FROM quotes WHERE id NOT IN (SELECT MIN(id) FROM quotes GROUP BY quote_number)")
    conn.execute("DELETE FROM kits   WHERE id NOT IN (SELECT MIN(id) FROM kits   GROUP BY code)")
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────
def _hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# app_settings
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULTS = {
    "admin_username":   "admin",
    "admin_password":   _hash_password("admin123"),
    "company_name":     "Abaroa Smart",
    "company_phone":    "+56 9 8183 8679",
    "company_email":    "contacto@abaroasmart.com",
    "company_address":  "Osorno, Región de Los Lagos",
    "company_web":      "www.abaroasmart.com",
    "vat_rate":         "19",
    "default_margin":   "30",
    "quote_prefix":     "COT",
    "ot_prefix":        "OT",
    "project_prefix":   "PROY",
    "warranty_months":  "6",
    "low_stock_alert":  "1",
}


def ensure_app_settings():
    conn = get_conn()
    # Migrar clave legacy admin_password_hash → admin_password
    row = conn.execute("SELECT value FROM app_settings WHERE key='admin_password_hash'").fetchone()
    if row:
        conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('admin_password', ?)", (row["value"],))
        conn.execute("DELETE FROM app_settings WHERE key='admin_password_hash'")
    for k, v in _DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (k, v))
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)", (key, str(value)))
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Autenticación
# ─────────────────────────────────────────────────────────────────────────────
def verify_admin_credentials(username: str, password: str) -> bool:
    stored_user = get_setting("admin_username", "admin")
    stored_hash = get_setting("admin_password", _hash_password("admin123"))
    return (username.strip() == stored_user.strip() and
            _hash_password(password) == stored_hash)


def admin_logged_in() -> bool:
    try:
        import streamlit as st
        return bool(st.session_state.get("admin_logged_in", False))
    except Exception:
        return False


def change_admin_password(new_password: str):
    set_setting("admin_password", _hash_password(new_password))


# ─────────────────────────────────────────────────────────────────────────────
# Recálculo de precios
# ─────────────────────────────────────────────────────────────────────────────
def recalc_all_sale_prices():
    """Recalcula sale_price = cost_unit * (1 + margin_pct/100)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT sku, cost_unit, margin_pct, sale_price FROM inventory WHERE is_service=0"
    ).fetchall()
    for r in rows:
        if r["cost_unit"] and r["margin_pct"]:
            calc = round(r["cost_unit"] * (1 + r["margin_pct"] / 100))
            if abs(calc - (r["sale_price"] or 0)) > 1:
                conn.execute("UPDATE inventory SET sale_price=? WHERE sku=?", (calc, r["sku"]))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Recálculo de stock
# ─────────────────────────────────────────────────────────────────────────────
def recalc_stock():
    """Recalcula stock_current desde inventory_movements si hay movimientos."""
    conn = get_conn()
    movements = conn.execute("""
        SELECT sku,
               SUM(CASE
                   WHEN movement_type IN ('PURCHASE','ENTRADA','entrada','ADJUSTMENT_IN') THEN quantity
                   WHEN movement_type IN ('SALE','SALIDA','salida','PROJECT_CONSUMPTION','RESERVE') THEN -quantity
                   ELSE 0 END) AS net
        FROM inventory_movements GROUP BY sku
    """).fetchall()
    for m in movements:
        conn.execute(
            "UPDATE inventory SET stock_current = MAX(0, COALESCE(stock_initial,0) + ?) WHERE sku=?",
            (m["net"] or 0, m["sku"])
        )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Alertas
# ─────────────────────────────────────────────────────────────────────────────
def get_alerts_data() -> list:
    alerts = []
    conn   = get_conn()
    today  = date.today().isoformat()

    # Stock bajo mínimo
    for r in conn.execute("""
        SELECT sku, description, stock_current, stock_min FROM inventory
        WHERE is_service=0 AND stock_min>0 AND stock_current<=stock_min
        ORDER BY (stock_min-stock_current) DESC LIMIT 10
    """):
        alerts.append({"level": "warning",
                        "title": f"Stock bajo: {r['description']}",
                        "detail": f"SKU {r['sku']} · Stock: {r['stock_current']} · Mínimo: {r['stock_min']}"})

    # Cotizaciones enviadas vencidas
    for r in conn.execute("""
        SELECT q.quote_number, c.name AS cn,
               date(q.quote_date, '+'||q.validity_days||' days') AS exp
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id
        WHERE q.status IN ('Enviada','Pendiente')
          AND date(q.quote_date,'+'||q.validity_days||' days') < ?
        LIMIT 5
    """, (today,)):
        alerts.append({"level": "warning",
                        "title": f"Cotización vencida: {r['quote_number']}",
                        "detail": f"Cliente: {r['cn'] or '-'} · Venció: {r['exp']}"})

    # OT vencidas
    for r in conn.execute("""
        SELECT ot_number, scheduled_date FROM work_orders
        WHERE status IN ('Pendiente','Agendada','En ejecución')
          AND scheduled_date != '' AND scheduled_date < ?
        ORDER BY scheduled_date LIMIT 5
    """, (today,)):
        alerts.append({"level": "info",
                        "title": f"OT vencida: {r['ot_number']}",
                        "detail": f"Programada: {r['scheduled_date']}"})

    # Garantías por vencer (30 días)
    for r in conn.execute("""
        SELECT w.id, c.name AS cn, w.expiry_date FROM warranties w
        LEFT JOIN clients c ON c.id=w.client_id
        WHERE w.status='Vigente' AND w.expiry_date != ''
          AND w.expiry_date BETWEEN ? AND date(?,' +30 days')
        LIMIT 5
    """, (today, today)):
        alerts.append({"level": "info",
                        "title": f"Garantía por vencer #{r['id']}",
                        "detail": f"Cliente: {r['cn'] or '-'} · Vence: {r['expiry_date']}"})

    conn.close()
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Helpers pandas — usados por las vistas
# ─────────────────────────────────────────────────────────────────────────────
def get_df(sql: str, params: tuple = ()):
    """Ejecuta SQL y devuelve pandas DataFrame. Retorna DF vacío si falla."""
    import pandas as pd
    conn = get_conn()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_dashboard_work_orders_df(limit: int = 8):
    """OT activas para el dashboard."""
    import pandas as pd
    conn = get_conn()
    try:
        df = pd.read_sql_query(f"""
            SELECT wo.ot_number AS 'N° OT', c.name AS 'Cliente',
                   wo.status AS 'Estado', wo.scheduled_date AS 'Fecha',
                   (wo.labor_cost + wo.travel_cost + wo.extra_material_cost) AS 'Costo'
            FROM work_orders wo
            LEFT JOIN clients c ON c.id=wo.client_id
            WHERE wo.status IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso')
            ORDER BY wo.scheduled_date ASC
            LIMIT {int(limit)}
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Numeración automática
# ─────────────────────────────────────────────────────────────────────────────
def _next_number(prefix: str, table: str, col: str) -> str:
    conn = get_conn()
    row  = conn.execute(f"SELECT {col} FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    num = 1
    if row and row[0]:
        try:
            num = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            pass
    return f"{prefix}-{num:04d}"


def next_quote_number() -> str:
    from datetime import datetime
    return f"COT-{datetime.now().strftime('%Y%m%d-%H%M')}"

def next_ot_number() -> str:
    return _next_number(get_setting("ot_prefix","OT"), "work_orders", "ot_number")

def next_project_number() -> str:
    from datetime import datetime
    return f"PROY-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Clientes
# ─────────────────────────────────────────────────────────────────────────────
def get_clients(search: str = "") -> list:
    conn = get_conn()
    q    = f"%{search}%"
    rows = conn.execute(
        "SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? ORDER BY name",
        (q, q, q)
    ).fetchall()
    conn.close()
    return rows

def get_client(client_id: int):
    conn = get_conn()
    row  = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    conn.close()
    return row

def upsert_client(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("UPDATE clients SET name=?,phone=?,email=?,address=? WHERE id=?",
                     (data["name"], data.get("phone",""), data.get("email",""),
                      data.get("address",""), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("INSERT INTO clients(name,phone,email,address) VALUES(?,?,?,?)",
                           (data["name"], data.get("phone",""), data.get("email",""), data.get("address","")))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid

def delete_client(client_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Vendedores
# ─────────────────────────────────────────────────────────────────────────────
def get_vendors(active_only: bool = False) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM vendors ORDER BY name").fetchall()
    conn.close()
    return rows

def get_vendor(vendor_id: int):
    conn = get_conn()
    row  = conn.execute("SELECT * FROM vendors WHERE id=?", (vendor_id,)).fetchone()
    conn.close()
    return row

def upsert_vendor(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("UPDATE vendors SET name=?,email=?,phone=?,role=? WHERE id=?",
                     (data["name"], data.get("email",""), data.get("phone",""),
                      data.get("role",""), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("INSERT INTO vendors(name,email,phone,role) VALUES(?,?,?,?)",
                           (data["name"], data.get("email",""), data.get("phone",""), data.get("role","")))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Proveedores
# ─────────────────────────────────────────────────────────────────────────────
def get_suppliers(search: str = "") -> list:
    conn = get_conn()
    q    = f"%{search}%"
    rows = conn.execute(
        "SELECT * FROM suppliers WHERE name LIKE ? OR email LIKE ? ORDER BY name", (q, q)
    ).fetchall()
    conn.close()
    return rows

def get_supplier(supplier_id: int):
    conn = get_conn()
    row  = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    conn.close()
    return row

def upsert_supplier(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("UPDATE suppliers SET name=?,phone=?,email=?,contact_person=?,notes=? WHERE id=?",
                     (data["name"], data.get("phone",""), data.get("email",""),
                      data.get("contact_person",""), data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute(
            "INSERT INTO suppliers(name,phone,email,contact_person,notes) VALUES(?,?,?,?,?)",
            (data["name"], data.get("phone",""), data.get("email",""),
             data.get("contact_person",""), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid

def delete_supplier(supplier_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Inventario
# ─────────────────────────────────────────────────────────────────────────────
def get_products(search: str = "", active_only: bool = True, category: str = "") -> list:
    conn   = get_conn()
    q      = f"%{search}%"
    where  = "WHERE (sku LIKE ? OR description LIKE ? OR category LIKE ?)"
    params = [q, q, q]
    if category:
        where += " AND category=?"; params.append(category)
    rows = conn.execute(f"SELECT * FROM inventory {where} ORDER BY description", params).fetchall()
    conn.close()
    return rows

def get_product(sku: str):
    conn = get_conn()
    row  = conn.execute("SELECT * FROM inventory WHERE sku=?", (sku,)).fetchone()
    conn.close()
    return row

def get_product_by_sku(sku: str):
    return get_product(sku)

def upsert_product(data: dict) -> str:
    conn = get_conn()
    cost   = int(data.get("cost_unit", 0) or 0)
    margin = int(data.get("margin_pct", 30) or 30)
    sale   = round(cost * (1 + margin / 100))
    fields = ("sku","description","category","protocol","stock_current","cost_unit",
              "margin_pct","sale_price","provider","is_service","stock_min",
              "image_path","location","publish_web","description_web")
    vals   = (data["sku"], data.get("description",""), data.get("category",""),
              data.get("protocol",""), int(data.get("stock_current",0)),
              cost, margin, sale, data.get("provider",""),
              int(data.get("is_service",0)), int(data.get("stock_min",0)),
              data.get("image_path",""), data.get("location",""),
              data.get("publish_web","NO"), data.get("description_web",""))
    existing = conn.execute("SELECT sku FROM inventory WHERE sku=?", (data["sku"],)).fetchone()
    if existing:
        sets = ", ".join(f"{f}=?" for f in fields[1:])
        conn.execute(f"UPDATE inventory SET {sets} WHERE sku=?", vals[1:] + (data["sku"],))
    else:
        conn.execute(f"INSERT INTO inventory({','.join(fields)}) VALUES({','.join(['?']*len(fields))})", vals)
    conn.commit(); conn.close()
    return data["sku"]

def delete_product(sku: str):
    conn = get_conn()
    conn.execute("DELETE FROM inventory WHERE sku=?", (sku,))
    conn.commit(); conn.close()

def get_product_categories() -> list:
    conn  = get_conn()
    rows  = conn.execute(
        "SELECT DISTINCT category FROM inventory WHERE category!='' ORDER BY category"
    ).fetchall()
    conn.close()
    return [r["category"] for r in rows]

def adjust_stock(sku: str, quantity: float, movement_type: str = "ADJUSTMENT",
                 ref_type: str = "", ref_id=None, notes: str = ""):
    conn = get_conn()
    sign = -1 if movement_type in ("SALE","SALIDA","PROJECT_CONSUMPTION","RESERVE") else 1
    conn.execute(
        "UPDATE inventory SET stock_current = MAX(0, COALESCE(stock_current,0) + ?) WHERE sku=?",
        (sign * abs(quantity), sku)
    )
    conn.execute(
        "INSERT INTO inventory_movements(sku,movement_type,quantity,reference_type,reference_id,notes) VALUES(?,?,?,?,?,?)",
        (sku, movement_type, abs(quantity), ref_type, ref_id, notes)
    )
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Herramientas
# ─────────────────────────────────────────────────────────────────────────────
def get_tools(search: str = "") -> list:
    conn = get_conn()
    q    = f"%{search}%"
    rows = conn.execute(
        "SELECT * FROM tools_assets WHERE tool_name LIKE ? OR asset_id LIKE ? OR category LIKE ? ORDER BY tool_name",
        (q, q, q)
    ).fetchall()
    conn.close()
    return rows

def upsert_tool(data: dict) -> str:
    conn = get_conn()
    existing = conn.execute("SELECT asset_id FROM tools_assets WHERE asset_id=?", (data["asset_id"],)).fetchone()
    if existing:
        conn.execute("""UPDATE tools_assets SET tool_name=?,category=?,provider=?,quantity=?,cost_unit=?,
            purchase_date=?,useful_life_months=?,monthly_cost=?,status=?,notes=? WHERE asset_id=?""",
            (data["tool_name"], data.get("category","Herramienta"), data.get("provider",""),
             int(data.get("quantity",1)), int(data.get("cost_unit",0)),
             data.get("purchase_date",""), int(data.get("useful_life_months",12)),
             int(data.get("monthly_cost",0)), data.get("status","Activa"),
             data.get("notes",""), data["asset_id"]))
    else:
        conn.execute("""INSERT INTO tools_assets(asset_id,tool_name,category,provider,quantity,cost_unit,
            purchase_date,useful_life_months,monthly_cost,status,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (data["asset_id"], data["tool_name"], data.get("category","Herramienta"),
             data.get("provider",""), int(data.get("quantity",1)), int(data.get("cost_unit",0)),
             data.get("purchase_date",""), int(data.get("useful_life_months",12)),
             int(data.get("monthly_cost",0)), data.get("status","Activa"), data.get("notes","")))
    conn.commit(); conn.close()
    return data["asset_id"]

def delete_tool(asset_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM tools_assets WHERE asset_id=?", (asset_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Kits
# ─────────────────────────────────────────────────────────────────────────────
def get_kits(search: str = "") -> list:
    conn = get_conn()
    q    = f"%{search}%"
    rows = conn.execute(
        "SELECT * FROM kits WHERE name LIKE ? OR code LIKE ? ORDER BY name", (q, q)
    ).fetchall()
    conn.close()
    return rows

def get_kit(kit_id: int):
    conn  = get_conn()
    kit   = conn.execute("SELECT * FROM kits WHERE id=?", (kit_id,)).fetchone()
    items = conn.execute("""
        SELECT ki.*, inv.description, inv.sale_price
        FROM kit_items ki LEFT JOIN inventory inv ON inv.sku=ki.sku
        WHERE ki.kit_id=? ORDER BY ki.id
    """, (kit_id,)).fetchall()
    conn.close()
    return kit, items

def upsert_kit(data: dict, items: list) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("UPDATE kits SET code=?,name=?,sale_price=?,notes=? WHERE id=?",
                     (data["code"], data["name"], int(data.get("sale_price",0)),
                      data.get("notes",""), data["id"]))
        kid = data["id"]
    else:
        cur = conn.execute("INSERT INTO kits(code,name,sale_price,notes) VALUES(?,?,?,?)",
                           (data["code"], data["name"], int(data.get("sale_price",0)), data.get("notes","")))
        kid = cur.lastrowid
    conn.execute("DELETE FROM kit_items WHERE kit_id=?", (kid,))
    for item in items:
        conn.execute("INSERT INTO kit_items(kit_id,sku,quantity) VALUES(?,?,?)",
                     (kid, item["sku"], int(item.get("quantity",1))))
    conn.commit(); conn.close()
    return kid

def delete_kit(kit_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM kits WHERE id=?", (kit_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Cotizaciones
# ─────────────────────────────────────────────────────────────────────────────
def get_quotes(search: str = "", status: str = "") -> list:
    conn   = get_conn()
    q      = f"%{search}%"
    where  = "WHERE (qu.quote_number LIKE ? OR c.name LIKE ?)"
    params = [q, q]
    if status:
        where += " AND qu.status=?"; params.append(status)
    rows = conn.execute(f"""
        SELECT qu.*, c.name AS client_name, v.name AS vendor_name
        FROM quotes qu
        LEFT JOIN clients c ON c.id=qu.client_id
        LEFT JOIN vendors v ON v.id=qu.vendor_id
        {where} ORDER BY qu.id DESC
    """, params).fetchall()
    conn.close()
    return rows

def get_quote(quote_id: int):
    conn  = get_conn()
    quote = conn.execute("""
        SELECT qu.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address,
               v.name AS vendor_name
        FROM quotes qu
        LEFT JOIN clients c ON c.id=qu.client_id
        LEFT JOIN vendors v ON v.id=qu.vendor_id
        WHERE qu.id=?
    """, (quote_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM quote_items WHERE quote_id=? ORDER BY id", (quote_id,)
    ).fetchall()
    conn.close()
    return quote, items

def upsert_quote(data: dict, items: list) -> int:
    vat_rate   = float(get_setting("vat_rate","19")) / 100
    subtotal_p = sum(int(i.get("line_total",0)) for i in items if not i.get("vat_exempt"))
    subtotal_s = sum(int(i.get("line_total",0)) for i in items if i.get("vat_exempt"))
    vat        = round(subtotal_p * vat_rate)
    total      = subtotal_p + subtotal_s + vat
    conn       = get_conn()
    if data.get("id"):
        conn.execute("""UPDATE quotes SET client_id=?,vendor_id=?,quote_date=?,validity_days=?,
            status=?,notes=?,subtotal_products=?,subtotal_services_exempt=?,vat_products=?,total=?
            WHERE id=?""",
            (data.get("client_id"), data.get("vendor_id"), data.get("quote_date", str(date.today())),
             int(data.get("validity_days",10)), data.get("status","Pendiente"), data.get("notes",""),
             subtotal_p, subtotal_s, vat, total, data["id"]))
        qid = data["id"]
        conn.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
    else:
        qn  = data.get("quote_number") or next_quote_number()
        cur = conn.execute("""INSERT INTO quotes(quote_number,quote_date,client_id,vendor_id,
            validity_days,status,notes,subtotal_products,subtotal_services_exempt,vat_products,total)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (qn, data.get("quote_date", str(date.today())), data.get("client_id"),
             data.get("vendor_id"), int(data.get("validity_days",10)),
             data.get("status","Pendiente"), data.get("notes",""),
             subtotal_p, subtotal_s, vat, total))
        qid = cur.lastrowid
    for item in items:
        conn.execute("""INSERT INTO quote_items(quote_id,item_type,sku,description,
            quantity,unit_price,line_total,vat_exempt) VALUES(?,?,?,?,?,?,?,?)""",
            (qid, item.get("item_type","producto"), item.get("sku",""),
             item.get("description",""), int(item.get("quantity",1)),
             int(item.get("unit_price",0)), int(item.get("line_total",0)),
             int(item.get("vat_exempt",0))))
    conn.commit(); conn.close()
    return qid

def update_quote_status(quote_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE quotes SET status=? WHERE id=?", (status, quote_id))
    conn.commit(); conn.close()

def delete_quote(quote_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM quotes WHERE id=?", (quote_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Proyectos
# ─────────────────────────────────────────────────────────────────────────────
def get_projects(search: str = "", status: str = "") -> list:
    conn   = get_conn()
    q      = f"%{search}%"
    where  = "WHERE (p.project_number LIKE ? OR p.name LIKE ? OR c.name LIKE ?)"
    params = [q, q, q]
    if status:
        where += " AND p.status=?"; params.append(status)
    rows = conn.execute(f"""
        SELECT p.*, c.name AS client_name, v.name AS vendor_name,
               qu.quote_number
        FROM projects p
        LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN vendors v ON v.id=p.client_id
        LEFT JOIN quotes qu ON qu.id=p.quotation_id
        {where} ORDER BY p.id DESC
    """, params).fetchall()
    conn.close()
    return rows

def get_project(project_id: int):
    conn    = get_conn()
    project = conn.execute("""
        SELECT p.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address,
               qu.quote_number
        FROM projects p
        LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN quotes qu ON qu.id=p.quotation_id
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
        conn.execute("""UPDATE projects SET name=?,client_id=?,quotation_id=?,status=?,
            technical_status=?,installation_date=?,delivery_date=?,configuration_url=?,
            description=?,notes=?,checklist_required=?,is_active=?,
            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (data.get("name",""), data.get("client_id"), data.get("quotation_id"),
             data.get("status","Pendiente"), data.get("technical_status","Pendiente"),
             data.get("installation_date",""), data.get("delivery_date",""),
             data.get("configuration_url",""), data.get("description",""),
             data.get("notes",""), int(data.get("checklist_required",1)),
             int(data.get("is_active",1)), data["id"]))
        rid = data["id"]
    else:
        pn  = data.get("project_number") or next_project_number()
        cur = conn.execute("""INSERT INTO projects(project_number,name,client_id,quotation_id,
            status,technical_status,installation_date,delivery_date,configuration_url,
            description,notes,checklist_required,is_active)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pn, data.get("name",""), data.get("client_id"), data.get("quotation_id"),
             data.get("status","Pendiente"), data.get("technical_status","Pendiente"),
             data.get("installation_date",""), data.get("delivery_date",""),
             data.get("configuration_url",""), data.get("description",""),
             data.get("notes",""), int(data.get("checklist_required",1)),
             int(data.get("is_active",1))))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid

def delete_project(project_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Órdenes de Trabajo
# ─────────────────────────────────────────────────────────────────────────────
def get_work_orders(search: str = "", status: str = "") -> list:
    conn   = get_conn()
    q      = f"%{search}%"
    where  = "WHERE (wo.ot_number LIKE ? OR c.name LIKE ?)"
    params = [q, q]
    if status:
        where += " AND wo.status=?"; params.append(status)
    rows = conn.execute(f"""
        SELECT wo.*, c.name AS client_name
        FROM work_orders wo LEFT JOIN clients c ON c.id=wo.client_id
        {where} ORDER BY wo.id DESC
    """, params).fetchall()
    conn.close()
    return rows

def get_work_order(ot_id: int):
    conn = get_conn()
    ot   = conn.execute("""
        SELECT wo.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address
        FROM work_orders wo LEFT JOIN clients c ON c.id=wo.client_id
        WHERE wo.id=?
    """, (ot_id,)).fetchone()
    items = conn.execute(
        "SELECT * FROM work_order_items WHERE work_order_id=? ORDER BY id", (ot_id,)
    ).fetchall()
    conn.close()
    return ot, items

def upsert_work_order(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""UPDATE work_orders SET client_id=?,vendor_id=?,quote_id=?,status=?,
            scheduled_date=?,address=?,hours_work=?,labor_cost=?,travel_cost=?,
            extra_material_cost=?,notes=? WHERE id=?""",
            (data.get("client_id"), data.get("vendor_id"), data.get("quote_id"),
             data.get("status","Pendiente"), data.get("scheduled_date",""),
             data.get("address",""), float(data.get("hours_work",0)),
             int(data.get("labor_cost",0)), int(data.get("travel_cost",0)),
             int(data.get("extra_material_cost",0)), data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        otn = data.get("ot_number") or next_ot_number()
        cur = conn.execute("""INSERT INTO work_orders(ot_number,client_id,vendor_id,quote_id,
            status,scheduled_date,address,hours_work,labor_cost,travel_cost,
            extra_material_cost,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (otn, data.get("client_id"), data.get("vendor_id"), data.get("quote_id"),
             data.get("status","Pendiente"), data.get("scheduled_date",""),
             data.get("address",""), float(data.get("hours_work",0)),
             int(data.get("labor_cost",0)), int(data.get("travel_cost",0)),
             int(data.get("extra_material_cost",0)), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid

def update_ot_status(ot_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE work_orders SET status=? WHERE id=?", (status, ot_id))
    conn.commit(); conn.close()

def delete_work_order(ot_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM work_orders WHERE id=?", (ot_id,))
    conn.commit(); conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Garantías
# ─────────────────────────────────────────────────────────────────────────────
def get_warranties(search: str = "", status: str = "") -> list:
    conn   = get_conn()
    q      = f"%{search}%"
    where  = "WHERE (c.name LIKE ? OR CAST(w.id AS TEXT) LIKE ?)"
    params = [q, q]
    if status:
        where += " AND w.status=?"; params.append(status)
    rows = conn.execute(f"""
        SELECT w.*, c.name AS client_name
        FROM warranties w LEFT JOIN clients c ON c.id=w.client_id
        {where} ORDER BY w.id DESC
    """, params).fetchall()
    conn.close()
    return rows

def upsert_warranty(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute("""UPDATE warranties SET client_id=?,sale_id=?,install_date=?,
            warranty_months=?,expiry_date=?,status=?,notes=? WHERE id=?""",
            (data.get("client_id"), data.get("sale_id"), data.get("install_date",""),
             int(data.get("warranty_months",6)), data.get("expiry_date",""),
             data.get("status","Vigente"), data.get("notes",""), data["id"]))
        rid = data["id"]
    else:
        cur = conn.execute("""INSERT INTO warranties(client_id,sale_id,install_date,
            warranty_months,expiry_date,status,notes) VALUES(?,?,?,?,?,?,?)""",
            (data.get("client_id"), data.get("sale_id"), data.get("install_date",""),
             int(data.get("warranty_months",6)), data.get("expiry_date",""),
             data.get("status","Vigente"), data.get("notes","")))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Ventas / Facturación
# ─────────────────────────────────────────────────────────────────────────────
def get_sales(search: str = "") -> list:
    conn = get_conn()
    q    = f"%{search}%"
    rows = conn.execute("""
        SELECT s.*, c.name AS client_name
        FROM sales s LEFT JOIN clients c ON c.id=s.client_id
        WHERE c.name LIKE ? OR CAST(s.id AS TEXT) LIKE ?
        ORDER BY s.id DESC
    """, (q, q)).fetchall()
    conn.close()
    return rows

def get_billing(search: str = "") -> list:
    conn = get_conn()
    q    = f"%{search}%"
    rows = conn.execute("""
        SELECT b.*, c.name AS client_name
        FROM billing b LEFT JOIN clients c ON c.id=b.client_id
        WHERE c.name LIKE ? ORDER BY b.id DESC
    """, (q,)).fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Compras
# ─────────────────────────────────────────────────────────────────────────────
def get_purchase_batches() -> list:
    conn  = get_conn()
    rows  = conn.execute("SELECT * FROM purchase_batches ORDER BY id DESC").fetchall()
    conn.close()
    return rows

def get_purchase_batch(batch_id: int):
    conn  = get_conn()
    batch = conn.execute("SELECT * FROM purchase_batches WHERE id=?", (batch_id,)).fetchone()
    items = conn.execute(
        "SELECT pbi.*, inv.description FROM purchase_batch_items pbi "
        "LEFT JOIN inventory inv ON inv.sku=pbi.product_sku WHERE pbi.batch_id=?", (batch_id,)
    ).fetchall()
    conn.close()
    return batch, items


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard KPIs
# ─────────────────────────────────────────────────────────────────────────────
def get_dashboard_kpis() -> dict:
    conn        = get_conn()
    total_sales = conn.execute("SELECT COALESCE(SUM(total),0) FROM sales").fetchone()[0]
    low_stock   = conn.execute(
        "SELECT COUNT(*) FROM inventory WHERE is_service=0 AND stock_min>0 AND stock_current<=stock_min"
    ).fetchone()[0]
    open_ot     = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE status IN ('Pendiente','Agendada','En ejecución')"
    ).fetchone()[0]
    open_proj   = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE is_active=1 AND status NOT IN ('Cerrado','Cancelado')"
    ).fetchone()[0]
    clients     = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    products    = conn.execute("SELECT COUNT(*) FROM inventory WHERE is_service=0").fetchone()[0]
    conn.close()
    return {"total_sales": total_sales, "low_stock": low_stock,
            "open_ot": open_ot, "open_projects": open_proj,
            "clients": clients, "products": products}


# ─────────────────────────────────────────────────────────────────────────────
# Respaldo y Restauración
# ─────────────────────────────────────────────────────────────────────────────
def export_db_bytes() -> bytes:
    with open(str(DB_PATH), "rb") as f:
        return f.read()

def restore_db_from_bytes(data: bytes) -> bool:
    backup = str(DB_PATH) + ".backup"
    try:
        if DB_PATH.exists():
            shutil.copy2(str(DB_PATH), backup)
        with open(str(DB_PATH), "wb") as f:
            f.write(data)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        return True
    except Exception:
        if os.path.exists(backup):
            shutil.copy2(backup, str(DB_PATH))
        return False

def get_table_stats() -> dict:
    tables = ["clients","vendors","suppliers","inventory","kits","kit_items",
              "quotes","quote_items","sales","billing","projects","project_items",
              "work_orders","work_order_items","warranties","installations",
              "tools_assets","purchase_batches","purchase_batch_items",
              "inventory_movements","checklist_templates","checklist_template_items",
              "app_settings"]
    conn  = get_conn()
    stats = {}
    for t in tables:
        try:
            stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            stats[t] = "N/A"
    conn.close()
    return stats
