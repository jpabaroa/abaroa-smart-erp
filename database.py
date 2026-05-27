"""
database.py — Abaroa Smart ERP (definitivo)
Esquema 100% compatible con el original abaroa_smart_erp.db y todas las vistas.
"""

import sqlite3, hashlib, os, shutil, json, re
from datetime import date, datetime
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "abaroa_smart_erp.db"
BACKUP_DIR = APP_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
IVA_RATE = 0.19

# ── Conexión ──────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def q(conn, sql, params=()):
    """Ejecuta SQL con commit automático."""
    conn.execute(sql, params)
    conn.commit()

# ── Esquema ───────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, phone TEXT, email TEXT, address TEXT
);
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, email TEXT, phone TEXT, role TEXT
);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, phone TEXT, email TEXT,
    contact_person TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY, description TEXT NOT NULL,
    category TEXT, protocol TEXT, stock_initial INTEGER,
    stock_current INTEGER, cost_unit INTEGER, margin_pct INTEGER,
    sale_price INTEGER, provider TEXT, is_service INTEGER DEFAULT 0,
    stock_min INTEGER DEFAULT 0, image_path TEXT DEFAULT '',
    location TEXT DEFAULT '', stock_reserved INTEGER DEFAULT 0,
    average_landed_cost INTEGER DEFAULT 0, publish_web TEXT DEFAULT 'NO',
    description_web TEXT, source_category TEXT, source_subcategory TEXT
);
CREATE TABLE IF NOT EXISTS inventory_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL,
    movement_type TEXT NOT NULL, quantity INTEGER DEFAULT 0,
    reference_type TEXT, reference_id INTEGER,
    notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    sale_price INTEGER DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS kit_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_id INTEGER NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number TEXT NOT NULL, quote_date TEXT NOT NULL,
    client_id INTEGER, vendor_id INTEGER, validity_days INTEGER DEFAULT 10,
    status TEXT DEFAULT 'Pendiente', notes TEXT,
    subtotal_products INTEGER DEFAULT 0,
    subtotal_services_exempt INTEGER DEFAULT 0,
    vat_products INTEGER DEFAULT 0, total INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS quote_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id INTEGER NOT NULL, item_type TEXT NOT NULL,
    sku TEXT, description TEXT NOT NULL,
    quantity INTEGER DEFAULT 1, unit_price INTEGER DEFAULT 0,
    line_total INTEGER DEFAULT 0, vat_exempt INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date TEXT NOT NULL, client_id INTEGER, quote_id INTEGER,
    total INTEGER DEFAULT 0, material_cost INTEGER DEFAULT 0,
    gross_margin INTEGER DEFAULT 0, gross_margin_pct REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS billing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER, client_id INTEGER, total INTEGER DEFAULT 0,
    advance_50 INTEGER DEFAULT 0, balance_50 INTEGER DEFAULT 0,
    payment_status TEXT DEFAULT 'Pendiente'
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number TEXT NOT NULL, quotation_id INTEGER,
    client_id INTEGER, name TEXT, description TEXT,
    status TEXT DEFAULT 'Pendiente', technical_status TEXT DEFAULT 'Pendiente',
    installation_date TEXT, delivery_date TEXT,
    configuration_url TEXT, notes TEXT,
    checklist_required INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS project_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL, item_type TEXT NOT NULL,
    sku TEXT, description TEXT NOT NULL,
    quantity INTEGER DEFAULT 1, unit_cost INTEGER DEFAULT 0,
    unit_price INTEGER DEFAULT 0, total_price INTEGER DEFAULT 0,
    reserved_quantity INTEGER DEFAULT 0, used_quantity INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL, template_id INTEGER,
    status TEXT DEFAULT 'Pendiente', completed_at TEXT,
    completed_by TEXT, notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_checklist_id INTEGER NOT NULL,
    item_text TEXT NOT NULL, is_required INTEGER DEFAULT 1,
    is_checked INTEGER DEFAULT 0, checked_at TEXT,
    evidence_note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ot_number TEXT NOT NULL, client_id INTEGER, vendor_id INTEGER,
    quote_id INTEGER, status TEXT DEFAULT 'Pendiente',
    scheduled_date TEXT, address TEXT,
    hours_work REAL DEFAULT 0, labor_cost INTEGER DEFAULT 0,
    travel_cost INTEGER DEFAULT 0, extra_material_cost INTEGER DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS work_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL, sku TEXT, description TEXT,
    quantity INTEGER DEFAULT 1, cost_unit INTEGER DEFAULT 0,
    line_cost INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warranties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER, sale_id INTEGER UNIQUE,
    install_date TEXT, warranty_months INTEGER DEFAULT 6,
    expiry_date TEXT, status TEXT DEFAULT 'Vigente', notes TEXT
);
CREATE TABLE IF NOT EXISTS installations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL, install_date TEXT NOT NULL,
    sku TEXT, description TEXT NOT NULL, serial_number TEXT,
    location TEXT, notes TEXT, warranty_months INTEGER DEFAULT 12
);
CREATE TABLE IF NOT EXISTS tools_assets (
    asset_id TEXT PRIMARY KEY, tool_name TEXT NOT NULL,
    category TEXT DEFAULT 'Herramienta', provider TEXT,
    quantity INTEGER DEFAULT 1, cost_unit INTEGER DEFAULT 0,
    purchase_date TEXT DEFAULT '', useful_life_months INTEGER DEFAULT 12,
    monthly_cost INTEGER DEFAULT 0, status TEXT DEFAULT 'Activa',
    notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS purchase_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_name TEXT,
    purchase_date TEXT, shipping_cost INTEGER DEFAULT 0,
    customs_cost INTEGER DEFAULT 0, other_costs INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS purchase_batch_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL,
    product_sku TEXT NOT NULL, quantity INTEGER DEFAULT 1,
    unit_price INTEGER DEFAULT 0, landed_cost INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS supplies_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT UNIQUE NOT NULL, default_unit_price INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checklist_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    description TEXT, service_type TEXT, is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS checklist_template_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL, item_order INTEGER DEFAULT 1,
    item_text TEXT NOT NULL, is_required INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db():
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

def remove_duplicate_rows():
    conn = get_conn()
    conn.execute("DELETE FROM quotes WHERE id NOT IN (SELECT MIN(id) FROM quotes GROUP BY quote_number)")
    conn.execute("DELETE FROM kits WHERE id NOT IN (SELECT MIN(id) FROM kits GROUP BY code)")
    conn.commit()
    conn.close()

# ── Settings ──────────────────────────────────────────────────────────────────
def hash_password(plain):
    return hashlib.sha256(str(plain).encode()).hexdigest()

_DEFAULTS = {
    "admin_username":       "admin",
    "admin_password_hash":  hash_password("admin123"),
    "company_name":         "Abaroa Smart",
    "company_phone":        "+56 9 8183 8679",
    "company_email":        "contacto@abaroasmart.com",
    "vat_rate":             "19",
    "default_margin":       "30",
    "ot_prefix":            "OT",
    "project_prefix":       "PROY",
    "warranty_months":      "6",
}

def ensure_app_settings():
    conn = get_conn()
    for k, v in _DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (k, v))
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

# ── Auth ──────────────────────────────────────────────────────────────────────
def verify_admin_credentials(username, password):
    stored_user = get_setting("admin_username", "admin")
    stored_hash = get_setting("admin_password_hash", hash_password("admin123"))
    return username.strip() == stored_user.strip() and hash_password(password) == stored_hash

def admin_logged_in():
    try:
        import streamlit as st
        return bool(st.session_state.get("admin_logged_in", False))
    except Exception:
        return False

# ── Inventario ─────────────────────────────────────────────────────────────────
def calc_sale_price(cost, margin_pct):
    try:
        return round(int(cost) * (1 + int(margin_pct) / 100))
    except Exception:
        return 0

def next_sku_for_category(category, existing_skus, is_service=False):
    prefix_map = {
        "Interruptores": "PRD-INT", "Cámaras": "PRD-CAM", "Sensores": "PRD-SEN",
        "Clima": "PRD-CLI", "Configuraciones": "PRD-CFG", "Integraciones": "PRD-INT2",
        "Insumos": "INS", "Servicios": "SRV",
    }
    if is_service:
        base = "SRV"
    else:
        base = prefix_map.get(category, f"PRD-{category[:3].upper()}")
    nums = []
    for s in existing_skus:
        if str(s).startswith(base + "-"):
            try:
                nums.append(int(str(s).split("-")[-1]))
            except ValueError:
                pass
    n = max(nums) + 1 if nums else 1
    return f"{base}-{n:04d}"

def save_inventory_image(image_file, sku):
    try:
        img_dir = APP_DIR / "static" / "inventory_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(image_file.name).suffix
        dest = img_dir / f"{sku}{ext}"
        dest.write_bytes(image_file.read())
        return str(dest.relative_to(APP_DIR))
    except Exception:
        return ""

def inventory_image_web_path(image_path):
    if not image_path:
        return None
    full = APP_DIR / image_path
    return str(full) if full.exists() else None

def recalc_all_sale_prices():
    conn = get_conn()
    rows = conn.execute("SELECT sku, cost_unit, margin_pct FROM inventory WHERE is_service=0").fetchall()
    for r in rows:
        if r["cost_unit"] and r["margin_pct"]:
            conn.execute("UPDATE inventory SET sale_price=? WHERE sku=?",
                         (calc_sale_price(r["cost_unit"], r["margin_pct"]), r["sku"]))
    conn.commit()
    conn.close()

def recalc_stock():
    conn = get_conn()
    movements = conn.execute("""
        SELECT sku,
            SUM(CASE WHEN movement_type IN ('PURCHASE','ENTRADA','entrada') THEN quantity
                     WHEN movement_type IN ('SALE','SALIDA','salida','PROJECT_CONSUMPTION','RESERVE') THEN -quantity
                     ELSE 0 END) AS net
        FROM inventory_movements GROUP BY sku
    """).fetchall()
    for m in movements:
        conn.execute("UPDATE inventory SET stock_current=MAX(0,COALESCE(stock_initial,0)+?) WHERE sku=?",
                     (m["net"] or 0, m["sku"]))
    conn.commit()
    conn.close()

# ── Herramientas ───────────────────────────────────────────────────────────────
def calc_monthly_tool_cost(cost_unit, quantity, useful_life_months):
    try:
        return round(int(cost_unit) * int(quantity) / max(int(useful_life_months), 1))
    except Exception:
        return 0

def normalize_tools_df(df):
    if df is None or df.empty:
        return df
    for col in ["asset_id","tool_name","category","provider","status","notes","purchase_date"]:
        if col not in df.columns:
            df[col] = ""
    for col in ["quantity","cost_unit","useful_life_months","monthly_cost"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)
    return df

def import_tools_csv(file_obj):
    import pandas as pd
    df = pd.read_csv(file_obj)
    df.columns = [c.strip().lower() for c in df.columns]
    conn = get_conn()
    n = 0
    for _, row in df.iterrows():
        aid = str(row.get("asset_id", "")).strip()
        tname = str(row.get("tool_name", row.get("nombre", ""))).strip()
        if not aid or not tname:
            continue
        cost = int(row.get("cost_unit", row.get("costo", 0)) or 0)
        life = int(row.get("useful_life_months", row.get("vida_util", 12)) or 12)
        qty  = int(row.get("quantity", row.get("cantidad", 1)) or 1)
        monthly = calc_monthly_tool_cost(cost, qty, life)
        conn.execute("""INSERT INTO tools_assets (asset_id,tool_name,category,provider,quantity,
            cost_unit,purchase_date,useful_life_months,monthly_cost,status,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_id) DO UPDATE SET tool_name=excluded.tool_name,
            quantity=excluded.quantity, cost_unit=excluded.cost_unit,
            monthly_cost=excluded.monthly_cost""",
            (aid, tname, str(row.get("category","Herramienta") or "Herramienta"),
             str(row.get("provider","") or ""), qty, cost,
             str(row.get("purchase_date","") or ""), life, monthly,
             str(row.get("status","Activa") or "Activa"),
             str(row.get("notes","") or "")))
        n += 1
    conn.commit(); conn.close()
    return n

# ── Kits ───────────────────────────────────────────────────────────────────────
def kit_components_df(kit_id):
    return get_df("""
        SELECT ki.sku, COALESCE(i.description, ki.sku) AS description,
               ki.quantity, COALESCE(i.sale_price,0) AS sale_price,
               ki.quantity * COALESCE(i.sale_price,0) AS subtotal
        FROM kit_items ki LEFT JOIN inventory i ON i.sku=ki.sku
        WHERE ki.kit_id=? ORDER BY ki.id
    """, (kit_id,))

# ── Cotizaciones ───────────────────────────────────────────────────────────────
def save_quote(quote_number, quote_date, client_id, vendor_id, validity_days,
               status, notes, product_lines, service_lines, kit_lines, supply_lines):
    subtotal_p = sum(int(x.get("line_total",0)) for x in product_lines + kit_lines + supply_lines)
    subtotal_s = sum(int(x.get("line_total",0)) for x in service_lines)
    vat        = round(subtotal_p * IVA_RATE)
    total      = subtotal_p + subtotal_s + vat
    conn = get_conn()
    existing = conn.execute("SELECT id FROM quotes WHERE quote_number=?", (quote_number,)).fetchone()
    if existing:
        quote_id = existing["id"]
        conn.execute("""UPDATE quotes SET quote_date=?,client_id=?,vendor_id=?,validity_days=?,
            status=?,notes=?,subtotal_products=?,subtotal_services_exempt=?,vat_products=?,total=?
            WHERE id=?""",
            (quote_date, client_id, vendor_id, validity_days, status, notes,
             subtotal_p, subtotal_s, vat, total, quote_id))
        conn.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
    else:
        cur = conn.execute("""INSERT INTO quotes (quote_number,quote_date,client_id,vendor_id,
            validity_days,status,notes,subtotal_products,subtotal_services_exempt,vat_products,total)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (quote_number, quote_date, client_id, vendor_id, validity_days,
             status, notes, subtotal_p, subtotal_s, vat, total))
        quote_id = cur.lastrowid
    for item in product_lines:
        conn.execute("INSERT INTO quote_items(quote_id,item_type,sku,description,quantity,unit_price,line_total,vat_exempt) VALUES(?,?,?,?,?,?,?,?)",
                     (quote_id,"producto",item["sku"],item["description"],int(item["quantity"]),int(item["unit_price"]),int(item["line_total"]),0))
    for item in kit_lines:
        conn.execute("INSERT INTO quote_items(quote_id,item_type,sku,description,quantity,unit_price,line_total,vat_exempt) VALUES(?,?,?,?,?,?,?,?)",
                     (quote_id,"kit",item.get("code",""),item["name"],int(item["quantity"]),int(item["unit_price"]),int(item["line_total"]),0))
    for item in service_lines:
        conn.execute("INSERT INTO quote_items(quote_id,item_type,sku,description,quantity,unit_price,line_total,vat_exempt) VALUES(?,?,?,?,?,?,?,?)",
                     (quote_id,"servicio",item["sku"],item["description"],int(item["quantity"]),int(item["unit_price"]),int(item["line_total"]),1))
    for item in supply_lines:
        conn.execute("INSERT INTO quote_items(quote_id,item_type,sku,description,quantity,unit_price,line_total,vat_exempt) VALUES(?,?,?,?,?,?,?,?)",
                     (quote_id,"insumo","INSUMO",item["description"],int(item["quantity"]),int(item["unit_price"]),int(item["line_total"]),0))
    conn.commit(); conn.close()
    return quote_id, total

def validate_quote_before_save(client_row, product_lines, service_lines, kit_lines, supply_lines, products_df):
    errors = []
    if not client_row or not client_row.get("id"):
        errors.append("Selecciona un cliente válido.")
    total_items = len(product_lines) + len(service_lines) + len(kit_lines) + len(supply_lines)
    if total_items == 0:
        errors.append("Agrega al menos un ítem a la cotización.")
    return errors

def get_quote_stock_warnings(product_lines, products_df):
    warnings = []
    for line in product_lines:
        prod = products_df.loc[products_df["sku"] == line["sku"]] if not products_df.empty else []
        if len(prod) > 0:
            available = int(prod.iloc[0].get("stock_current", 0) or 0)
            if int(line["quantity"]) > available:
                warnings.append(f"Stock insuficiente para {line['description']}: disponible {available}, solicitado {int(line['quantity'])}.")
    return warnings

def load_quote_context(quote_id):
    conn = get_conn()
    header = conn.execute("""
        SELECT q.*, c.name AS client_name, c.phone AS client_phone,
               c.email AS client_email, c.address AS client_address,
               v.name AS vendor_name
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id
        LEFT JOIN vendors v ON v.id=q.vendor_id WHERE q.id=?
    """, (quote_id,)).fetchone()
    if not header:
        conn.close()
        return None
    items = conn.execute("SELECT * FROM quote_items WHERE quote_id=? ORDER BY id", (quote_id,)).fetchall()
    client_row = {"id": header["client_id"], "name": header["client_name"],
                  "phone": header["client_phone"], "email": header["client_email"],
                  "address": header["client_address"]}
    product_lines = [dict(r) for r in items if r["item_type"] == "producto"]
    service_lines = [dict(r) for r in items if r["item_type"] == "servicio"]
    kit_lines     = [dict(r) for r in items if r["item_type"] == "kit"]
    supply_lines  = [dict(r) for r in items if r["item_type"] == "insumo"]
    conn.close()
    return {"header": dict(header), "client_row": client_row,
            "vendor_name": header["vendor_name"] or "",
            "product_lines": product_lines, "service_lines": service_lines,
            "kit_lines": kit_lines, "supply_lines": supply_lines}

def duplicate_quote(quote_id):
    ctx = load_quote_context(quote_id)
    if not ctx:
        return False, "Cotización no encontrada."
    h = ctx["header"]
    new_number = f"COT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    conn = get_conn()
    cur = conn.execute("""INSERT INTO quotes(quote_number,quote_date,client_id,vendor_id,validity_days,
        status,notes,subtotal_products,subtotal_services_exempt,vat_products,total)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (new_number, date.today().isoformat(), h["client_id"], h["vendor_id"],
         h["validity_days"], "Pendiente", h.get("notes",""),
         h["subtotal_products"], h["subtotal_services_exempt"], h["vat_products"], h["total"]))
    new_id = cur.lastrowid
    items = conn.execute("SELECT * FROM quote_items WHERE quote_id=?", (quote_id,)).fetchall()
    for it in items:
        conn.execute("INSERT INTO quote_items(quote_id,item_type,sku,description,quantity,unit_price,line_total,vat_exempt) VALUES(?,?,?,?,?,?,?,?)",
                     (new_id, it["item_type"], it["sku"], it["description"],
                      it["quantity"], it["unit_price"], it["line_total"], it["vat_exempt"]))
    conn.commit(); conn.close()
    return True, f"Cotización duplicada como {new_number}."

def delete_quote(quote_id):
    conn = get_conn()
    conn.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
    conn.execute("DELETE FROM quotes WHERE id=?", (quote_id,))
    conn.commit(); conn.close()

def convert_quote_to_sale(quote_id):
    conn = get_conn()
    quote = conn.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
    if not quote:
        conn.close()
        return False, "Cotización no encontrada."
    existing = conn.execute("SELECT id FROM sales WHERE quote_id=?", (quote_id,)).fetchone()
    if existing:
        conn.close()
        return False, "Esta cotización ya tiene una venta registrada."
    items = conn.execute("SELECT * FROM quote_items WHERE quote_id=?", (quote_id,)).fetchall()
    material_cost = 0
    for it in items:
        if it["item_type"] in ("producto","insumo","kit"):
            inv = conn.execute("SELECT cost_unit FROM inventory WHERE sku=?", (it["sku"],)).fetchone()
            if inv:
                material_cost += int(it["quantity"]) * int(inv["cost_unit"] or 0)
    total = int(quote["total"] or 0)
    gross_margin = total - material_cost
    gross_margin_pct = (gross_margin / total) if total else 0
    conn.execute("""INSERT INTO sales(sale_date,client_id,quote_id,total,material_cost,gross_margin,gross_margin_pct)
        VALUES(?,?,?,?,?,?,?)""",
        (date.today().isoformat(), quote["client_id"], quote_id,
         total, material_cost, gross_margin, gross_margin_pct))
    sale_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Billing
    advance = round(total * 0.5)
    conn.execute("INSERT INTO billing(sale_id,client_id,total,advance_50,balance_50,payment_status) VALUES(?,?,?,?,?,?)",
                 (sale_id, quote["client_id"], total, advance, total - advance, "Pendiente"))
    conn.execute("UPDATE quotes SET status='Vendida' WHERE id=?", (quote_id,))
    conn.commit(); conn.close()
    return True, f"Venta registrada por ${total:,}."

# ── Proyectos ──────────────────────────────────────────────────────────────────
def project_exists_for_quote(quote_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM projects WHERE quotation_id=? LIMIT 1", (quote_id,)).fetchone()
    conn.close()
    return int(row["id"]) if row else None

def create_project_from_quote(quote_id, installation_date=None, configuration_url="", notes=""):
    conn = get_conn()
    quote = conn.execute("""
        SELECT q.*, c.name AS client_name FROM quotes q
        LEFT JOIN clients c ON c.id=q.client_id WHERE q.id=?
    """, (quote_id,)).fetchone()
    if not quote:
        conn.close()
        return False, None, "Cotización no encontrada."
    existing = conn.execute("SELECT id FROM projects WHERE quotation_id=?", (quote_id,)).fetchone()
    if existing:
        conn.close()
        return False, int(existing["id"]), "Ya existe un proyecto para esta cotización."
    pnumber = f"PROY-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    pname   = f"{quote['client_name']} · {quote['quote_number']}"
    cur = conn.execute("""INSERT INTO projects(project_number,quotation_id,client_id,name,status,
        technical_status,installation_date,configuration_url,notes,is_active)
        VALUES(?,?,?,?,?,?,?,?,?,1)""",
        (pnumber, quote_id, quote["client_id"], pname, "Pendiente",
         "Pendiente", installation_date or date.today().isoformat(),
         configuration_url, notes))
    pid = cur.lastrowid
    # Copiar items de la cotización al proyecto
    items = conn.execute("SELECT * FROM quote_items WHERE quote_id=?", (quote_id,)).fetchall()
    for it in items:
        inv = conn.execute("SELECT cost_unit FROM inventory WHERE sku=?", (it["sku"],)).fetchone()
        cost = int(inv["cost_unit"] or 0) if inv else 0
        conn.execute("""INSERT INTO project_items(project_id,item_type,sku,description,quantity,
            unit_cost,unit_price,total_price,reserved_quantity,used_quantity) VALUES(?,?,?,?,?,?,?,?,?,0)""",
            (pid, it["item_type"], it["sku"] or "", it["description"],
             int(it["quantity"]), cost, int(it["unit_price"]),
             int(it["line_total"]), int(it["quantity"])))
        if it["item_type"] in ("producto","insumo") and it["sku"] and it["sku"] not in ("","INSUMO"):
            conn.execute("""UPDATE inventory SET stock_reserved=COALESCE(stock_reserved,0)+?,
                stock_current=MAX(0,COALESCE(stock_current,0)-?) WHERE sku=?""",
                (int(it["quantity"]), int(it["quantity"]), it["sku"]))
            conn.execute("INSERT INTO inventory_movements(sku,movement_type,quantity,reference_type,reference_id,notes) VALUES(?,?,?,?,?,?)",
                         (it["sku"],"RESERVE",int(it["quantity"]),"project",pid,f"Reserva proyecto {pnumber}"))
    # Checklist por defecto desde template
    template = conn.execute("SELECT id FROM checklist_templates WHERE is_active=1 LIMIT 1").fetchone()
    if template:
        cl = conn.execute("INSERT INTO project_checklists(project_id,template_id,status) VALUES(?,?,?)",
                         (pid, template["id"], "Pendiente"))
        cl_id = cl.lastrowid
        tmpl_items = conn.execute("SELECT * FROM checklist_template_items WHERE template_id=? ORDER BY item_order",
                                   (template["id"],)).fetchall()
        for ti in tmpl_items:
            conn.execute("INSERT INTO project_checklist_items(project_checklist_id,item_text,is_required) VALUES(?,?,?)",
                         (cl_id, ti["item_text"], ti["is_required"]))
    conn.execute("UPDATE quotes SET status='Aprobada' WHERE id=?", (quote_id,))
    conn.commit(); conn.close()
    return True, pid, f"Proyecto {pnumber} creado con {len(items)} ítems."

def create_work_order_from_project(project_id, scheduled_date=None):
    conn = get_conn()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return False, None, "Proyecto no encontrado."
    existing = conn.execute("SELECT id FROM work_orders WHERE quote_id=?", (proj["quotation_id"],)).fetchone()
    if existing:
        conn.close()
        return False, int(existing["id"]), "Ya existe una OT para este proyecto."
    otn = f"OT-{datetime.now().strftime('%Y%m%d-%H%M')}"
    cur = conn.execute("""INSERT INTO work_orders(ot_number,client_id,quote_id,status,scheduled_date,notes)
        VALUES(?,?,?,?,?,?)""",
        (otn, proj["client_id"], proj["quotation_id"], "Pendiente",
         scheduled_date or date.today().isoformat(), f"OT generada desde proyecto {proj['project_number']}"))
    ot_id = cur.lastrowid
    conn.commit(); conn.close()
    return True, ot_id, f"OT {otn} creada."

def get_workflow_ot(project_id):
    conn = get_conn()
    proj = conn.execute("SELECT quotation_id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return None
    row = conn.execute("SELECT * FROM work_orders WHERE quote_id=? LIMIT 1", (proj["quotation_id"],)).fetchone()
    conn.close()
    return dict(row) if row else None

def validate_project_completion(project_id):
    conn = get_conn()
    checklist = conn.execute("""
        SELECT COUNT(*) AS total, SUM(is_checked) AS checked FROM project_checklist_items pci
        JOIN project_checklists pc ON pc.id=pci.project_checklist_id
        WHERE pc.project_id=?
    """, (project_id,)).fetchone()
    conn.close()
    total   = int(checklist["total"] or 0)
    checked = int(checklist["checked"] or 0)
    if total == 0:
        return True, "Sin checklist requerido."
    if checked < total:
        return False, f"Checklist incompleto: {checked}/{total} ítems marcados."
    return True, f"Checklist completo ({checked}/{total}). Listo para cerrar."

def sync_project_item_usage(item_id, new_used):
    conn = get_conn()
    item = conn.execute("SELECT * FROM project_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return False, "Ítem no encontrado."
    old_used = int(item["used_quantity"] or 0)
    delta    = new_used - old_used
    conn.execute("UPDATE project_items SET used_quantity=? WHERE id=?", (new_used, item_id))
    if item["sku"] and item["sku"] not in ("","INSUMO") and delta != 0:
        movement = "PROJECT_CONSUMPTION" if delta > 0 else "ENTRADA"
        conn.execute("INSERT INTO inventory_movements(sku,movement_type,quantity,reference_type,reference_id,notes) VALUES(?,?,?,?,?,?)",
                     (item["sku"], movement, abs(delta), "project", item["project_id"], f"Uso real actualizado"))
    conn.commit(); conn.close()
    return True, f"Uso actualizado a {new_used}."

def close_project_workflow(project_id):
    conn = get_conn()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return False, "Proyecto no encontrado."
    conn.execute("UPDATE projects SET status='Cerrado', technical_status='Finalizado', updated_at=CURRENT_TIMESTAMP WHERE id=?", (project_id,))
    if proj["quotation_id"]:
        conn.execute("UPDATE work_orders SET status='Cerrada' WHERE quote_id=?", (proj["quotation_id"],))
    # Liberar stock reservado no usado
    items = conn.execute("SELECT * FROM project_items WHERE project_id=?", (project_id,)).fetchall()
    for it in items:
        if it["sku"] and it["sku"] not in ("","INSUMO"):
            reserved = int(it["reserved_quantity"] or 0)
            used     = int(it["used_quantity"] or 0)
            leftover = max(reserved - used, 0)
            if leftover > 0:
                conn.execute("UPDATE inventory SET stock_reserved=MAX(0,COALESCE(stock_reserved,0)-?), stock_current=COALESCE(stock_current,0)+? WHERE sku=?",
                             (leftover, leftover, it["sku"]))
    conn.commit(); conn.close()
    return True, f"Proyecto cerrado correctamente."

# ── OT ─────────────────────────────────────────────────────────────────────────
def add_wo_item(ot_id, sku, description, quantity, cost_unit):
    conn = get_conn()
    line_cost = int(quantity) * int(cost_unit)
    conn.execute("INSERT INTO work_order_items(work_order_id,sku,description,quantity,cost_unit,line_cost) VALUES(?,?,?,?,?,?)",
                 (ot_id, sku, description, int(quantity), int(cost_unit), line_cost))
    if sku and sku not in ("","INSUMO"):
        conn.execute("UPDATE inventory SET stock_current=MAX(0,COALESCE(stock_current,0)-?) WHERE sku=?", (int(quantity), sku))
        conn.execute("INSERT INTO inventory_movements(sku,movement_type,quantity,reference_type,reference_id,notes) VALUES(?,?,?,?,?,?)",
                     (sku,"SALIDA",int(quantity),"ot",ot_id,"Usado en OT"))
    conn.commit(); conn.close()

# ── Alertas ────────────────────────────────────────────────────────────────────
def get_alerts_data():
    alerts = []
    conn   = get_conn()
    today  = date.today().isoformat()
    for r in conn.execute("SELECT sku,description,stock_current,stock_min FROM inventory WHERE is_service=0 AND stock_min>0 AND stock_current<=stock_min LIMIT 10"):
        alerts.append({"level":"warning","title":f"Stock bajo: {r['description']}","detail":f"SKU {r['sku']} · Stock: {r['stock_current']} · Mínimo: {r['stock_min']}"})
    for r in conn.execute("SELECT ot_number,scheduled_date FROM work_orders WHERE status IN ('Pendiente','Agendada','En ejecución') AND scheduled_date<? LIMIT 5", (today,)):
        alerts.append({"level":"info","title":f"OT vencida: {r['ot_number']}","detail":f"Programada: {r['scheduled_date']}"})
    for r in conn.execute("SELECT id,expiry_date FROM warranties WHERE status='Vigente' AND expiry_date<? LIMIT 5", (today,)):
        alerts.append({"level":"warning","title":f"Garantía vencida #{r['id']}","detail":f"Venció: {r['expiry_date']}"})
    conn.close()
    return alerts

# ── pandas helpers ─────────────────────────────────────────────────────────────
def get_df(sql, params=()):
    import pandas as pd
    conn = get_conn()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def get_dashboard_work_orders_df(limit=8):
    return get_df(f"""
        SELECT wo.ot_number AS 'N° OT', c.name AS 'Cliente',
               wo.status AS 'Estado', wo.scheduled_date AS 'Fecha',
               (wo.labor_cost+wo.travel_cost+wo.extra_material_cost) AS 'Costo'
        FROM work_orders wo LEFT JOIN clients c ON c.id=wo.client_id
        WHERE wo.status IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso')
        ORDER BY wo.scheduled_date ASC LIMIT {int(limit)}
    """)

# ── Buscador global ────────────────────────────────────────────────────────────
def run_global_search(term):
    import pandas as pd
    t = f"%{term}%"
    results = {}
    results["Inventario"]   = get_df("SELECT sku,description,category,stock_current,sale_price FROM inventory WHERE sku LIKE ? OR description LIKE ? OR category LIKE ?", (t,t,t))
    results["Clientes"]     = get_df("SELECT id,name,phone,email,address FROM clients WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?", (t,t,t))
    results["Cotizaciones"] = get_df("SELECT q.quote_number,c.name,q.status,q.quote_date,q.total AS monto FROM quotes q LEFT JOIN clients c ON c.id=q.client_id WHERE q.quote_number LIKE ? OR c.name LIKE ?", (t,t))
    results["OT"]           = get_df("SELECT wo.ot_number,c.name,wo.status,wo.scheduled_date,'' AS monto FROM work_orders wo LEFT JOIN clients c ON c.id=wo.client_id WHERE wo.ot_number LIKE ? OR c.name LIKE ?", (t,t))
    results["Proyectos"]    = get_df("SELECT p.project_number,c.name,p.status,p.installation_date,'' AS monto FROM projects p LEFT JOIN clients c ON c.id=p.client_id WHERE p.project_number LIKE ? OR p.name LIKE ? OR c.name LIKE ?", (t,t,t))
    results["Ventas"]       = get_df("SELECT s.id,c.name,s.sale_date,'' AS d2,s.total AS monto FROM sales s LEFT JOIN clients c ON c.id=s.client_id WHERE c.name LIKE ?", (t,))
    results["Kits"]         = get_df("SELECT code,name,sale_price,notes,'' AS monto FROM kits WHERE name LIKE ? OR code LIKE ?", (t,t))
    results["Proveedores"]  = get_df("SELECT name,phone,email,contact_person,'' AS monto FROM suppliers WHERE name LIKE ? OR email LIKE ?", (t,t))
    # Normalizar a 5 columnas
    for k, df in results.items():
        if df.empty:
            results[k] = pd.DataFrame(columns=["col1","col2","col3","col4","monto"])
        else:
            cols = list(df.columns)
            while len(cols) < 5:
                df[f"_x{len(cols)}"] = ""; cols = list(df.columns)
            df.columns = ["col1","col2","col3","col4","monto"] + list(df.columns[5:])
            results[k] = df[["col1","col2","col3","col4","monto"]]
    return results

# ── Respaldo ───────────────────────────────────────────────────────────────────
def backup_database(name="abaroa_smart"):
    if not DB_PATH.exists():
        return None
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"{name}_{ts}.db"
    shutil.copy2(str(DB_PATH), str(dst))
    return dst

def list_backups():
    return sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)

def restore_backup(filename):
    src = BACKUP_DIR / filename
    if not src.exists():
        return False, f"Respaldo {filename} no encontrado."
    try:
        backup_database("pre_restore")
        shutil.copy2(str(src), str(DB_PATH))
        return True, f"Restaurado desde {filename}."
    except Exception as e:
        return False, str(e)

def restore_from_uploaded_db(data_bytes):
    try:
        backup_database("pre_upload_restore")
        tmp = DB_PATH.with_suffix(".tmp")
        tmp.write_bytes(data_bytes)
        conn = sqlite3.connect(str(tmp))
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        shutil.move(str(tmp), str(DB_PATH))
        return True, "Base de datos restaurada correctamente."
    except Exception as e:
        if Path(str(DB_PATH.with_suffix(".tmp"))).exists():
            Path(str(DB_PATH.with_suffix(".tmp"))).unlink()
        return False, f"Error: {e}"

def export_all_data_json():
    conn   = get_conn()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    data   = {}
    for t in tables:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        data[t] = [dict(r) for r in rows]
    conn.close()
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = APP_DIR / f"export_abaroa_smart_{ts}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return out

def get_table_stats():
    conn  = get_conn()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    stats = {}
    for t in tables:
        try:
            stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            stats[t] = "N/A"
    conn.close()
    return stats

def export_db_bytes():
    with open(str(DB_PATH), "rb") as f:
        return f.read()

def restore_db_from_bytes(data):
    return restore_from_uploaded_db(data)
