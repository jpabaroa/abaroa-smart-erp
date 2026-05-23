"""
database.py — Abaroa Smart ERP
Conexión SQLite, schema, funciones CRUD y lógica de negocio.
"""

import sqlite3
import shutil
import hashlib
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
IVA_RATE = 0.19


def resolve_db_path():
    preferred = BASE_DIR / "abaroa_smart_erp.db"
    if preferred.exists():
        return preferred
    candidates = sorted(BASE_DIR.glob("abaroa_smart_erp*.db"), key=lambda p: p.name)
    return candidates[0] if candidates else preferred


DB_PATH = resolve_db_path()
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"
UPLOAD_DIR = BASE_DIR / "uploads" / "inventory"
APP_DIR = BASE_DIR

BACKUP_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── Conexión ───────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def q(conn, sql, params=(), fetch=False):
    cur = conn.cursor()
    cur.execute(sql, params)
    if fetch:
        return cur.fetchall()
    conn.commit()
    return cur


def get_df(sql, params=()):
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


# ── Helpers de columnas ────────────────────────────────────────────────────────
def ensure_column(conn, table, column, definition):
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def table_columns(table_name):
    conn = get_conn()
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    conn.close()
    return cols


def table_exists(conn, table):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


# ── Auth / Settings ───────────────────────────────────────────────────────────
def hash_password(raw):
    return hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()


def ensure_app_settings():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    defaults = {
        "admin_username": "admin",
        "admin_password_hash": hash_password("admin123"),
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def verify_admin_credentials(username, password):
    stored_user = get_setting("admin_username", "admin")
    stored_hash = get_setting("admin_password_hash", hash_password("admin123"))
    return (str(username or "").strip() == stored_user and
            hash_password(password) == stored_hash)


def admin_logged_in():
    import streamlit as st
    return st.session_state.get("admin_logged_in", False)


# ── SKU helpers ───────────────────────────────────────────────────────────────
def category_prefix(category):
    base = (category or "").strip().lower()
    mapping = {
        "interruptores": "INT", "cámara": "CAM", "camaras": "CAM", "cámaras": "CAM",
        "clima": "CLI", "ir": "IR", "sensores": "SEN", "motores": "MOT",
        "configuraciones": "CFG", "integraciones": "IGR", "mantenciones": "MNT",
        "consultorías": "CON", "consultorias": "CON", "diseño": "DIS", "diseno": "DIS",
        "auditorías": "AUD", "auditorias": "AUD", "insumos": "INS",
    }
    if base in mapping:
        return mapping[base]
    letters = "".join(ch for ch in base.upper() if ch.isalpha())
    return (letters[:3] if letters else "GEN").ljust(3, "X")


def sku_prefix_for_item(category, is_service=False):
    base = "SRV" if is_service else "PRD"
    return f"{base}-{category_prefix(category)}"


def next_sku_for_category(category, existing_skus, is_service=False):
    prefix = sku_prefix_for_item(category, is_service)
    nums = []
    for sku in existing_skus:
        if isinstance(sku, str) and sku.startswith(prefix + "-"):
            try:
                nums.append(int(sku.split("-")[-1]))
            except Exception:
                pass
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}-{nxt:04d}"


def build_category_sku_map(rows):
    counters = {}
    sku_map = {}
    for row in rows:
        prefix = sku_prefix_for_item(row["category"], bool(row["is_service"]))
        counters[prefix] = counters.get(prefix, 0) + 1
        sku_map[row["sku"]] = f"{prefix}-{counters[prefix]:04d}"
    return sku_map


# ── Imágenes inventario ───────────────────────────────────────────────────────
def inventory_image_web_path(path_value):
    path_str = str(path_value or "").strip()
    if not path_str:
        return ""
    normalized = path_str.replace("\\", "/")
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = BASE_DIR / normalized.lstrip("/\\")
    try:
        candidate = candidate.resolve()
    except Exception:
        pass
    return str(candidate) if candidate.exists() else ""


def save_inventory_image(uploaded_file, sku):
    if uploaded_file is None or not sku:
        return ""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower() or ".jpg"
    if suffix == ".jpeg":
        suffix = ".jpg"
    safe_sku = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(sku))
    target = UPLOAD_DIR / f"{safe_sku}{suffix}"
    temp_target = UPLOAD_DIR / f"{safe_sku}.__tmp__{suffix}"
    data = uploaded_file.getbuffer()
    with open(temp_target, "wb") as f:
        f.write(data)
    for old_path in UPLOAD_DIR.glob(f"{safe_sku}.*"):
        if old_path.name == temp_target.name:
            continue
        try:
            old_path.unlink()
        except Exception:
            pass
    try:
        temp_target.replace(target)
    except Exception:
        if temp_target.exists():
            try:
                temp_target.unlink()
            except Exception:
                pass
        raise
    return str(target.relative_to(BASE_DIR)).replace("\\", "/")


# ── Recálculos ────────────────────────────────────────────────────────────────
def calc_sale_price(cost_unit, margin_pct):
    return int(round(float(cost_unit) * (1 + float(margin_pct) / 100), 0))


def recalc_all_sale_prices():
    conn = get_conn()
    rows = conn.execute("SELECT sku, cost_unit, margin_pct FROM inventory").fetchall()
    for row in rows:
        sp = calc_sale_price(row["cost_unit"] or 0, row["margin_pct"] or 0)
        conn.execute("UPDATE inventory SET sale_price = ? WHERE sku = ?", (int(sp), row["sku"]))
    conn.commit()
    conn.close()


def recalc_stock():
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT sku, stock_initial, is_service FROM inventory").fetchall()
    for row in items:
        sku = row["sku"]
        if row["is_service"]:
            cur.execute("UPDATE inventory SET stock_current=0, stock_reserved=0 WHERE sku=?", (sku,))
            continue
        used = cur.execute(
            "SELECT COALESCE(SUM(used_quantity),0) FROM project_items WHERE sku=? AND item_type IN ('producto','kit_component')", (sku,)
        ).fetchone()[0]
        reserved = cur.execute(
            "SELECT COALESCE(SUM(reserved_quantity),0) FROM project_items WHERE sku=? AND item_type IN ('producto','kit_component')", (sku,)
        ).fetchone()[0]
        stock_initial = int(row["stock_initial"] or 0)
        stock_current = max(stock_initial - int(used or 0), 0)
        stock_reserved = min(max(int(reserved or 0), 0), stock_current)
        cur.execute("UPDATE inventory SET stock_current=?, stock_reserved=? WHERE sku=?", (stock_current, stock_reserved, sku))
    conn.commit()
    conn.close()


def landed_cost_per_unit(unit_price, customs, shipping, other, qty):
    qty = max(int(qty or 1), 1)
    total = int(unit_price or 0) * qty + int(customs or 0) + int(shipping or 0) + int(other or 0)
    return int(round(total / qty, 0))


# ── Normalización textos ──────────────────────────────────────────────────────
def normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())


def remove_duplicate_rows():
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute("SELECT id, name, phone, email, address FROM clients ORDER BY id").fetchall()
    seen = {}
    to_delete = []
    for r in rows:
        key = (normalize_text(r["name"]), normalize_text(r["phone"]), normalize_text(r["email"]), normalize_text(r["address"]))
        if key in seen:
            to_delete.append(r["id"])
        else:
            seen[key] = r["id"]
    for rid in to_delete:
        cur.execute("DELETE FROM clients WHERE id=?", (rid,))
    conn.commit()
    conn.close()


# ── Alertas ───────────────────────────────────────────────────────────────────
def get_alerts_data():
    alerts = []
    try:
        low_stock_df = get_df("""
            SELECT sku, description, stock_current, stock_min FROM inventory
            WHERE COALESCE(is_service,0)=0 AND COALESCE(stock_min,0)>0
              AND COALESCE(stock_current,0) <= COALESCE(stock_min,0)
            ORDER BY stock_current ASC LIMIT 8
        """)
        for _, row in low_stock_df.iterrows():
            alerts.append({"level": "warning", "title": f"Stock bajo · {row['sku']}",
                           "detail": f"{row['description']} · stock {int(row['stock_current'] or 0)} / mín {int(row['stock_min'] or 0)}"})
    except Exception:
        pass
    try:
        pq = get_df("SELECT quote_number, status FROM quotes WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Enviada') ORDER BY id DESC LIMIT 5")
        for _, row in pq.iterrows():
            alerts.append({"level": "info", "title": f"Cotización {row['quote_number']}", "detail": f"Estado: {row['status']}"})
    except Exception:
        pass
    try:
        pp = get_df("SELECT project_number, status, technical_status FROM projects WHERE COALESCE(status,'Pendiente') NOT IN ('Entregado','Cerrado') ORDER BY id DESC LIMIT 5")
        for _, row in pp.iterrows():
            alerts.append({"level": "info", "title": f"Proyecto {row['project_number']}",
                           "detail": f"Estado: {row['status']} · Técnico: {row['technical_status']}"})
    except Exception:
        pass
    return alerts[:10]


# ── Respaldo ──────────────────────────────────────────────────────────────────
def backup_database(custom_name=""):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{custom_name}_{ts}.db" if custom_name else f"abaroa_smart_erp_backup_{ts}.db"
    backup_path = BACKUP_DIR / name
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, backup_path)
        return backup_path
    return None


def list_backups():
    return sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def restore_backup(backup_name):
    backup_path = BACKUP_DIR / backup_name
    if not backup_path.exists():
        return False, "Respaldo no encontrado."
    if DB_PATH.exists():
        pre = BACKUP_DIR / f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, pre)
    shutil.copy2(backup_path, DB_PATH)
    try:
        init_db()
        remove_duplicate_rows()
        recalc_all_sale_prices()
        recalc_stock()
    except Exception:
        pass
    return True, f"Base restaurada desde {backup_name}."


def restore_from_uploaded_db(uploaded_file_bytes):
    tmp = APP_DIR / "_restore_temp.db"
    with open(tmp, "wb") as f:
        f.write(uploaded_file_bytes)
    try:
        conn = sqlite3.connect(str(tmp))
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        conn.close()
    except Exception:
        if tmp.exists():
            tmp.unlink()
        return False, "El archivo no parece ser una SQLite válida."
    if DB_PATH.exists():
        safe = BACKUP_DIR / f"pre_upload_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, safe)
    shutil.copy2(tmp, DB_PATH)
    tmp.unlink(missing_ok=True)
    try:
        init_db()
        remove_duplicate_rows()
        recalc_all_sale_prices()
        recalc_stock()
    except Exception:
        pass
    return True, "Base restaurada desde archivo cargado."


def export_all_data_json():
    import json
    conn = get_conn()
    tables = ["inventory", "clients", "vendors", "quotes", "quote_items", "sales", "billing",
              "warranties", "installations", "kits", "kit_items", "work_orders", "work_order_items",
              "inventory_movements", "projects", "project_items", "project_checklists",
              "project_checklist_items", "purchase_batches", "purchase_batch_items",
              "tools_assets", "suppliers", "supplies_catalog"]
    data = {}
    for t in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            data[t] = [dict(r) for r in rows]
        except Exception:
            data[t] = []
    conn.close()
    out = APP_DIR / f"export_abaroa_smart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ── Cotizaciones ──────────────────────────────────────────────────────────────
def save_quote(quote_number, quote_date, client_id, vendor_id, validity_days, status, notes,
               product_lines, service_lines, kit_lines, supply_lines):
    subtotal_products = int(sum(l["line_total"] for l in product_lines))
    subtotal_services = int(sum(l["line_total"] for l in service_lines))
    subtotal_kits = int(sum(l["line_total"] for l in kit_lines))
    subtotal_supplies = int(sum(l["line_total"] for l in supply_lines))
    vat_products = int(round((subtotal_products + subtotal_kits + subtotal_supplies) * IVA_RATE, 0))
    total = int(subtotal_products + subtotal_kits + subtotal_services + subtotal_supplies + vat_products)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO quotes (quote_number, quote_date, client_id, vendor_id, validity_days, status, notes,
            subtotal_products, subtotal_services_exempt, vat_products, total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (quote_number, quote_date, client_id, vendor_id, int(validity_days), status, notes,
          subtotal_products + subtotal_kits + subtotal_supplies, subtotal_services, vat_products, total))
    quote_id = cur.lastrowid
    for line in product_lines:
        cur.execute("INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt) VALUES (?, 'producto', ?, ?, ?, ?, ?, 0)",
                    (quote_id, line["sku"], line["description"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    for line in service_lines:
        cur.execute("INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt) VALUES (?, 'servicio', ?, ?, ?, ?, ?, 1)",
                    (quote_id, line["sku"], line["description"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    for line in supply_lines:
        cur.execute("INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt) VALUES (?, 'insumo', ?, ?, ?, ?, ?, 0)",
                    (quote_id, line["sku"], line["description"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    for line in kit_lines:
        cur.execute("INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt) VALUES (?, 'kit', ?, ?, ?, ?, ?, 0)",
                    (quote_id, line["code"], line["name"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    conn.commit()
    conn.close()
    recalc_stock()
    return quote_id, total


def load_quote_context(quote_id):
    header_df = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, q.status, q.notes, q.total,
               q.subtotal_products, q.subtotal_services_exempt, q.vat_products,
               c.id as client_id, c.name as client_name, c.phone, c.email, c.address,
               v.name as vendor_name
        FROM quotes q
        LEFT JOIN clients c ON c.id = q.client_id
        LEFT JOIN vendors v ON v.id = q.vendor_id
        WHERE q.id = ?
    """, (quote_id,))
    if header_df.empty:
        return None
    h = header_df.iloc[0].to_dict()
    items_df = get_df("SELECT item_type, sku, description, quantity, unit_price, line_total FROM quote_items WHERE quote_id=? ORDER BY id", (quote_id,))
    product_lines, service_lines, kit_lines, supply_lines = [], [], [], []
    for _, r in items_df.iterrows():
        item = {"sku": r["sku"], "description": r["description"], "quantity": int(r["quantity"]),
                "unit_price": int(r["unit_price"]), "line_total": int(r["line_total"])}
        if r["item_type"] == "producto":
            product_lines.append(item)
        elif r["item_type"] == "servicio":
            service_lines.append(item)
        elif r["item_type"] == "kit":
            item["name"] = r["description"]
            item["code"] = r["sku"]
            kit_lines.append(item)
        elif r["item_type"] == "insumo":
            supply_lines.append(item)
    return {"header": h,
            "client_row": {"name": h.get("client_name",""), "phone": h.get("phone",""), "email": h.get("email",""), "address": h.get("address",""), "id": h.get("client_id")},
            "vendor_name": h.get("vendor_name",""),
            "product_lines": product_lines, "service_lines": service_lines,
            "kit_lines": kit_lines, "supply_lines": supply_lines}


def duplicate_quote(quote_id):
    ctx = load_quote_context(quote_id)
    if not ctx:
        return False, "Cotización no encontrada."
    h = ctx["header"]
    new_number = f"COP-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    new_id, total_saved = save_quote(new_number, date.today().isoformat(), int(h["client_id"]),
                                     None, 10, "Borrador", h.get("notes",""),
                                     ctx["product_lines"], ctx["service_lines"],
                                     ctx["kit_lines"], ctx["supply_lines"])
    return True, f"Cotización duplicada: {new_number} (ID {new_id})"


def delete_quote(quote_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
    cur.execute("DELETE FROM quotes WHERE id=?", (quote_id,))
    conn.commit()
    conn.close()
    recalc_stock()


def validate_quote_before_save(client_row, product_lines, service_lines, kit_lines, supply_lines, products_df):
    errors = []
    if not (client_row and bool(str(client_row.get("name","") or "").strip())):
        errors.append("Debes seleccionar un cliente.")
    if not product_lines and not service_lines and not kit_lines and not supply_lines:
        errors.append("Agrega al menos un producto, kit, servicio o insumo.")
    for line in product_lines:
        sku = line.get("sku")
        if products_df.loc[products_df["sku"] == sku].empty:
            errors.append(f"No se encontró el producto {line.get('description','')}.")
    return errors


def get_quote_stock_warnings(product_lines, products_df):
    warnings = []
    for line in product_lines or []:
        sku = line.get("sku")
        qty = int(line.get("quantity", 0) or 0)
        prod = products_df.loc[products_df["sku"] == sku]
        if prod.empty:
            continue
        stock = int(prod.iloc[0]["stock_current"] or 0)
        reserved = int(prod.iloc[0]["stock_reserved"] or 0) if "stock_reserved" in prod.columns else 0
        available = max(stock - reserved, 0)
        if qty > available:
            warnings.append(f"Stock insuficiente para {line.get('description','')}: disponible {available}, solicitado {qty}.")
    return warnings


# ── Ventas ────────────────────────────────────────────────────────────────────
def convert_quote_to_sale(quote_id):
    conn = get_conn()
    cur = conn.cursor()
    quote = cur.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
    if not quote:
        conn.close()
        return False, "Cotización no encontrada."
    product_cost = cur.execute("""
        SELECT COALESCE(SUM(qi.quantity * inv.cost_unit),0)
        FROM quote_items qi LEFT JOIN inventory inv ON inv.sku=qi.sku
        WHERE qi.quote_id=? AND qi.item_type='producto'
    """, (quote_id,)).fetchone()[0]
    kit_cost = cur.execute("""
        SELECT COALESCE(SUM(qi.quantity * ki.quantity * inv.cost_unit),0)
        FROM quote_items qi JOIN kits k ON k.code=qi.sku
        JOIN kit_items ki ON ki.kit_id=k.id JOIN inventory inv ON inv.sku=ki.sku
        WHERE qi.quote_id=? AND qi.item_type='kit'
    """, (quote_id,)).fetchone()[0]
    supplies_cost = cur.execute(
        "SELECT COALESCE(SUM(qi.line_total),0) FROM quote_items qi WHERE qi.quote_id=? AND qi.item_type='insumo'", (quote_id,)
    ).fetchone()[0]
    material_cost = int(product_cost or 0) + int(kit_cost or 0) + int(supplies_cost or 0)
    total = int(quote["total"] or 0)
    gross_margin = int(round(total - material_cost, 0))
    gross_margin_pct = round((gross_margin / total), 4) if total else 0
    existing_sale = cur.execute("SELECT id FROM sales WHERE quote_id=? ORDER BY id DESC LIMIT 1", (quote_id,)).fetchone()
    if existing_sale:
        sale_id = int(existing_sale["id"])
        cur.execute("UPDATE sales SET sale_date=?, client_id=?, total=?, material_cost=?, gross_margin=?, gross_margin_pct=? WHERE id=?",
                    (date.today().isoformat(), quote["client_id"], total, material_cost, gross_margin, gross_margin_pct, sale_id))
    else:
        cur.execute("INSERT INTO sales (sale_date, client_id, quote_id, total, material_cost, gross_margin, gross_margin_pct) VALUES (?,?,?,?,?,?,?)",
                    (date.today().isoformat(), quote["client_id"], quote_id, total, material_cost, gross_margin, gross_margin_pct))
        sale_id = cur.lastrowid
    advance = int(round(total * 0.5, 0))
    balance = int(total - advance)
    existing_billing = cur.execute("SELECT id FROM billing WHERE sale_id=? ORDER BY id DESC LIMIT 1", (sale_id,)).fetchone()
    if existing_billing:
        cur.execute("UPDATE billing SET client_id=?, total=?, advance_50=?, balance_50=?, payment_status=? WHERE id=?",
                    (quote["client_id"], total, advance, balance, "Anticipo 50%", int(existing_billing["id"])))
    else:
        cur.execute("INSERT INTO billing (sale_id, client_id, total, advance_50, balance_50, payment_status) VALUES (?,?,?,?,?,'Anticipo 50%')",
                    (sale_id, quote["client_id"], total, advance, balance))
    cur.execute("UPDATE quotes SET status='Vendida' WHERE id=?", (quote_id,))
    conn.commit()
    conn.close()
    create_warranty_for_sale(sale_id, quote["client_id"])
    recalc_stock()
    return True, f"Venta #{sale_id} creada desde cotización #{quote_id}."


def create_warranty_for_sale(sale_id, client_id, install_date=None, warranty_months=6, notes="Garantía automática"):
    install_date = install_date or date.today().isoformat()
    expiry_date = (datetime.fromisoformat(install_date).date() + timedelta(days=30 * int(warranty_months))).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    exists = cur.execute("SELECT id FROM warranties WHERE sale_id=?", (sale_id,)).fetchone()
    if not exists:
        cur.execute("INSERT INTO warranties (client_id, sale_id, install_date, warranty_months, expiry_date, status, notes) VALUES (?,?,?,?,?,?,?)",
                    (client_id, sale_id, install_date, int(warranty_months), expiry_date, "Vigente", notes))
        conn.commit()
    conn.close()


# ── Kits ───────────────────────────────────────────────────────────────────────
def kit_components_df(kit_id):
    return get_df("""
        SELECT ki.sku, inv.description, ki.quantity, inv.stock_current, inv.sale_price, inv.cost_unit
        FROM kit_items ki LEFT JOIN inventory inv ON inv.sku=ki.sku
        WHERE ki.kit_id=? ORDER BY ki.id
    """, (kit_id,))


# ── Proyectos ─────────────────────────────────────────────────────────────────
def project_exists_for_quote(quote_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM projects WHERE quotation_id=? LIMIT 1", (quote_id,)).fetchone()
    conn.close()
    return int(row["id"]) if row else None


def create_project_checklist(project_id):
    conn = get_conn()
    cur = conn.cursor()
    template = cur.execute("SELECT id FROM checklist_templates WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
    if not template:
        conn.close()
        return None
    template_id = int(template["id"])
    cur.execute("INSERT INTO project_checklists (project_id, template_id, status) VALUES (?,?,'Pendiente')", (project_id, template_id))
    checklist_id = cur.lastrowid
    items = cur.execute("SELECT item_text, is_required FROM checklist_template_items WHERE template_id=? ORDER BY item_order", (template_id,)).fetchall()
    for item in items:
        cur.execute("INSERT INTO project_checklist_items (project_checklist_id, item_text, is_required) VALUES (?,?,?)",
                    (checklist_id, item["item_text"], int(item["is_required"] or 0)))
    conn.commit()
    conn.close()
    return checklist_id


def reserve_inventory_for_project(project_id):
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT * FROM project_items WHERE project_id=?", (project_id,)).fetchall()
    for item in items:
        if item["item_type"] not in ("producto", "kit_component"):
            continue
        sku = item["sku"]
        qty = int(item["quantity"] or 0)
        inv = cur.execute("SELECT stock_current, stock_reserved FROM inventory WHERE sku=?", (sku,)).fetchone()
        if not inv:
            continue
        available = max(int(inv["stock_current"] or 0) - int(inv["stock_reserved"] or 0), 0)
        reserve_qty = min(qty, available)
        if reserve_qty <= 0:
            continue
        cur.execute("UPDATE inventory SET stock_reserved=COALESCE(stock_reserved,0)+? WHERE sku=?", (reserve_qty, sku))
        cur.execute("UPDATE project_items SET reserved_quantity=COALESCE(reserved_quantity,0)+? WHERE id=?", (reserve_qty, item["id"]))
        cur.execute("INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?,'RESERVE',?,'project',?,?)",
                    (sku, reserve_qty, project_id, f"Reserva por proyecto #{project_id}"))
    conn.commit()
    conn.close()


def release_reserved_stock_for_project(project_id):
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT id, sku, reserved_quantity FROM project_items WHERE project_id=?", (project_id,)).fetchall()
    for item in items:
        qty = int(item["reserved_quantity"] or 0)
        if not item["sku"] or qty <= 0:
            continue
        cur.execute("UPDATE inventory SET stock_reserved=MAX(COALESCE(stock_reserved,0)-?,0) WHERE sku=?", (qty, item["sku"]))
        cur.execute("UPDATE project_items SET reserved_quantity=0 WHERE id=?", (item["id"],))
        cur.execute("INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?,'RELEASE_RESERVE',?,'project',?,?)",
                    (item["sku"], qty, project_id, f"Liberación reserva proyecto #{project_id}"))
    conn.commit()
    conn.close()


def consume_inventory_for_project(project_id):
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT id, sku, quantity, reserved_quantity, used_quantity FROM project_items WHERE project_id=?", (project_id,)).fetchall()
    for item in items:
        sku = item["sku"]
        if not sku:
            continue
        target_qty = int(item["quantity"] or 0)
        already_used = int(item["used_quantity"] or 0)
        consume_qty = max(target_qty - already_used, 0)
        if consume_qty <= 0:
            continue
        inv = cur.execute("SELECT stock_current, stock_reserved FROM inventory WHERE sku=?", (sku,)).fetchone()
        if not inv:
            continue
        consume_qty = min(consume_qty, int(inv["stock_current"] or 0))
        release_qty = min(consume_qty, int(inv["stock_reserved"] or 0))
        cur.execute("UPDATE inventory SET stock_current=MAX(COALESCE(stock_current,0)-?,0), stock_reserved=MAX(COALESCE(stock_reserved,0)-?,0) WHERE sku=?",
                    (consume_qty, release_qty, sku))
        cur.execute("UPDATE project_items SET used_quantity=COALESCE(used_quantity,0)+?, reserved_quantity=MAX(COALESCE(reserved_quantity,0)-?,0) WHERE id=?",
                    (consume_qty, release_qty, item["id"]))
        cur.execute("INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?,'PROJECT_CONSUMPTION',?,'project',?,?)",
                    (sku, consume_qty, project_id, f"Consumo real proyecto #{project_id}"))
    conn.commit()
    conn.close()


def sync_project_item_usage(item_id, new_used_quantity):
    conn = get_conn()
    cur = conn.cursor()
    item = cur.execute("SELECT id, project_id, sku, quantity, reserved_quantity, used_quantity, item_type FROM project_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return False, "Ítem no encontrado."
    if item["item_type"] not in ("producto", "kit_component", "insumo"):
        cur.execute("UPDATE project_items SET used_quantity=? WHERE id=?", (max(new_used_quantity, 0), item_id))
        conn.commit()
        conn.close()
        return True, "Uso actualizado."
    target_qty = max(0, min(int(new_used_quantity or 0), int(item["quantity"] or 0)))
    current_used = int(item["used_quantity"] or 0)
    delta = target_qty - current_used
    if delta == 0:
        conn.close()
        return True, "Sin cambios."
    sku = item["sku"]
    inv = cur.execute("SELECT stock_current, stock_reserved FROM inventory WHERE sku=?", (sku,)).fetchone() if sku else None
    if not inv:
        cur.execute("UPDATE project_items SET used_quantity=? WHERE id=?", (target_qty, item_id))
        conn.commit()
        conn.close()
        return True, "Uso actualizado sin impacto de inventario."
    stock_current = int(inv["stock_current"] or 0)
    stock_reserved = int(inv["stock_reserved"] or 0)
    if delta > 0:
        consume_qty = min(delta, stock_current)
        release_qty = min(consume_qty, stock_reserved, max(int(item["reserved_quantity"] or 0), 0))
        cur.execute("UPDATE inventory SET stock_current=MAX(COALESCE(stock_current,0)-?,0), stock_reserved=MAX(COALESCE(stock_reserved,0)-?,0) WHERE sku=?",
                    (consume_qty, release_qty, sku))
        cur.execute("UPDATE project_items SET used_quantity=COALESCE(used_quantity,0)+?, reserved_quantity=MAX(COALESCE(reserved_quantity,0)-?,0) WHERE id=?",
                    (consume_qty, release_qty, item_id))
        cur.execute("INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?,'PROJECT_CONSUMPTION',?,'project',?,?)",
                    (sku, consume_qty, item["project_id"], f"Consumo manual proyecto #{item['project_id']}"))
    else:
        restore_qty = abs(delta)
        cur.execute("UPDATE inventory SET stock_current=COALESCE(stock_current,0)+?, stock_reserved=COALESCE(stock_reserved,0)+? WHERE sku=?",
                    (restore_qty, restore_qty, sku))
        cur.execute("UPDATE project_items SET used_quantity=MAX(COALESCE(used_quantity,0)-?,0), reserved_quantity=COALESCE(reserved_quantity,0)+? WHERE id=?",
                    (restore_qty, restore_qty, item_id))
        cur.execute("INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?,'USAGE_ADJUSTMENT',?,'project',?,?)",
                    (sku, restore_qty, item["project_id"], f"Ajuste manual proyecto #{item['project_id']}"))
    conn.commit()
    conn.close()
    return True, "Uso actualizado correctamente."


def validate_project_completion(project_id):
    conn = get_conn()
    checklist = conn.execute("SELECT id FROM project_checklists WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    if not checklist:
        conn.close()
        return False, "Proyecto sin checklist."
    pending = conn.execute(
        "SELECT COUNT(*) AS c FROM project_checklist_items WHERE project_checklist_id=? AND is_required=1 AND COALESCE(is_checked,0)=0",
        (int(checklist["id"]),)
    ).fetchone()
    conn.close()
    return (False, "Checklist incompleto.") if int(pending["c"] or 0) > 0 else (True, "Checklist completo.")


def create_project_from_quote(quote_id, installation_date=None, configuration_url="", notes=""):
    existing = project_exists_for_quote(quote_id)
    if existing:
        return False, existing, "La cotización ya tiene un proyecto asociado."
    conn = get_conn()
    cur = conn.cursor()
    quote = cur.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
    if not quote:
        conn.close()
        return False, None, "No se encontró la cotización."
    client = cur.execute("SELECT * FROM clients WHERE id=?", (quote["client_id"],)).fetchone()
    quote_items = cur.execute("SELECT * FROM quote_items WHERE quote_id=? ORDER BY id", (quote_id,)).fetchall()
    project_number = f"PROY-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    project_name = f"{client['name'] if client else 'Cliente'} · {quote['quote_number']}"
    cur.execute("""
        INSERT INTO projects (project_number, quotation_id, client_id, name, description, status, technical_status,
            installation_date, configuration_url, notes, checklist_required, updated_at)
        VALUES (?,?,?,?,?,'Aprobado','Pendiente',?,?,?,1,CURRENT_TIMESTAMP)
    """, (project_number, quote_id, quote["client_id"], project_name,
          f"Proyecto desde cotización {quote['quote_number']}", installation_date, configuration_url, notes))
    project_id = cur.lastrowid
    for item in quote_items:
        item_type = item["item_type"]
        if item_type == "kit":
            comps = cur.execute("""
                SELECT ki.sku, ki.quantity, i.description, i.cost_unit FROM kit_items ki
                LEFT JOIN inventory i ON i.sku=ki.sku
                WHERE ki.kit_id=(SELECT id FROM kits WHERE code=? LIMIT 1)
            """, (item["sku"],)).fetchall()
            for comp in comps:
                qty = int(item["quantity"] or 0) * int(comp["quantity"] or 0)
                cur.execute("INSERT INTO project_items (project_id, item_type, sku, description, quantity, unit_cost, unit_price, total_price) VALUES (?,'kit_component',?,?,?,?,0,0)",
                            (project_id, comp["sku"], comp["description"] or comp["sku"], qty, int(comp["cost_unit"] or 0)))
        else:
            inv = cur.execute("SELECT cost_unit FROM inventory WHERE sku=?", (item["sku"],)).fetchone()
            unit_cost = int(inv["cost_unit"] or 0) if inv else 0
            cur.execute("INSERT INTO project_items (project_id, item_type, sku, description, quantity, unit_cost, unit_price, total_price) VALUES (?,?,?,?,?,?,?,?)",
                        (project_id, item_type, item["sku"], item["description"], int(item["quantity"] or 0), unit_cost, int(item["unit_price"] or 0), int(item["line_total"] or 0)))
    cur.execute("UPDATE quotes SET status='Aprobada' WHERE id=?", (quote_id,))
    conn.commit()
    conn.close()
    create_project_checklist(project_id)
    reserve_inventory_for_project(project_id)
    return True, project_id, f"Proyecto #{project_id} creado desde la cotización."


# ── OT ────────────────────────────────────────────────────────────────────────
def create_work_order_from_project(project_id, scheduled_date=None):
    conn = get_conn()
    cur = conn.cursor()
    project = cur.execute("""
        SELECT p.*, c.address AS client_address FROM projects p
        LEFT JOIN clients c ON c.id=p.client_id WHERE p.id=?
    """, (project_id,)).fetchone()
    if not project:
        conn.close()
        return False, None, "Proyecto no encontrado."
    existing = cur.execute("SELECT id, ot_number FROM work_orders WHERE quote_id=? AND client_id=? ORDER BY id DESC LIMIT 1",
                           (project["quotation_id"], project["client_id"])).fetchone()
    if existing:
        conn.close()
        return True, int(existing["id"]), f"OT existente {existing['ot_number']}."
    ot_number = f"OT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    cur.execute("""
        INSERT INTO work_orders (ot_number, client_id, vendor_id, quote_id, status, scheduled_date, address,
            hours_work, labor_cost, travel_cost, extra_material_cost, notes)
        VALUES (?,?,?,?,'Pendiente',?,?,0,0,0,0,?)
    """, (ot_number, project["client_id"], None, project["quotation_id"],
          scheduled_date or project["installation_date"] or date.today().isoformat(),
          project["client_address"] or "", f"OT generada desde proyecto {project['project_number']}"))
    ot_id = cur.lastrowid
    conn.commit()
    conn.close()
    return True, ot_id, f"OT {ot_number} creada correctamente."


def add_wo_item(work_order_id, sku, description, quantity, cost_unit):
    conn = get_conn()
    line_cost = int(quantity) * int(cost_unit)
    q(conn, "INSERT INTO work_order_items (work_order_id, sku, description, quantity, cost_unit, line_cost) VALUES (?,?,?,?,?,?)",
      (work_order_id, sku, description, int(quantity), int(cost_unit), int(line_cost)))
    conn.close()


def get_workflow_ot(project_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT wo.* FROM work_orders wo
        JOIN projects p ON p.quotation_id=wo.quote_id AND p.client_id=wo.client_id
        WHERE p.id=? ORDER BY wo.id DESC LIMIT 1
    """, (project_id,)).fetchone()
    conn.close()
    return row


def close_project_workflow(project_id):
    ok, msg = validate_project_completion(project_id)
    if not ok:
        return False, msg
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE projects SET status='Entregado', technical_status='Cerrado', delivery_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (date.today().isoformat(), project_id))
    cur.execute("""
        UPDATE work_orders SET status='Cerrada'
        WHERE quote_id=(SELECT quotation_id FROM projects WHERE id=?)
          AND client_id=(SELECT client_id FROM projects WHERE id=?)
          AND COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso')
    """, (project_id, project_id))
    conn.commit()
    conn.close()
    recalc_stock()
    return True, "Proyecto, acta y OT cerrados correctamente."


# ── Herramientas ──────────────────────────────────────────────────────────────
def calc_monthly_tool_cost(cost_unit, quantity, useful_life_months):
    qty = max(int(quantity or 0), 1)
    life = max(int(useful_life_months or 0), 1)
    return int(round(int(cost_unit or 0) * qty / life, 0))


def normalize_tools_df(df):
    df = df.copy()
    rename_map = {"producto": "tool_name", "proveedor": "provider", "cantidad": "quantity",
                  "costo_unitario": "cost_unit", "categoria": "category", "nombre": "tool_name"}
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    if "asset_id" not in df.columns:
        df["asset_id"] = [f"TL-{i+1:04d}" for i in range(len(df.index))]
    defaults = {"tool_name": "", "category": "Herramienta", "provider": "", "quantity": 1,
                "cost_unit": 0, "purchase_date": "", "useful_life_months": 12, "monthly_cost": 0, "status": "Activa", "notes": ""}
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    for col in ["quantity", "cost_unit", "useful_life_months", "monthly_cost"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["quantity"] = df["quantity"].clip(lower=1)
    df["useful_life_months"] = df["useful_life_months"].clip(lower=1)
    if (df["monthly_cost"] == 0).any():
        mask = df["monthly_cost"] == 0
        df.loc[mask, "monthly_cost"] = ((df.loc[mask, "cost_unit"] * df.loc[mask, "quantity"]) / df.loc[mask, "useful_life_months"]).round().astype(int)
    ordered = ["asset_id","tool_name","category","provider","quantity","cost_unit","purchase_date","useful_life_months","monthly_cost","status","notes"]
    return df[[c for c in ordered if c in df.columns]]


def import_tools_csv(uploaded_file):
    df = normalize_tools_df(pd.read_csv(uploaded_file))
    conn = get_conn()
    cur = conn.cursor()
    inserted = 0
    for _, row in df.iterrows():
        asset_id = str(row.get("asset_id", "") or "").strip()
        tool_name = str(row.get("tool_name", "") or "").strip()
        if not asset_id or not tool_name:
            continue
        monthly_cost = calc_monthly_tool_cost(row.get("cost_unit", 0), row.get("quantity", 1), row.get("useful_life_months", 12))
        cur.execute("""
            INSERT INTO tools_assets (asset_id, tool_name, category, provider, quantity, cost_unit,
                purchase_date, useful_life_months, monthly_cost, status, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_id) DO UPDATE SET tool_name=excluded.tool_name, category=excluded.category,
                provider=excluded.provider, quantity=excluded.quantity, cost_unit=excluded.cost_unit,
                purchase_date=excluded.purchase_date, useful_life_months=excluded.useful_life_months,
                monthly_cost=excluded.monthly_cost, status=excluded.status, notes=excluded.notes
        """, (asset_id, tool_name, str(row.get("category","Herramienta") or "Herramienta").strip(),
              str(row.get("provider","") or "").strip(), int(row.get("quantity",1) or 1),
              int(row.get("cost_unit",0) or 0), str(row.get("purchase_date","") or "").strip(),
              int(row.get("useful_life_months",12) or 12), monthly_cost,
              str(row.get("status","Activa") or "Activa").strip(), str(row.get("notes","") or "").strip()))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


# ── Búsqueda global ───────────────────────────────────────────────────────────
def search_like_clause(columns):
    return " OR ".join([f"COALESCE(CAST({col} AS TEXT),'') LIKE ?" for col in columns])


def run_global_search(term):
    needle = f"%{str(term or '').strip()}%"
    results = {}
    conn = get_conn()
    specs = {
        "Inventario": (f"SELECT sku AS codigo, description AS titulo, category AS detalle_1, provider AS detalle_2, sale_price AS monto FROM inventory WHERE {search_like_clause(['sku','description','category','provider','protocol','location'])} ORDER BY category, sku LIMIT 200", [needle]*6),
        "Clientes": (f"SELECT CAST(id AS TEXT) AS codigo, name AS titulo, phone AS detalle_1, email AS detalle_2, NULL AS monto FROM clients WHERE {search_like_clause(['id','name','phone','email','address'])} ORDER BY id DESC LIMIT 200", [needle]*5),
        "Cotizaciones": (f"SELECT quote_number AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, q.status AS detalle_1, q.quote_date AS detalle_2, q.total AS monto FROM quotes q LEFT JOIN clients c ON c.id=q.client_id WHERE {search_like_clause(['q.quote_number','q.status','q.quote_date','q.notes','c.name'])} ORDER BY q.id DESC LIMIT 200", [needle]*5),
        "OT": (f"SELECT ot_number AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, w.status AS detalle_1, w.scheduled_date AS detalle_2, (COALESCE(w.labor_cost,0)+COALESCE(w.travel_cost,0)+COALESCE(w.extra_material_cost,0)) AS monto FROM work_orders w LEFT JOIN clients c ON c.id=w.client_id WHERE {search_like_clause(['w.ot_number','w.status','w.scheduled_date','w.address','w.notes','c.name'])} ORDER BY w.id DESC LIMIT 200", [needle]*6),
        "Proyectos": (f"SELECT project_number AS codigo, COALESCE(name,'Sin nombre') AS titulo, status AS detalle_1, technical_status AS detalle_2, NULL AS monto FROM projects WHERE {search_like_clause(['project_number','name','description','status','technical_status','configuration_url','notes'])} ORDER BY id DESC LIMIT 200", [needle]*7),
        "Ventas": (f"SELECT CAST(s.id AS TEXT) AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, s.sale_date AS detalle_1, printf('Margen %.1f%%', COALESCE(s.gross_margin_pct,0)*100.0) AS detalle_2, s.total AS monto FROM sales s LEFT JOIN clients c ON c.id=s.client_id WHERE {search_like_clause(['s.id','s.sale_date','c.name'])} ORDER BY s.id DESC LIMIT 200", [needle]*3),
        "Kits": (f"SELECT code AS codigo, name AS titulo, notes AS detalle_1, NULL AS detalle_2, sale_price AS monto FROM kits WHERE {search_like_clause(['code','name','notes'])} ORDER BY code LIMIT 200", [needle]*3),
        "Proveedores": (f"SELECT CAST(id AS TEXT) AS codigo, name AS titulo, phone AS detalle_1, email AS detalle_2, NULL AS monto FROM suppliers WHERE {search_like_clause(['id','name','phone','email','contact_person','notes'])} ORDER BY id DESC LIMIT 200", [needle]*6),
    }
    try:
        for name, (sql, params) in specs.items():
            try:
                results[name] = pd.read_sql_query(sql, conn, params=params)
            except Exception:
                results[name] = pd.DataFrame(columns=["codigo","titulo","detalle_1","detalle_2","monto"])
    finally:
        conn.close()
    return results


# ── Dashboard helpers ─────────────────────────────────────────────────────────
def get_dashboard_work_orders_df(limit=8):
    cols = set(table_columns("work_orders"))
    if "estimated_material_cost" in cols:
        sql = "SELECT ot_number AS OT, status AS Estado, scheduled_date AS Fecha, estimated_material_cost AS 'Costo estimado' FROM work_orders WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso') ORDER BY id DESC LIMIT ?"
    else:
        cost_parts = [f"COALESCE({c},0)" for c in ["labor_cost","travel_cost","extra_material_cost"] if c in cols]
        cost_expr = "+".join(cost_parts) if cost_parts else "0"
        sql = f"SELECT ot_number AS OT, status AS Estado, scheduled_date AS Fecha, ({cost_expr}) AS 'Costo estimado' FROM work_orders WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso') ORDER BY id DESC LIMIT ?"
    return get_df(sql, (limit,))


# ── Init DB ───────────────────────────────────────────────────────────────────
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS inventory (
        sku TEXT PRIMARY KEY, description TEXT NOT NULL, category TEXT, protocol TEXT,
        stock_initial INTEGER, stock_current INTEGER, cost_unit INTEGER, margin_pct INTEGER,
        sale_price INTEGER, provider TEXT, is_service INTEGER DEFAULT 0, stock_min INTEGER DEFAULT 0,
        image_path TEXT DEFAULT '', location TEXT DEFAULT '',
        stock_reserved INTEGER DEFAULT 0, average_landed_cost INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        phone TEXT, email TEXT, address TEXT, rut TEXT, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        email TEXT, phone TEXT, role TEXT
    );
    CREATE TABLE IF NOT EXISTS supplies_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT UNIQUE NOT NULL, default_unit_price INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
        phone TEXT, email TEXT, contact_person TEXT, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, quote_number TEXT NOT NULL,
        quote_date TEXT NOT NULL, client_id INTEGER, vendor_id INTEGER,
        validity_days INTEGER DEFAULT 10, status TEXT DEFAULT 'Borrador', notes TEXT,
        subtotal_products INTEGER DEFAULT 0, subtotal_services_exempt INTEGER DEFAULT 0,
        vat_products INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
        sent_date TEXT, approved_date TEXT
    );
    CREATE TABLE IF NOT EXISTS quote_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL,
        item_type TEXT NOT NULL, sku TEXT, description TEXT NOT NULL,
        quantity INTEGER DEFAULT 1, unit_price INTEGER DEFAULT 0,
        line_total INTEGER DEFAULT 0, vat_exempt INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sale_date TEXT NOT NULL,
        client_id INTEGER, quote_id INTEGER, total INTEGER DEFAULT 0,
        material_cost INTEGER DEFAULT 0, gross_margin INTEGER DEFAULT 0,
        gross_margin_pct REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS billing (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER, client_id INTEGER,
        total INTEGER DEFAULT 0, advance_50 INTEGER DEFAULT 0, balance_50 INTEGER DEFAULT 0,
        payment_status TEXT DEFAULT 'Pendiente'
    );
    CREATE TABLE IF NOT EXISTS warranties (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER,
        sale_id INTEGER UNIQUE, install_date TEXT, warranty_months INTEGER DEFAULT 6,
        expiry_date TEXT, status TEXT DEFAULT 'Vigente', notes TEXT
    );
    CREATE TABLE IF NOT EXISTS installations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL,
        install_date TEXT NOT NULL, sku TEXT, description TEXT NOT NULL,
        serial_number TEXT, location TEXT, notes TEXT, warranty_months INTEGER DEFAULT 12
    );
    CREATE TABLE IF NOT EXISTS kits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, sale_price INTEGER DEFAULT 0, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS kit_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kit_id INTEGER NOT NULL,
        sku TEXT NOT NULL, quantity INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ot_number TEXT NOT NULL,
        client_id INTEGER, vendor_id INTEGER, quote_id INTEGER,
        status TEXT DEFAULT 'Pendiente', scheduled_date TEXT, address TEXT,
        hours_work REAL DEFAULT 0, labor_cost INTEGER DEFAULT 0,
        travel_cost INTEGER DEFAULT 0, extra_material_cost INTEGER DEFAULT 0, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS work_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id INTEGER NOT NULL,
        sku TEXT, description TEXT, quantity INTEGER DEFAULT 1,
        cost_unit INTEGER DEFAULT 0, line_cost INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS inventory_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL,
        movement_type TEXT NOT NULL, quantity INTEGER DEFAULT 0,
        reference_type TEXT, reference_id INTEGER, notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_number TEXT NOT NULL,
        quotation_id INTEGER, client_id INTEGER, name TEXT, description TEXT,
        status TEXT DEFAULT 'Pendiente', technical_status TEXT DEFAULT 'Pendiente',
        installation_date TEXT, delivery_date TEXT, configuration_url TEXT, notes TEXT,
        checklist_required INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS project_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        item_type TEXT NOT NULL, sku TEXT, description TEXT NOT NULL,
        quantity INTEGER DEFAULT 1, unit_cost INTEGER DEFAULT 0,
        unit_price INTEGER DEFAULT 0, total_price INTEGER DEFAULT 0,
        reserved_quantity INTEGER DEFAULT 0, used_quantity INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS checklist_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        description TEXT, service_type TEXT, is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS checklist_template_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, template_id INTEGER NOT NULL,
        item_order INTEGER DEFAULT 1, item_text TEXT NOT NULL,
        is_required INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS project_checklists (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        template_id INTEGER, status TEXT DEFAULT 'Pendiente',
        completed_at TEXT, completed_by TEXT, notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS project_checklist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_checklist_id INTEGER NOT NULL,
        item_text TEXT NOT NULL, is_required INTEGER DEFAULT 1,
        is_checked INTEGER DEFAULT 0, checked_at TEXT, evidence_note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS purchase_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_name TEXT, purchase_date TEXT,
        shipping_cost INTEGER DEFAULT 0, customs_cost INTEGER DEFAULT 0,
        other_costs INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS purchase_batch_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL,
        product_sku TEXT NOT NULL, quantity INTEGER DEFAULT 1,
        unit_price INTEGER DEFAULT 0, landed_cost INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS tools_assets (
        asset_id TEXT PRIMARY KEY, tool_name TEXT NOT NULL,
        category TEXT DEFAULT 'Herramienta', provider TEXT,
        quantity INTEGER DEFAULT 1, cost_unit INTEGER DEFAULT 0,
        purchase_date TEXT DEFAULT '', useful_life_months INTEGER DEFAULT 12,
        monthly_cost INTEGER DEFAULT 0, status TEXT DEFAULT 'Activa',
        notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_name_unique ON suppliers(name);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_supplies_desc_unique ON supplies_catalog(description);
    """)
    conn.commit()

    ensure_column(conn, "inventory", "stock_reserved", "INTEGER DEFAULT 0")
    ensure_column(conn, "inventory", "average_landed_cost", "INTEGER DEFAULT 0")
    ensure_column(conn, "clients", "rut", "TEXT")
    ensure_column(conn, "clients", "notes", "TEXT")
    ensure_column(conn, "quotes", "sent_date", "TEXT")
    ensure_column(conn, "quotes", "approved_date", "TEXT")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM checklist_templates")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO checklist_templates (name, description, service_type) VALUES (?,?,?)",
                    ("Entrega Domótica Abaroa Smart", "Checklist base para cierre y entrega profesional.", "domotica"))
        tid = cur.lastrowid
        for idx, item in enumerate([
            "¿Se verificó la carga de los automáticos (RIC)?",
            "¿Los dispositivos Zigbee tienen señal estable?",
            "¿El cliente tiene la app configurada en su móvil?",
            "¿Se probó encendido y apagado manual y desde la app?",
            "¿Se dejó respaldo o enlace de configuración del sistema?",
            "¿Se explicó operación básica y garantía al cliente?"
        ], start=1):
            cur.execute("INSERT INTO checklist_template_items (template_id, item_order, item_text, is_required) VALUES (?,?,?,1)", (tid, idx, item))

    cur.execute("SELECT COUNT(*) FROM vendors")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO vendors (name, email, phone, role) VALUES ('Abaroa Smart','','','Ventas')")

    cur.execute("SELECT COUNT(*) FROM app_settings WHERE key='admin_username'")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT OR IGNORE INTO app_settings (key,value) VALUES ('admin_username','admin')")
        cur.execute("INSERT OR IGNORE INTO app_settings (key,value) VALUES ('admin_password_hash',?)", (hash_password("admin123"),))

    conn.commit()
    conn.close()
