
import sqlite3
import shutil
import json
import hashlib
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from io import BytesIO

APP_TITLE = "Abaroa Smart ERP"
BASE_DIR = Path(__file__).resolve().parent

def resolve_db_path():
    preferred = BASE_DIR / "abaroa_smart_erp.db"
    if preferred.exists():
        return preferred
    candidates = sorted(BASE_DIR.glob("abaroa_smart_erp*.db"), key=lambda p: p.name)
    return candidates[0] if candidates else preferred

def first_existing(*paths):
    for path in paths:
        if path.exists():
            return path
    return paths[0]

DB_PATH = resolve_db_path()
LOGO_PATH = first_existing(BASE_DIR / "logo-abaroasmart.svg", BASE_DIR / "logo-azul-abaroasmart.svg", BASE_DIR / "logo-azul-abaroasmart(2).svg")
LOGO_CROP_PATH = first_existing(BASE_DIR / "logo-abaroasmart-crop.png", BASE_DIR / "logo-abaroasmart.png")
LOGO_PNG_PATH = first_existing(BASE_DIR / "logo-abaroasmart.png", BASE_DIR / "logo-abaroasmart-crop.png")
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"
UPLOAD_DIR = BASE_DIR / "uploads" / "inventory"
IVA_RATE = 0.19
SEED_INVENTORY = []


BACKUP_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="💡")

def money(x):
    try:
        return "$ " + format(int(round(float(x))), ",").replace(",", ".")
    except Exception:
        return "$ 0"


def category_prefix(category):
    base = (category or "").strip().lower()
    mapping = {
        "interruptores": "INT",
        "cámara": "CAM",
        "camaras": "CAM",
        "cámaras": "CAM",
        "clima": "CLI",
        "ir": "IR",
        "sensores": "SEN",
        "motores": "MOT",
        "configuraciones": "CFG",
        "integraciones": "IGR",
        "mantenciones": "MNT",
        "consultorías": "CON",
        "consultorias": "CON",
        "diseño": "DIS",
        "diseno": "DIS",
        "auditorías": "AUD",
        "auditorias": "AUD",
        "insumos": "INS",
    }
    if base in mapping:
        return mapping[base]
    letters = "".join(ch for ch in base.upper() if ch.isalpha())
    return (letters[:3] if letters else "GEN").ljust(3, "X")

def build_category_sku_map(rows):
    counters = {}
    sku_map = {}
    for row in rows:
        prefix = sku_prefix_for_item(row["category"], bool(row["is_service"]))
        counters[prefix] = counters.get(prefix, 0) + 1
        sku_map[row["sku"]] = f"{prefix}-{counters[prefix]:04d}"
    return sku_map

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

def migrate_inventory_skus():
    conn = get_conn()
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(inventory)").fetchall()]
    has_image = "image_path" in cols
    has_location = "location" in cols
    has_reserved = "stock_reserved" in cols
    has_avg_landed = "average_landed_cost" in cols

    rows = cur.execute("SELECT * FROM inventory ORDER BY category, description, sku").fetchall()
    if not rows:
        conn.close()
        return

    sku_map = build_category_sku_map(rows)
    changed = any(old != new for old, new in sku_map.items())
    if not changed:
        conn.close()
        return

    cur.execute("DROP TABLE IF EXISTS inventory_tmp")
    cur.execute("""
        CREATE TABLE inventory_tmp (
            sku TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            category TEXT,
            protocol TEXT,
            stock_initial INTEGER,
            stock_current INTEGER,
            cost_unit INTEGER,
            margin_pct INTEGER,
            sale_price INTEGER,
            provider TEXT,
            is_service INTEGER DEFAULT 0,
            stock_min INTEGER DEFAULT 0,
            image_path TEXT DEFAULT '',
            location TEXT DEFAULT '',
            stock_reserved INTEGER DEFAULT 0,
            average_landed_cost INTEGER DEFAULT 0
        )
    """)

    for row in rows:
        new_sku = sku_map[row["sku"]]
        cur.execute("""
            INSERT INTO inventory_tmp (
                sku, description, category, protocol, stock_initial, stock_current,
                cost_unit, margin_pct, sale_price, provider, is_service, stock_min,
                image_path, location, stock_reserved, average_landed_cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_sku,
            row["description"],
            row["category"],
            row["protocol"],
            row["stock_initial"],
            row["stock_current"],
            row["cost_unit"],
            row["margin_pct"],
            row["sale_price"],
            row["provider"],
            row["is_service"],
            row["stock_min"],
            row["image_path"] if has_image else "",
            row["location"] if has_location else "",
            row["stock_reserved"] if has_reserved else 0,
            row["average_landed_cost"] if has_avg_landed else 0,
        ))

    cur.execute("DELETE FROM inventory")
    cur.execute("""
        INSERT INTO inventory (
            sku, description, category, protocol, stock_initial, stock_current,
            cost_unit, margin_pct, sale_price, provider, is_service, stock_min,
            image_path, location, stock_reserved, average_landed_cost
        )
        SELECT
            sku, description, category, protocol, stock_initial, stock_current,
            cost_unit, margin_pct, sale_price, provider, is_service, stock_min,
            image_path, location, stock_reserved, average_landed_cost
        FROM inventory_tmp
    """)

    for old_sku, new_sku in sku_map.items():
        if old_sku == new_sku:
            continue
        cur.execute("UPDATE quote_items SET sku = ? WHERE sku = ? AND item_type IN ('producto','servicio','insumo')", (new_sku, old_sku))
        cur.execute("UPDATE kit_items SET sku = ? WHERE sku = ?", (new_sku, old_sku))
        cur.execute("UPDATE installations SET sku = ? WHERE sku = ?", (new_sku, old_sku))
        cur.execute("UPDATE work_order_items SET sku = ? WHERE sku = ?", (new_sku, old_sku))

    cur.execute("DROP TABLE inventory_tmp")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_sku_unique ON inventory(sku)")
    conn.commit()
    conn.close()

def _pdf_logo_path():
    for path in [LOGO_CROP_PATH, BASE_DIR / "logo-abaroasmart.png"]:
        if path.exists():
            return path
    return None

def make_pdf(title, subtitle="", sections=None):
    sections = sections or []
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40

    logo_path = _pdf_logo_path()
    if logo_path:
        try:
            c.drawImage(str(logo_path), 40, y-35, width=140, height=35, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, y-55, title)
    y -= 75
    if subtitle:
        c.setFont("Helvetica", 10)
        c.drawString(40, y, subtitle)
        y -= 20

    c.setFont("Helvetica", 10)
    for section_title, lines in sections:
        if y < 80:
            c.showPage()
            y = height - 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, section_title)
        y -= 16
        c.setFont("Helvetica", 10)
        for line in lines:
            if y < 60:
                c.showPage()
                y = height - 40
                c.setFont("Helvetica", 10)
            c.drawString(50, y, str(line)[:110])
            y -= 14
        y -= 8

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def make_project_delivery_pdf(project_id):
    conn = get_conn()
    project = conn.execute("""
        SELECT p.*, c.name AS client_name, c.address AS client_address, c.phone AS client_phone,
               c.email AS client_email, q.quote_number
        FROM projects p
        LEFT JOIN clients c ON c.id = p.client_id
        LEFT JOIN quotes q ON q.id = p.quotation_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    if not project:
        conn.close()
        return None
    items = conn.execute("SELECT * FROM project_items WHERE project_id = ? AND item_type IN ('producto','kit_component','insumo') ORDER BY id", (project_id,)).fetchall()
    checklist = conn.execute("""
        SELECT pci.item_text, pci.is_checked, pci.evidence_note
        FROM project_checklists pc
        JOIN project_checklist_items pci ON pci.project_checklist_id = pc.id
        WHERE pc.project_id = ?
        ORDER BY pci.id
    """, (project_id,)).fetchall()
    conn.close()

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    navy = colors.HexColor("#23356d")
    blue = colors.HexColor("#3f69b8")
    page_bg = colors.whitesmoke

    c.setFillColor(page_bg)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0b4f94"))
    c.rect(0, height - 88, width, 88, fill=1, stroke=0)

    logo_path = _pdf_logo_path()
    if logo_path:
        try:
            c.drawImage(str(logo_path), 42, height - 66, width=150, height=32, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(205, height - 40, "Abaroa Smart – Domótica y Automatización")
    c.setFont("Helvetica", 9)
    c.drawString(205, height - 54, "WhatsApp: +56 9 8183 8679  |  contacto@abaroasmart.com")
    c.drawString(205, height - 68, "www.abaroasmart.com  |  Cobertura: Región de Los Lagos (Osorno) / Santiago")

    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(width / 2, height - 122, "Acta de Entrega")

    y = height - 178
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Datos del Cliente")
    c.drawString(width/2 + 20, y, "Datos del Proyecto")
    c.setFont("Helvetica", 10)

    left_lines = [str(project["client_name"] or ""), str(project["client_address"] or ""), str(project["client_phone"] or ""), str(project["client_email"] or "")]
    right_lines = [f"N° Proyecto: {project['project_number'] or '-'}", f"Cotización: {project['quote_number'] or '-'}", f"Instalación: {project['installation_date'] or '-'}", f"Entrega: {project['delivery_date'] or '-'}"]
    yl = y - 18
    for line in left_lines:
        c.drawString(50, yl, line[:42]); yl -= 14
    yr = y - 18
    for line in right_lines:
        c.drawString(width/2 + 20, yr, line[:42]); yr -= 14

    table_w = 500
    table_x = (width - table_w) / 2
    table_top = height - 314
    col_widths = [280, 70, 70, 80]
    row_h = 26
    c.setFillColor(blue); c.rect(table_x, table_top, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 11)
    headers = ["Ítem", "SKU", "Comprado", "Usado"]
    cx = table_x
    for h, w in zip(headers, col_widths):
        c.drawCentredString(cx + w/2, table_top + 8, h); cx += w

    yrow = table_top - row_h
    c.setFont("Helvetica", 9)
    display_items = items[:8] if items else [{"description":"Sin ítems asociados.","sku":"-","quantity":0,"used_quantity":0}]
    for row in display_items:
        cx = table_x
        c.setFillColor(colors.white)
        for w in col_widths:
            c.rect(cx, yrow, w, row_h, fill=1, stroke=1); cx += w
        c.setFillColor(colors.black)
        c.drawString(table_x + 8, yrow + 8, str(row["description"])[:42])
        c.drawCentredString(table_x + col_widths[0] + col_widths[1]/2, yrow + 8, str(row["sku"] or "-"))
        c.drawCentredString(table_x + sum(col_widths[:2]) + col_widths[2]/2, yrow + 8, str(int(row["quantity"] or 0)))
        c.drawCentredString(table_x + sum(col_widths[:3]) + col_widths[3]/2, yrow + 8, str(int(row["used_quantity"] or 0)))
        yrow -= row_h

    section_y = yrow - 18
    c.setFillColor(navy); c.setFont("Helvetica-Bold", 11); c.drawString(42, section_y, "Checklist")
    c.setFont("Helvetica", 9); section_y -= 14
    if checklist:
        for row in checklist[:6]:
            state = "OK" if int(row["is_checked"] or 0) else "Pendiente"
            note = f" · {row['evidence_note']}" if row["evidence_note"] else ""
            c.drawString(50, section_y, f"[{state}] {row['item_text']}{note}"[:100]); section_y -= 12
            if section_y < 120: break
    else:
        c.drawString(50, section_y, "Sin checklist cargado."); section_y -= 12

    section_y -= 6
    c.setFont("Helvetica-Bold", 11); c.drawString(42, section_y, "Observaciones")
    c.setFont("Helvetica", 9); section_y -= 14
    obs = str(project["notes"] or "Sin observaciones.")
    for line in [obs[i:i+100] for i in range(0, len(obs), 100)][:3]:
        c.drawString(50, section_y, line); section_y -= 12

    sign_y = 80
    c.setStrokeColor(navy)
    c.line(70, sign_y + 18, 250, sign_y + 18)
    c.line(340, sign_y + 18, 520, sign_y + 18)
    c.setFillColor(navy); c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(160, sign_y, "Firma Cliente")
    c.drawCentredString(430, sign_y, "Firma Técnico")

    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def make_quote_pdf(quote_number, quote_date, client_row, vendor_name, product_lines, kit_lines, service_lines, supply_lines, notes, subtotal_products, subtotal_kits, subtotal_services, subtotal_supplies, vat_products, total):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    navy = colors.HexColor("#23356d")
    blue = colors.HexColor("#3f69b8")
    page_bg = colors.whitesmoke

    c.setFillColor(page_bg)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0b4f94"))
    c.rect(0, height - 88, width, 88, fill=1, stroke=0)

    logo_path = _pdf_logo_path()
    if logo_path:
        try:
            c.drawImage(str(logo_path), 42, height - 66, width=150, height=32, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(205, height - 40, "Abaroa Smart – Domótica y Automatización")
    c.setFont("Helvetica", 9)
    c.drawString(205, height - 54, "WhatsApp: +56 9 8183 8679  |  contacto@abaroasmart.com")
    c.drawString(205, height - 68, "www.abaroasmart.com  |  Cobertura: Región de Los Lagos (Osorno) / Santiago")

    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(width / 2, height - 122, "Orden de Compra")
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, height - 140, f"N° {quote_number} · Fecha {quote_date}")

    y = height - 178
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Datos del Cliente")
    c.drawString(width/2 + 20, y, "Datos del Emisor")
    c.setFont("Helvetica", 10)

    left_lines = [
        str(client_row.get("name","")),
        str(client_row.get("address","")),
        str(client_row.get("phone","")),
        str(client_row.get("email","")),
    ]
    right_lines = [
        "Abaroa Smart",
        f"Ejecutivo: {vendor_name or 'Abaroa Smart'}",
        "Región de Los Lagos (Osorno) / Santiago",
        "contacto@abaroasmart.com",
    ]
    yl = y - 18
    for line in left_lines:
        c.drawString(50, yl, line[:42])
        yl -= 14
    yr = y - 18
    for line in right_lines:
        c.drawString(width/2 + 20, yr, line[:42])
        yr -= 14

    rows = []
    for x in product_lines:
        rows.append((x["description"], int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    for x in kit_lines:
        rows.append((x["name"], int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    for x in service_lines:
        rows.append((f"Servicio · {x['description']}", int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    for x in supply_lines:
        rows.append((f"Insumo · {x['description']}", int(x["quantity"]), int(x["unit_price"]), int(x["line_total"])))
    service_total = int(sum(int(x["line_total"]) for x in service_lines))

    table_w = 500
    table_x = (width - table_w) / 2
    table_top = height - 314
    col_widths = [250, 70, 90, 90]
    row_h = 28

    c.setFillColor(blue)
    c.rect(table_x, table_top, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    headers = ["Producto", "Cantidad", "Precio", "Subtotal"]
    cx = table_x
    for h, w in zip(headers, col_widths):
        c.drawCentredString(cx + w/2, table_top + 9, h)
        cx += w

    yrow = table_top - row_h
    c.setFont("Helvetica", 10)
    display_rows = rows[:10] if rows else [("Descripción", 1, 0, 0)]
    for desc, qty, unit, subtotal in display_rows:
        cx = table_x
        c.setFillColor(colors.white)
        for w in col_widths:
            c.rect(cx, yrow, w, row_h, fill=1, stroke=1)
            cx += w
        c.setFillColor(colors.black)
        c.drawString(table_x + 8, yrow + 9, str(desc)[:38])
        c.drawCentredString(table_x + col_widths[0] + col_widths[1]/2, yrow + 9, str(qty))
        c.drawCentredString(table_x + col_widths[0] + col_widths[1] + col_widths[2]/2, yrow + 9, money(unit))
        c.drawCentredString(table_x + sum(col_widths[:3]) + col_widths[3]/2, yrow + 9, money(subtotal))
        yrow -= row_h

    total_afecto = int(subtotal_products + subtotal_kits + subtotal_supplies)
    total_exento = int(service_total)

    ty = yrow - 20
    label_x = width - 180
    value_x = width - 50
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(label_x, ty, "Total afecto")
    c.drawRightString(value_x, ty, money(total_afecto))
    c.drawRightString(label_x, ty - 20, "Total exento")
    c.drawRightString(value_x, ty - 20, money(total_exento))
    c.drawRightString(label_x, ty - 40, "IVA 19%")
    c.drawRightString(value_x, ty - 40, money(vat_products))
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(label_x, ty - 66, "Total")
    c.drawRightString(value_x, ty - 66, money(total))

    notes_clean = [ln.strip() for ln in str(notes or "").splitlines() if ln.strip()]
    footer_lines = [
        "- Los valores de Servicios Profesionales contemplan la configuración lógica (software) y capacitación.",
        "- Modificaciones estructurales en la red eléctrica o reparaciones de internet no están incluidas.",
        "- Condición de Pago: 50% para la adquisición de equipos y reserva de agenda; 50% restante contra entrega y pruebas de funcionamiento.",
        "- Requerimientos Técnicos: El cliente debe contar con acceso a la red eléctrica y señal WiFi estable en los puntos de instalación.",
        "- Garantía: Consulta los términos detallados y cobertura en www.abaroasmart.com.",
    ]
    c.setFillColor(navy)
    c.setFont("Helvetica", 7.5)
    txt = c.beginText(42, 94)
    txt.setLeading(9)
    max_width = width - 84
    for raw in footer_lines:
        words = raw.split()
        line = ""
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, "Helvetica", 7.5) <= max_width:
                line = test
            else:
                txt.textLine(line)
                line = word
        if line:
            txt.textLine(line)
    c.drawText(txt)

    if notes_clean:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(navy)
        c.drawString(42, 62, "Observaciones:")
        c.setFont("Helvetica", 8)
        obs_text = c.beginText(42, 50)
        obs_text.setLeading(9)
        for line in notes_clean[:3]:
            obs_text.textLine(line[:115])
        c.drawText(obs_text)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()



def search_like_clause(columns):
    return " OR ".join([f"COALESCE(CAST({col} AS TEXT),'') LIKE ?" for col in columns])


def run_global_search(term):
    needle = f"%{str(term or '').strip()}%"
    results = {}
    conn = get_conn()
    search_specs = {
        "Inventario": {
            "sql": f"SELECT sku AS codigo, description AS titulo, category AS detalle_1, provider AS detalle_2, sale_price AS monto FROM inventory WHERE {search_like_clause(['sku','description','category','provider','protocol','location'])} ORDER BY category, sku LIMIT 200",
            "params": [needle] * 6,
        },
        "Herramientas": {
            "sql": f"SELECT asset_id AS codigo, tool_name AS titulo, category AS detalle_1, provider AS detalle_2, cost_unit AS monto FROM tools_assets WHERE {search_like_clause(['asset_id','tool_name','category','provider','status','notes'])} ORDER BY tool_name, asset_id LIMIT 200",
            "params": [needle] * 6,
        },
        "Clientes": {
            "sql": f"SELECT CAST(id AS TEXT) AS codigo, name AS titulo, phone AS detalle_1, email AS detalle_2, NULL AS monto FROM clients WHERE {search_like_clause(['id','name','phone','email','address'])} ORDER BY id DESC LIMIT 200",
            "params": [needle] * 5,
        },
        "Proveedores": {
            "sql": f"SELECT CAST(id AS TEXT) AS codigo, name AS titulo, phone AS detalle_1, email AS detalle_2, NULL AS monto FROM suppliers WHERE {search_like_clause(['id','name','phone','email','contact_person','notes'])} ORDER BY id DESC LIMIT 200",
            "params": [needle] * 6,
        },
        "Vendedores": {
            "sql": f"SELECT CAST(id AS TEXT) AS codigo, name AS titulo, role AS detalle_1, email AS detalle_2, NULL AS monto FROM vendors WHERE {search_like_clause(['id','name','role','email','phone'])} ORDER BY id DESC LIMIT 200",
            "params": [needle] * 5,
        },
        "Cotizaciones": {
            "sql": f"SELECT quote_number AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, q.status AS detalle_1, q.quote_date AS detalle_2, q.total AS monto FROM quotes q LEFT JOIN clients c ON c.id=q.client_id WHERE {search_like_clause(['q.quote_number','q.status','q.quote_date','q.notes','c.name'])} ORDER BY q.id DESC LIMIT 200",
            "params": [needle] * 5,
        },
        "OT": {
            "sql": f"SELECT ot_number AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, w.status AS detalle_1, w.scheduled_date AS detalle_2, (COALESCE(w.labor_cost,0)+COALESCE(w.travel_cost,0)+COALESCE(w.extra_material_cost,0)) AS monto FROM work_orders w LEFT JOIN clients c ON c.id=w.client_id WHERE {search_like_clause(['w.ot_number','w.status','w.scheduled_date','w.address','w.notes','c.name'])} ORDER BY w.id DESC LIMIT 200",
            "params": [needle] * 6,
        },
        "Proyectos": {
            "sql": f"SELECT project_number AS codigo, COALESCE(name,'Sin nombre') AS titulo, status AS detalle_1, technical_status AS detalle_2, NULL AS monto FROM projects WHERE {search_like_clause(['project_number','name','description','status','technical_status','configuration_url','notes'])} ORDER BY id DESC LIMIT 200",
            "params": [needle] * 7,
        },
        "Ventas": {
            "sql": f"SELECT CAST(s.id AS TEXT) AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, s.sale_date AS detalle_1, printf('Margen %.1f%%', COALESCE(s.gross_margin_pct,0)*100.0) AS detalle_2, s.total AS monto FROM sales s LEFT JOIN clients c ON c.id=s.client_id WHERE {search_like_clause(['s.id','s.sale_date','c.name'])} ORDER BY s.id DESC LIMIT 200",
            "params": [needle] * 3,
        },
        "Garantías": {
            "sql": f"SELECT CAST(w.id AS TEXT) AS codigo, COALESCE(c.name,'Sin cliente') AS titulo, w.status AS detalle_1, w.expiry_date AS detalle_2, NULL AS monto FROM warranties w LEFT JOIN clients c ON c.id=w.client_id WHERE {search_like_clause(['w.id','w.status','w.expiry_date','w.notes','c.name'])} ORDER BY w.id DESC LIMIT 200",
            "params": [needle] * 5,
        },
        "Instalaciones": {
            "sql": f"SELECT CAST(i.id AS TEXT) AS codigo, i.description AS titulo, i.location AS detalle_1, i.install_date AS detalle_2, NULL AS monto FROM installations i WHERE {search_like_clause(['i.id','i.sku','i.description','i.serial_number','i.location','i.notes'])} ORDER BY i.id DESC LIMIT 200",
            "params": [needle] * 6,
        },
        "Insumos": {
            "sql": f"SELECT CAST(id AS TEXT) AS codigo, description AS titulo, NULL AS detalle_1, NULL AS detalle_2, default_unit_price AS monto FROM supplies_catalog WHERE {search_like_clause(['id','description'])} ORDER BY description LIMIT 200",
            "params": [needle] * 2,
        },
        "Kits": {
            "sql": f"SELECT code AS codigo, name AS titulo, notes AS detalle_1, NULL AS detalle_2, sale_price AS monto FROM kits WHERE {search_like_clause(['code','name','notes'])} ORDER BY code LIMIT 200",
            "params": [needle] * 3,
        },
    }
    try:
        for name, spec in search_specs.items():
            try:
                df = pd.read_sql_query(spec['sql'], conn, params=spec['params'])
                results[name] = df
            except Exception:
                results[name] = pd.DataFrame(columns=['codigo','titulo','detalle_1','detalle_2','monto'])
    finally:
        conn.close()
    return results

def apply_theme():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(180deg, #0b1220 0%, #111827 55%, #0f172a 100%); color: #e5e7eb; }
    header[data-testid="stHeader"] {display:none;}
    [data-testid="stToolbar"] {display:none;}
    #MainMenu {visibility:hidden;}
    footer {visibility:hidden;}
    [data-testid="stAppViewContainer"] { background: linear-gradient(180deg, #0b1220 0%, #111827 55%, #0f172a 100%); }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(15,23,42,.98) 0%, rgba(2,6,23,.98) 100%) !important;
        border-right: 1px solid rgba(148,163,184,.12);
    }
    [data-testid="stSidebar"] > div:first-child {
        background: transparent !important;
    }
    .block-container { max-width: 100% !important; padding-top: 0.8rem; padding-bottom: 2rem; padding-left: 1rem; padding-right: 1rem; }
    h1,h2,h3,h4,h5 { color: #f8fafc !important; }
    [data-testid="stMetricValue"] { color: white !important; }
    [data-testid="stMetricLabel"] { color: #cbd5e1 !important; }
    div[data-testid="stTabs"] button { color: #e5e7eb; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color: #60a5fa !important; }
    .card, .soft-card {
        padding: 1rem 1.1rem;
        border: 1px solid rgba(148,163,184,.14);
        background: linear-gradient(180deg, rgba(15,23,42,.86) 0%, rgba(17,24,39,.92) 100%);
        border-radius: 22px;
        box-shadow: 0 14px 30px rgba(0,0,0,.25);
    }
    .hero {
        padding: 1.25rem 1.35rem;
        border-radius: 24px;
        background: linear-gradient(135deg, rgba(30,41,59,.95), rgba(15,23,42,.86));
        border: 1px solid rgba(148,163,184,.16);
        margin-bottom: 1rem;
        box-shadow: 0 12px 30px rgba(0,0,0,.18);
    }
    .app-shell-header {
        padding: .8rem 1rem;
        border-radius: 22px;
        border: 1px solid rgba(148,163,184,.14);
        background: linear-gradient(180deg, rgba(15,23,42,.92) 0%, rgba(17,24,39,.96) 100%);
        box-shadow: 0 14px 30px rgba(0,0,0,.18);
        margin-bottom: 1rem;
    }
    .app-shell-header .title {
        font-size: 1.45rem;
        font-weight: 800;
        color: #f8fafc;
        margin: 0;
        line-height: 1.1;
    }
    .app-shell-header .subtitle {
        color: #94a3b8;
        font-size: .88rem;
        margin-top: .22rem;
    }
    .kpi-card {
        border-radius: 24px;
        padding: 1.05rem 1.15rem;
        min-height: 136px;
        background: linear-gradient(180deg, rgba(15,23,42,.94) 0%, rgba(17,24,39,.96) 100%);
        border: 1px solid rgba(148,163,184,.14);
        box-shadow: 0 14px 30px rgba(0,0,0,.18);
    }
    .kpi-label {
        color: #94a3b8;
        font-size: .78rem;
        letter-spacing: .06em;
        text-transform: uppercase;
        font-weight: 700;
    }
    .kpi-value {
        color: #f8fafc;
        font-size: 2.1rem;
        font-weight: 800;
        margin-top: .45rem;
        line-height: 1.0;
    }
    .kpi-delta {
        color: #60a5fa;
        font-size: .88rem;
        margin-top: .4rem;
        font-weight: 600;
    }
    .panel-card {
        border-radius: 24px;
        padding: 1.1rem 1.2rem;
        min-height: 220px;
        background: linear-gradient(180deg, rgba(15,23,42,.90) 0%, rgba(17,24,39,.95) 100%);
        border: 1px solid rgba(148,163,184,.12);
        box-shadow: 0 14px 30px rgba(0,0,0,.16);
    }
    .panel-title {
        color: #f8fafc;
        font-size: 1rem;
        font-weight: 800;
        margin-bottom: .3rem;
    }
    .panel-subtitle {
        color: #94a3b8;
        font-size: .84rem;
        margin-bottom: .9rem;
    }
    .status-pill {
        display: inline-block;
        padding: .24rem .55rem;
        border-radius: 999px;
        background: rgba(96,165,250,.14);
        color: #93c5fd;
        font-size: .74rem;
        font-weight: 700;
        border: 1px solid rgba(96,165,250,.14);
    }
    [data-testid="stSidebar"] .stButton > button {
        width: 100%;
        border-radius: 14px;
        min-height: 44px;
        text-align: left;
        border: 1px solid rgba(148,163,184,.10);
        background: rgba(255,255,255,.02);
        color: #e5e7eb;
        font-weight: 600;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: rgba(96,165,250,.35);
        background: rgba(96,165,250,.10);
        color: #fff;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(37,99,235,.88), rgba(79,70,229,.88));
        border-color: rgba(96,165,250,.28);
        color: white;
    }
    .sidebar-brand {
        padding: .55rem .2rem 1rem .2rem;
        border-bottom: 1px solid rgba(148,163,184,.12);
        margin-bottom: .8rem;
    }
    .sidebar-brand-title { color:#f8fafc; font-size:1.15rem; font-weight:800; margin:0; }
    .sidebar-brand-sub { color:#94a3b8; font-size:.82rem; margin-top:.18rem; }
    .sidebar-section-title {
        color:#64748b;
        font-size:.74rem;
        text-transform:uppercase;
        letter-spacing:.09em;
        font-weight:800;
        margin:1rem 0 .5rem 0.2rem;
    }
    .stButton > button {
        white-space: nowrap !important;
    }
    div[data-testid="column"] .stButton > button {
        min-height: 42px;
        border-radius: 14px;
    }
    div[data-testid="stTextInput"] input {
        border-radius: 14px !important;
    }
    @media (max-width: 768px){
        .block-container{padding-top:.5rem;}
    }
    </style>
    """, unsafe_allow_html=True)

def logo(width=260):
    for path in [LOGO_CROP_PATH, BASE_DIR / "logo-abaroasmart.png", LOGO_PATH]:
        if path.exists():
            st.image(str(path), width=width)
            return

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



def hash_password(raw):
    return hashlib.sha256(str(raw or '').encode('utf-8')).hexdigest()


def ensure_app_settings():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    defaults = {
        'admin_username': 'admin',
        'admin_password_hash': hash_password('admin123'),
    }
    for key, value in defaults.items():
        row = cur.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        if row is None:
            cur.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_setting(key, default=''):
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row and row['value'] is not None else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        """INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, str(value))
    )
    conn.commit()
    conn.close()


def verify_admin_credentials(username, password):
    ensure_app_settings()
    saved_user = get_setting('admin_username', 'admin').strip()
    saved_hash = get_setting('admin_password_hash', hash_password('admin123')).strip()
    return username.strip() == saved_user and hash_password(password) == saved_hash


def admin_logged_in():
    return bool(st.session_state.get('admin_logged_in', False))


def refresh_quote_supply_unit_from_master():
    selected_desc = str(st.session_state.get("add_supply_desc_sel", "") or "").strip()
    if not selected_desc or selected_desc == "Nuevo insumo...":
        st.session_state["add_supply_unit"] = 0
        return
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT default_unit_price FROM supplies_catalog WHERE description = ? LIMIT 1",
            (selected_desc,)
        ).fetchone()
        conn.close()
        st.session_state["add_supply_unit"] = int(row["default_unit_price"] or 0) if row else 0
    except Exception:
        st.session_state["add_supply_unit"] = 0


def reset_quote_supply_inputs():
    st.session_state["quote_supply_reset_pending"] = True


def get_alerts_data():
    alerts = []
    try:
        low_stock_df = get_df("""
            SELECT sku, description, stock_current, stock_min
            FROM inventory
            WHERE COALESCE(is_service,0)=0
              AND COALESCE(stock_min,0) > 0
              AND COALESCE(stock_current,0) <= COALESCE(stock_min,0)
            ORDER BY stock_current ASC, description ASC
            LIMIT 8
        """)
        for _, row in low_stock_df.iterrows():
            alerts.append({
                'level': 'warning',
                'title': f"Stock bajo · {row['sku']}",
                'detail': f"{row['description']} · stock {int(row['stock_current'] or 0)} / mínimo {int(row['stock_min'] or 0)}",
            })
    except Exception:
        pass
    try:
        pending_quotes = get_df("SELECT quote_number, status FROM quotes WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Enviada') ORDER BY id DESC LIMIT 5")
        for _, row in pending_quotes.iterrows():
            alerts.append({
                'level': 'info',
                'title': f"Cotización {row['quote_number']}",
                'detail': f"Estado actual: {row['status']}",
            })
    except Exception:
        pass
    try:
        pending_projects = get_df("SELECT project_number, status, technical_status FROM projects WHERE COALESCE(status,'Pendiente') NOT IN ('Entregado','Cerrado') ORDER BY id DESC LIMIT 5")
        for _, row in pending_projects.iterrows():
            alerts.append({
                'level': 'info',
                'title': f"Proyecto {row['project_number']}",
                'detail': f"Estado: {row['status']} · Técnico: {row['technical_status']}",
            })
    except Exception:
        pass
    return alerts[:10]


def table_columns(table_name):
    conn = get_conn()
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    conn.close()
    return cols


def get_dashboard_work_orders_df(limit=8):
    cols = set(table_columns("work_orders"))
    if "estimated_material_cost" in cols:
        sql = (
            "SELECT ot_number AS OT, status AS Estado, scheduled_date AS Fecha, "
            "estimated_material_cost AS 'Costo estimado' "
            "FROM work_orders WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso') ORDER BY id DESC LIMIT ?"
        )
    else:
        cost_parts = []
        for c in ["labor_cost", "travel_cost", "extra_material_cost"]:
            if c in cols:
                cost_parts.append(f"COALESCE({c}, 0)")
        cost_expr = " + ".join(cost_parts) if cost_parts else "0"
        sql = (
            f"SELECT ot_number AS OT, status AS Estado, scheduled_date AS Fecha, "
            f"({cost_expr}) AS 'Costo estimado' "
            f"FROM work_orders WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso') ORDER BY id DESC LIMIT ?"
        )
    return get_df(sql, (limit,))


def ensure_column(conn, table, column, definition):
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def init_inventory_media_schema():
    conn = get_conn()
    ensure_column(conn, "inventory", "image_path", "TEXT DEFAULT ''")
    ensure_column(conn, "inventory", "location", "TEXT DEFAULT ''")
    conn.close()


def inventory_image_web_path(path_value):
    path_str = str(path_value or "").strip()
    if not path_str:
        return ""
    normalized = path_str.replace('\\', '/')
    if normalized.startswith('http://') or normalized.startswith('https://'):
        return normalized
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = BASE_DIR / normalized.lstrip('/\\')
    try:
        candidate = candidate.resolve()
    except Exception:
        pass
    return str(candidate) if candidate.exists() else ""


def save_inventory_image(uploaded_file, sku):
    if uploaded_file is None or not sku:
        return ""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower() or '.jpg'
    if suffix == '.jpeg':
        suffix = '.jpg'
    safe_sku = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in str(sku))
    target = UPLOAD_DIR / f"{safe_sku}{suffix}"
    temp_target = UPLOAD_DIR / f"{safe_sku}.__tmp__{suffix}"
    data = uploaded_file.getbuffer()
    with open(temp_target, 'wb') as f:
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
    return str(target.relative_to(BASE_DIR)).replace('\\\\', '/')


def normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())

def exists_duplicate(table, checks, exclude_id=None, exclude_field="id"):
    conn = get_conn()
    query = f"SELECT COUNT(*) as c FROM {table} WHERE " + " AND ".join([f"{k}=?" for k in checks.keys()])
    params = list(checks.values())
    if exclude_id is not None:
        query += f" AND {exclude_field} <> ?"
        params.append(exclude_id)
    row = conn.execute(query, params).fetchone()
    conn.close()
    return int(row["c"] or 0) > 0



def merge_items_by_key(items, key_field="sku", description_field="description"):
    merged = {}
    order = []
    for item in items or []:
        key = str(item.get(key_field, "") or "").strip() or str(item.get(description_field, "") or "").strip()
        if not key:
            continue
        qty = int(item.get("quantity", 0) or 0)
        unit_price = int(item.get("unit_price", 0) or 0)
        if key in merged:
            merged[key]["quantity"] = int(merged[key].get("quantity", 0) or 0) + qty
            merged[key]["unit_price"] = unit_price or int(merged[key].get("unit_price", 0) or 0)
            merged[key]["line_total"] = int(merged[key]["quantity"]) * int(merged[key]["unit_price"])
        else:
            row = dict(item)
            row["quantity"] = qty
            row["unit_price"] = unit_price
            row["line_total"] = int(row.get("line_total", qty * unit_price) or 0)
            merged[key] = row
            order.append(key)
    return [merged[k] for k in order]

def validate_quote_before_save(client_row, product_lines, service_lines, kit_lines, supply_lines, products_df):
    errors = []

    def _row_has_name(row):
        if row is None:
            return False
        if isinstance(row, dict):
            return bool(str(row.get("name", "") or "").strip())
        getter = getattr(row, "get", None)
        if callable(getter):
            try:
                return bool(str(getter("name", "") or "").strip())
            except Exception:
                pass
        try:
            return bool(str(row["name"] or "").strip())
        except Exception:
            return False

    if not _row_has_name(client_row):
        errors.append("Debes seleccionar un cliente.")
    if not product_lines and not service_lines and not kit_lines and not supply_lines:
        errors.append("Agrega al menos un producto, kit, servicio o insumo.")
    for line in product_lines:
        sku = line.get("sku")
        prod = products_df.loc[products_df["sku"] == sku]
        if prod.empty:
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
            warnings.append(f"Stock insuficiente para {line.get('description','')}: disponible {available}, solicitado {qty}. La cotización se guardará igualmente.")
    return warnings

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

def table_exists(conn, table):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def ensure_tools_assets_schema(conn):
    desired_cols = [
        ("asset_id", "TEXT"),
        ("tool_name", "TEXT"),
        ("category", "TEXT"),
        ("provider", "TEXT"),
        ("quantity", "INTEGER"),
        ("cost_unit", "INTEGER"),
        ("purchase_date", "TEXT"),
        ("useful_life_months", "INTEGER"),
        ("monthly_cost", "INTEGER"),
        ("status", "TEXT"),
        ("notes", "TEXT"),
        ("created_at", "TEXT"),
    ]
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tools_assets'")
    exists = cur.fetchone() is not None
    if not exists:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tools_assets (
            asset_id TEXT PRIMARY KEY,
            tool_name TEXT NOT NULL,
            category TEXT DEFAULT 'Herramienta',
            provider TEXT,
            quantity INTEGER DEFAULT 1,
            cost_unit INTEGER DEFAULT 0,
            purchase_date TEXT DEFAULT '',
            useful_life_months INTEGER DEFAULT 12,
            monthly_cost INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Activa',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
        return

    info = cur.execute("PRAGMA table_info(tools_assets)").fetchall()
    existing = [r[1] for r in info]
    if all(col in existing for col, _ in desired_cols):
        return

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tools_assets_new (
        asset_id TEXT PRIMARY KEY,
        tool_name TEXT NOT NULL,
        category TEXT DEFAULT 'Herramienta',
        provider TEXT,
        quantity INTEGER DEFAULT 1,
        cost_unit INTEGER DEFAULT 0,
        purchase_date TEXT DEFAULT '',
        useful_life_months INTEGER DEFAULT 12,
        monthly_cost INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Activa',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    src_cols = set(existing)
    select_map = {
        "asset_id": "asset_id" if "asset_id" in src_cols else ("tool_name" if "tool_name" in src_cols else ("producto" if "producto" in src_cols else "''")),
        "tool_name": "tool_name" if "tool_name" in src_cols else ("producto" if "producto" in src_cols else "''"),
        "category": "category" if "category" in src_cols else ("categoria" if "categoria" in src_cols else "'Herramienta'"),
        "provider": "provider" if "provider" in src_cols else ("proveedor" if "proveedor" in src_cols else "''"),
        "quantity": "quantity" if "quantity" in src_cols else ("cantidad" if "cantidad" in src_cols else "1"),
        "cost_unit": "cost_unit" if "cost_unit" in src_cols else ("costo_unitario" if "costo_unitario" in src_cols else "0"),
        "purchase_date": "purchase_date" if "purchase_date" in src_cols else "''",
        "useful_life_months": "useful_life_months" if "useful_life_months" in src_cols else "12",
        "monthly_cost": "monthly_cost" if "monthly_cost" in src_cols else "0",
        "status": "status" if "status" in src_cols else "'Activa'",
        "notes": "notes" if "notes" in src_cols else "''",
        "created_at": "created_at" if "created_at" in src_cols else "CURRENT_TIMESTAMP",
    }

    cur.execute("DELETE FROM tools_assets_new")
    cur.execute(f"""
        INSERT OR REPLACE INTO tools_assets_new (
            asset_id, tool_name, category, provider, quantity, cost_unit,
            purchase_date, useful_life_months, monthly_cost, status, notes, created_at
        )
        SELECT
            {select_map['asset_id']},
            {select_map['tool_name']},
            {select_map['category']},
            {select_map['provider']},
            {select_map['quantity']},
            {select_map['cost_unit']},
            {select_map['purchase_date']},
            {select_map['useful_life_months']},
            {select_map['monthly_cost']},
            {select_map['status']},
            {select_map['notes']},
            {select_map['created_at']}
        FROM tools_assets
    """)
    cur.execute("DROP TABLE tools_assets")
    cur.execute("ALTER TABLE tools_assets_new RENAME TO tools_assets")
    conn.commit()


def normalize_tools_df(df):
    df = df.copy()
    rename_map = {
        "producto": "tool_name",
        "proveedor": "provider",
        "cantidad": "quantity",
        "costo_unitario": "cost_unit",
        "categoria": "category",
        "nombre": "tool_name",
    }
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    if "asset_id" not in df.columns:
        if "tool_name" in df.columns:
            df["asset_id"] = [f"TL-{i+1:04d}" for i in range(len(df.index))]
        else:
            df["asset_id"] = []
    defaults = {
        "tool_name": "",
        "category": "Herramienta",
        "provider": "",
        "quantity": 1,
        "cost_unit": 0,
        "purchase_date": "",
        "useful_life_months": 12,
        "monthly_cost": 0,
        "status": "Activa",
        "notes": "",
    }
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
    return df[ordered]


APP_DIR = BASE_DIR  # alias para compatibilidad interna

def db_file():
    return str(DB_PATH)

def backup_database(custom_name=""):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"backup_{ts}.db" if not custom_name else f"{custom_name}_{ts}.db"
    dst = BACKUP_DIR / name
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, dst)
        return dst
    return None

def list_backups():
    files = sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files

def restore_backup(filename):
    src = BACKUP_DIR / filename
    if not src.exists():
        return False, "No se encontró el respaldo."
    if DB_PATH.exists():
        safe_copy = BACKUP_DIR / f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, safe_copy)
    shutil.copy2(src, DB_PATH)
    try:
        init_db()
        normalize_services_and_seed_abaroa_kits()
        remove_duplicate_rows()
        recalc_all_sale_prices()
        recalc_stock()
    except Exception:
        pass
    return True, f"Respaldo restaurado y migrado: {filename}"

def export_all_data_json():
    conn = get_conn()
    tables = [
        "inventory","clients","vendors","suppliers","supplies_catalog","kits","kit_items",
        "quotes","quote_items","sales","billing","work_orders","work_order_items","warranties"
    ]
    data = {}
    for t in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            data[t] = [dict(r) for r in rows]
        except Exception:
            data[t] = []
    conn.close()
    out = APP_DIR / f"export_abaroa_smart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return out

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
        return False, "El archivo no parece ser una base de datos SQLite válida."
    if DB_PATH.exists():
        safe_copy = BACKUP_DIR / f"pre_upload_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, safe_copy)
    shutil.copy2(tmp, DB_PATH)
    tmp.unlink(missing_ok=True)
    try:
        init_db()
        remove_duplicate_rows()
        recalc_all_sale_prices()
        recalc_stock()
    except Exception:
        pass
    return True, "Base restaurada desde archivo cargado y migrada."



def _find_inventory_sku_by_terms(cur, terms, require_physical=True):
    """Busca un SKU existente por términos en descripción/categoría/protocolo sin crear inventario falso."""
    where_service = "AND COALESCE(is_service,0)=0" if require_physical else ""
    rows = cur.execute(f"SELECT sku, description, category, protocol FROM inventory WHERE 1=1 {where_service}").fetchall()
    norm_terms = [str(t).lower() for t in terms if str(t).strip()]
    best = None
    best_score = 0
    for r in rows:
        hay = " ".join([str(r["sku"] or ""), str(r["description"] or ""), str(r["category"] or ""), str(r["protocol"] or "")]).lower()
        score = sum(1 for t in norm_terms if t in hay)
        if score > best_score:
            best_score = score
            best = r["sku"]
    return best if best_score > 0 else None


def normalize_services_and_seed_abaroa_kits():
    """Unifica servicios como inventario lógico y crea kits maestros Abaroa Smart desde abaroasmart.com.

    Reglas:
    - Servicios: is_service=1, stock=0, no alertas, no consumo físico.
    - Kits: plantillas comerciales editables, con precio propio y componentes desde inventory cuando existan.
    - No elimina datos existentes ni cambia cotizaciones históricas.
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1) Normalizar servicios existentes, incluyendo PRD-SER legacy.
    cur.execute("""
        UPDATE inventory
        SET is_service=1, stock_initial=0, stock_current=0, stock_reserved=0, stock_min=0,
            category=CASE WHEN COALESCE(category,'')='' THEN 'Servicios' ELSE category END,
            protocol=CASE WHEN COALESCE(protocol,'')='' THEN 'Servicios' ELSE protocol END
        WHERE sku LIKE 'PRD-SER-%'
           OR sku LIKE 'SRV-%'
           OR LOWER(COALESCE(category,'')) LIKE '%servicio%'
           OR LOWER(COALESCE(protocol,'')) LIKE '%servicio%'
    """)

    # 2) Servicios comerciales base del sitio/catálogo Abaroa Smart.
    services = [
        ('SRV-AUT-0001', 'Automatizaciones personalizadas', 55000),
        ('SRV-CAP-0001', 'Capacitación cliente', 25000),
        ('SRV-DIA-0001', 'Diagnóstico técnico / visita técnica', 25000),
        ('SRV-CAM-0001', 'Instalación de cámaras de seguridad IP', 40000),
        ('SRV-ALA-0001', 'Instalación de sistema de alarma inteligente', 50000),
        ('SRV-INT-0001', 'Integración completa hogar inteligente', 120000),
        ('SRV-CFG-0001', 'Configuración sistema domótico completo (software)', 85000),
        ('SRV-INS-0001', 'Instalación básica dispositivos inteligentes', 35000),
        ('SRV-HOG-0001', 'Instalación de sistema domótico completo (hogar)', 150000),
        ('SRV-MNT-0001', 'Mantención sistema domótico', 45000),
    ]
    for sku, desc, price in services:
        exists = cur.execute("SELECT sku FROM inventory WHERE description=? AND COALESCE(is_service,0)=1 LIMIT 1", (desc,)).fetchone()
        target_sku = exists["sku"] if exists else sku
        cur.execute("""
            INSERT INTO inventory (sku, description, category, protocol, stock_initial, stock_current, cost_unit, margin_pct, sale_price, provider, is_service, stock_min, image_path, location, stock_reserved, average_landed_cost)
            VALUES (?, ?, 'Servicios', 'Servicios', 0, 0, 0, 0, ?, 'Abaroa Smart', 1, 0, '', '', 0, 0)
            ON CONFLICT(sku) DO UPDATE SET
                description=excluded.description,
                category='Servicios', protocol='Servicios', stock_initial=0, stock_current=0, stock_reserved=0,
                stock_min=0, sale_price=excluded.sale_price, is_service=1
        """, (target_sku, desc, int(price)))

    # 3) Kits publicados por AbaroaSmart.com (precios públicos del sitio/contacto).
    kits = [
        ('KIT-INICIO-001', 'Pack Inicio Smart', 149990, 'Control de iluminación, sensor de movimiento, app de control incluida e instalación profesional.'),
        ('KIT-SEG-001', 'Pack Seguridad Smart', 289990, 'Pack Inicio Smart más cámara inteligente, sensores de apertura, sirena y automatización de seguridad.'),
        ('KIT-CONFORT-001', 'Pack Confort Smart', 599990, 'Pack Seguridad Smart más termostato inteligente, motores de cortina roller, panel táctil y escenas avanzadas.'),
    ]
    for code, name, price, notes in kits:
        cur.execute("""
            INSERT INTO kits (code, name, sale_price, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET name=excluded.name, sale_price=excluded.sale_price, notes=excluded.notes
        """, (code, name, int(price), notes))

    # 4) Componentes sugeridos desde inventario existente. No crea productos inexistentes.
    kit_components_terms = {
        'KIT-INICIO-001': [
            (['interruptor', '1 gang'], 1),
            (['bombilla', 'ampolleta'], 3),
            (['sensor', 'movimiento'], 1),
            (['instalación básica dispositivos inteligentes'], 1),
            (['configuración sistema domótico completo'], 1),
            (['automatizaciones personalizadas'], 1),
        ],
        'KIT-SEG-001': [
            (['interruptor', '1 gang'], 1),
            (['bombilla', 'ampolleta'], 3),
            (['sensor', 'movimiento'], 1),
            (['cámara', 'camara'], 1),
            (['sensor', 'apertura'], 2),
            (['sirena'], 1),
            (['instalación básica dispositivos inteligentes'], 1),
            (['configuración sistema domótico completo'], 1),
            (['instalación de cámaras de seguridad'], 1),
        ],
        'KIT-CONFORT-001': [
            (['interruptor', '1 gang'], 1),
            (['bombilla', 'ampolleta'], 3),
            (['sensor', 'movimiento'], 1),
            (['cámara', 'camara'], 1),
            (['sensor', 'apertura'], 2),
            (['sirena'], 1),
            (['termostato'], 1),
            (['motor', 'cortina'], 2),
            (['panel', 'táctil'], 1),
            (['integración completa hogar inteligente'], 1),
            (['configuración sistema domótico completo'], 1),
            (['automatizaciones personalizadas'], 1),
        ],
    }
    for code, comps in kit_components_terms.items():
        kit = cur.execute("SELECT id FROM kits WHERE code=?", (code,)).fetchone()
        if not kit:
            continue
        kit_id = int(kit['id'])
        # limpiar y reconstruir componentes para que sea determinista.
        cur.execute("DELETE FROM kit_items WHERE kit_id=?", (kit_id,))
        seen = set()
        for terms, qty in comps:
            # Buscar servicios por descripción primero si el término lo sugiere.
            require_physical = not any(x in ' '.join(terms).lower() for x in ['instalación','configuración','automatizaciones','integración'])
            sku = _find_inventory_sku_by_terms(cur, terms, require_physical=require_physical)
            if sku and sku not in seen:
                cur.execute("INSERT INTO kit_items (kit_id, sku, quantity) VALUES (?, ?, ?)", (kit_id, sku, int(qty)))
                seen.add(sku)

    conn.commit()
    conn.close()

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        sku TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        category TEXT,
        protocol TEXT,
        stock_initial INTEGER,
        stock_current INTEGER,
        cost_unit INTEGER,
        margin_pct INTEGER,
        sale_price INTEGER,
        provider TEXT,
        is_service INTEGER DEFAULT 0,
        stock_min INTEGER DEFAULT 0,
        image_path TEXT DEFAULT '',
        location TEXT DEFAULT '',
        stock_reserved INTEGER DEFAULT 0,
        average_landed_cost INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        address TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        role TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS supplies_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT UNIQUE NOT NULL,
        default_unit_price INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        phone TEXT,
        email TEXT,
        contact_person TEXT,
        notes TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote_number TEXT NOT NULL,
        quote_date TEXT NOT NULL,
        client_id INTEGER,
        vendor_id INTEGER,
        validity_days INTEGER DEFAULT 10,
        status TEXT DEFAULT 'Pendiente',
        notes TEXT,
        subtotal_products INTEGER DEFAULT 0,
        subtotal_services_exempt INTEGER DEFAULT 0,
        vat_products INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quote_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote_id INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        sku TEXT,
        description TEXT NOT NULL,
        quantity INTEGER DEFAULT 1,
        unit_price INTEGER DEFAULT 0,
        line_total INTEGER DEFAULT 0,
        vat_exempt INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT NOT NULL,
        client_id INTEGER,
        quote_id INTEGER,
        total INTEGER DEFAULT 0,
        material_cost INTEGER DEFAULT 0,
        gross_margin INTEGER DEFAULT 0,
        gross_margin_pct REAL DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS billing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER,
        client_id INTEGER,
        total INTEGER DEFAULT 0,
        advance_50 INTEGER DEFAULT 0,
        balance_50 INTEGER DEFAULT 0,
        payment_status TEXT DEFAULT 'Pendiente'
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS warranties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        sale_id INTEGER UNIQUE,
        install_date TEXT,
        warranty_months INTEGER DEFAULT 6,
        expiry_date TEXT,
        status TEXT DEFAULT 'Vigente',
        notes TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS installations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        install_date TEXT NOT NULL,
        sku TEXT,
        description TEXT NOT NULL,
        serial_number TEXT,
        location TEXT,
        notes TEXT,
        warranty_months INTEGER DEFAULT 12
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS kits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        sale_price INTEGER DEFAULT 0,
        notes TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS kit_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kit_id INTEGER NOT NULL,
        sku TEXT NOT NULL,
        quantity INTEGER NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ot_number TEXT NOT NULL,
        client_id INTEGER,
        vendor_id INTEGER,
        quote_id INTEGER,
        status TEXT DEFAULT 'Pendiente',
        scheduled_date TEXT,
        address TEXT,
        hours_work REAL DEFAULT 0,
        labor_cost INTEGER DEFAULT 0,
        travel_cost INTEGER DEFAULT 0,
        extra_material_cost INTEGER DEFAULT 0,
        notes TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS work_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_order_id INTEGER NOT NULL,
        sku TEXT,
        description TEXT,
        quantity INTEGER DEFAULT 1,
        cost_unit INTEGER DEFAULT 0,
        line_cost INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT NOT NULL,
        movement_type TEXT NOT NULL,
        quantity INTEGER DEFAULT 0,
        reference_type TEXT,
        reference_id INTEGER,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_number TEXT NOT NULL,
        quotation_id INTEGER,
        client_id INTEGER,
        name TEXT,
        description TEXT,
        status TEXT DEFAULT 'Pendiente',
        technical_status TEXT DEFAULT 'Pendiente',
        installation_date TEXT,
        delivery_date TEXT,
        configuration_url TEXT,
        notes TEXT,
        checklist_required INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        sku TEXT,
        description TEXT NOT NULL,
        quantity INTEGER DEFAULT 1,
        unit_cost INTEGER DEFAULT 0,
        unit_price INTEGER DEFAULT 0,
        total_price INTEGER DEFAULT 0,
        reserved_quantity INTEGER DEFAULT 0,
        used_quantity INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checklist_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        service_type TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checklist_template_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER NOT NULL,
        item_order INTEGER DEFAULT 1,
        item_text TEXT NOT NULL,
        is_required INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_checklists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        template_id INTEGER,
        status TEXT DEFAULT 'Pendiente',
        completed_at TEXT,
        completed_by TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_checklist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_checklist_id INTEGER NOT NULL,
        item_text TEXT NOT NULL,
        is_required INTEGER DEFAULT 1,
        is_checked INTEGER DEFAULT 0,
        checked_at TEXT,
        evidence_note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchase_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_name TEXT,
        purchase_date TEXT,
        shipping_cost INTEGER DEFAULT 0,
        customs_cost INTEGER DEFAULT 0,
        other_costs INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchase_batch_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL,
        product_sku TEXT NOT NULL,
        quantity INTEGER DEFAULT 1,
        unit_price INTEGER DEFAULT 0,
        landed_cost INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tools_assets (
        asset_id TEXT PRIMARY KEY,
        tool_name TEXT NOT NULL,
        category TEXT DEFAULT 'Herramienta',
        provider TEXT,
        quantity INTEGER DEFAULT 1,
        cost_unit INTEGER DEFAULT 0,
        purchase_date TEXT DEFAULT '',
        useful_life_months INTEGER DEFAULT 12,
        monthly_cost INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Activa',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_name_unique ON suppliers(name)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_supplies_desc_unique ON supplies_catalog(description)")
    conn.commit()
    ensure_column(conn, "inventory", "stock_reserved", "INTEGER DEFAULT 0")
    ensure_column(conn, "inventory", "average_landed_cost", "INTEGER DEFAULT 0")
    ensure_tools_assets_schema(conn)

    cur.execute("SELECT COUNT(*) FROM checklist_templates")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO checklist_templates (name, description, service_type) VALUES (?, ?, ?)", (
            "Entrega Domótica Abaroa Smart",
            "Checklist base para cierre y entrega profesional de proyectos.",
            "domotica"
        ))
        template_id = cur.lastrowid
        default_items = [
            "¿Se verificó la carga de los automáticos (RIC)?",
            "¿Los dispositivos Zigbee tienen señal estable?",
            "¿El cliente tiene la app configurada en su móvil?",
            "¿Se probó encendido y apagado manual y desde la app?",
            "¿Se dejó respaldo o enlace de configuración del sistema?",
            "¿Se explicó operación básica y garantía al cliente?"
        ]
        for idx, item in enumerate(default_items, start=1):
            cur.execute(
                "INSERT INTO checklist_template_items (template_id, item_order, item_text, is_required) VALUES (?, ?, ?, 1)",
                (template_id, idx, item)
            )
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM vendors")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO vendors (name, email, phone, role) VALUES (?, ?, ?, ?)", ("Abaroa Smart", "", "", "Ventas"))

    cur.execute("SELECT COUNT(*) FROM suppliers")
    if cur.fetchone()[0] == 0:
        providers = sorted({str(r[9]).strip() for r in SEED_INVENTORY if str(r[9]).strip()})
        for p in providers:
            cur.execute("INSERT OR IGNORE INTO suppliers (name) VALUES (?)", (p,))
    cur.execute("SELECT COUNT(*) FROM inventory")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO inventory (
                sku, description, category, protocol, stock_initial, stock_current,
                cost_unit, margin_pct, sale_price, provider, is_service, stock_min
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, SEED_INVENTORY)
    conn.commit()
    conn.close()


def recalc_all_sale_prices():
    conn = get_conn()
    rows = conn.execute("SELECT sku, cost_unit, margin_pct FROM inventory").fetchall()
    for row in rows:
        sale_price = calc_sale_price(row["cost_unit"] or 0, row["margin_pct"] or 0)
        conn.execute("UPDATE inventory SET sale_price = ? WHERE sku = ?", (int(sale_price), row["sku"]))
    conn.commit()
    conn.close()

def recalc_stock():
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT sku, stock_initial, is_service FROM inventory").fetchall()
    for row in items:
        sku = row["sku"]
        if row["is_service"]:
            cur.execute("UPDATE inventory SET stock_current = 0, stock_reserved = 0 WHERE sku = ?", (sku,))
            continue

        used_qty = cur.execute("""
            SELECT COALESCE(SUM(used_quantity), 0)
            FROM project_items
            WHERE sku = ? AND item_type IN ('producto','kit_component')
        """, (sku,)).fetchone()[0]

        reserved_qty = cur.execute("""
            SELECT COALESCE(SUM(reserved_quantity), 0)
            FROM project_items
            WHERE sku = ? AND item_type IN ('producto','kit_component')
        """, (sku,)).fetchone()[0]

        stock_initial = int(row["stock_initial"] or 0)
        stock_current = max(stock_initial - int(used_qty or 0), 0)
        stock_reserved = min(max(int(reserved_qty or 0), 0), stock_current)
        cur.execute(
            "UPDATE inventory SET stock_current = ?, stock_reserved = ? WHERE sku = ?",
            (stock_current, stock_reserved, sku)
        )
    conn.commit()
    conn.close()

def calc_sale_price(cost_unit, margin_pct):
    return int(round(float(cost_unit) * (1 + float(margin_pct) / 100), 0))

def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"abaroa_smart_erp_backup_{timestamp}.db"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, backup_path)
    return backup_path

def export_table(table_name):
    df = get_df(f"SELECT * FROM {table_name}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = EXPORT_DIR / f"{table_name}_{timestamp}.csv"
    xlsx_path = EXPORT_DIR / f"{table_name}_{timestamp}.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    return csv_path, xlsx_path

def add_installation(client_id, install_date, sku, description, serial_number, location, notes, warranty_months):
    conn = get_conn()
    q(conn, """
        INSERT INTO installations (client_id, install_date, sku, description, serial_number, location, notes, warranty_months)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (client_id, install_date, sku, description, serial_number, location, notes, warranty_months))
    conn.close()

def save_quote(quote_number, quote_date, client_id, vendor_id, validity_days, status, notes, product_lines, service_lines, kit_lines, supply_lines):
    subtotal_products = int(sum(line["line_total"] for line in product_lines))
    subtotal_services = int(sum(line["line_total"] for line in service_lines))
    subtotal_kits = int(sum(line["line_total"] for line in kit_lines))
    subtotal_supplies = int(sum(line["line_total"] for line in supply_lines))
    vat_products = int(round((subtotal_products + subtotal_kits + subtotal_supplies) * IVA_RATE, 0))
    total = int(subtotal_products + subtotal_services + subtotal_kits + subtotal_supplies + vat_products)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO quotes (
            quote_number, quote_date, client_id, vendor_id, validity_days, status, notes,
            subtotal_products, subtotal_services_exempt, vat_products, total
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quote_number, quote_date, client_id, vendor_id, int(validity_days), status, notes,
        subtotal_products + subtotal_kits + subtotal_supplies, subtotal_services, vat_products, total
    ))
    quote_id = cur.lastrowid
    for line in product_lines:
        cur.execute("""
            INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt)
            VALUES (?, 'producto', ?, ?, ?, ?, ?, 0)
        """, (quote_id, line["sku"], line["description"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    for line in service_lines:
        cur.execute("""
            INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt)
            VALUES (?, 'servicio', ?, ?, ?, ?, ?, 1)
        """, (quote_id, line["sku"], line["description"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    for line in supply_lines:
        cur.execute("""
            INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt)
            VALUES (?, 'insumo', ?, ?, ?, ?, ?, 0)
        """, (quote_id, line["sku"], line["description"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    for line in kit_lines:
        cur.execute("""
            INSERT INTO quote_items (quote_id, item_type, sku, description, quantity, unit_price, line_total, vat_exempt)
            VALUES (?, 'kit', ?, ?, ?, ?, ?, 0)
        """, (quote_id, line["code"], line["name"], int(line["quantity"]), int(line["unit_price"]), int(line["line_total"])))
    conn.commit()
    conn.close()
    recalc_stock()
    return quote_id, total


def create_warranty_for_sale(sale_id, client_id, install_date=None, warranty_months=6, notes="Garantía automática"):
    install_date = install_date or date.today().isoformat()
    expiry_date = (datetime.fromisoformat(install_date).date() + timedelta(days=30*int(warranty_months))).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    exists = cur.execute("SELECT id FROM warranties WHERE sale_id = ?", (sale_id,)).fetchone()
    if exists:
        conn.close()
        return
    cur.execute("""
        INSERT INTO warranties (client_id, sale_id, install_date, warranty_months, expiry_date, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (client_id, sale_id, install_date, int(warranty_months), expiry_date, "Vigente", notes))
    conn.commit()
    conn.close()

def load_quote_context(quote_id):
    header_df = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, q.status, q.notes, q.total, q.subtotal_products, q.subtotal_services_exempt, q.vat_products,
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
    items_df = get_df("""
        SELECT item_type, sku, description, quantity, unit_price, line_total
        FROM quote_items
        WHERE quote_id = ?
        ORDER BY id
    """, (quote_id,))
    product_lines = []
    service_lines = []
    kit_lines = []
    supply_lines = []
    for _, r in items_df.iterrows():
        item = {"sku": r["sku"], "description": r["description"], "quantity": int(r["quantity"]), "unit_price": int(r["unit_price"]), "line_total": int(r["line_total"])}
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
    client_row = {"name": h.get("client_name",""), "phone": h.get("phone",""), "email": h.get("email",""), "address": h.get("address","")}
    return {
        "header": h,
        "client_row": client_row,
        "vendor_name": h.get("vendor_name",""),
        "product_lines": product_lines,
        "service_lines": service_lines,
        "kit_lines": kit_lines,
        "supply_lines": supply_lines,
    }

def duplicate_quote(quote_id):
    ctx = load_quote_context(quote_id)
    if not ctx:
        return False, "Cotización no encontrada."
    h = ctx["header"]
    new_number = f"COP-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    new_id, total_saved = save_quote(
        new_number,
        date.today().isoformat(),
        int(h["client_id"]),
        None,
        10,
        "Borrador",
        h.get("notes",""),
        ctx["product_lines"],
        ctx["service_lines"],
        ctx["kit_lines"],
        ctx["supply_lines"],
    )
    return True, f"Cotización duplicada: {new_number} (ID {new_id})"
def delete_quote(quote_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM quote_items WHERE quote_id = ?", (quote_id,))
    cur.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    conn.close()
    recalc_stock()

def convert_quote_to_sale(quote_id):
    conn = get_conn()
    cur = conn.cursor()
    quote = cur.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    if not quote:
        conn.close()
        return False, "Cotización no encontrada."
    product_cost = cur.execute("""
        SELECT COALESCE(SUM(qi.quantity * inv.cost_unit), 0)
        FROM quote_items qi
        LEFT JOIN inventory inv ON inv.sku = qi.sku
        WHERE qi.quote_id = ? AND qi.item_type = 'producto'
    """, (quote_id,)).fetchone()[0]
    kit_cost = cur.execute("""
        SELECT COALESCE(SUM(qi.quantity * ki.quantity * inv.cost_unit), 0)
        FROM quote_items qi
        JOIN kits k ON k.code = qi.sku
        JOIN kit_items ki ON ki.kit_id = k.id
        JOIN inventory inv ON inv.sku = ki.sku
        WHERE qi.quote_id = ? AND qi.item_type = 'kit'
    """, (quote_id,)).fetchone()[0]
    supplies_cost = cur.execute("""
        SELECT COALESCE(SUM(qi.line_total), 0)
        FROM quote_items qi
        WHERE qi.quote_id = ? AND qi.item_type = 'insumo'
    """, (quote_id,)).fetchone()[0]
    material_cost = int(product_cost or 0) + int(kit_cost or 0) + int(supplies_cost or 0)
    total = int(quote["total"] or 0)
    gross_margin = int(round(total - material_cost, 0))
    gross_margin_pct = round((gross_margin / total), 4) if total else 0
    existing_sale = cur.execute("SELECT id FROM sales WHERE quote_id=? ORDER BY id DESC LIMIT 1", (quote_id,)).fetchone()
    if existing_sale:
        sale_id = int(existing_sale["id"])
        cur.execute("UPDATE sales SET sale_date=?, client_id=?, total=?, material_cost=?, gross_margin=?, gross_margin_pct=? WHERE id=?", (date.today().isoformat(), quote["client_id"], total, material_cost, gross_margin, gross_margin_pct, sale_id))
    else:
        cur.execute("""
            INSERT INTO sales (sale_date, client_id, quote_id, total, material_cost, gross_margin, gross_margin_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (date.today().isoformat(), quote["client_id"], quote_id, total, material_cost, gross_margin, gross_margin_pct))
        sale_id = cur.lastrowid
    advance = int(round(total * 0.5, 0))
    balance = int(total - advance)
    existing_billing = cur.execute("SELECT id FROM billing WHERE sale_id=? ORDER BY id DESC LIMIT 1", (sale_id,)).fetchone()
    if existing_billing:
        cur.execute("UPDATE billing SET client_id=?, total=?, advance_50=?, balance_50=?, payment_status=? WHERE id=?", (quote["client_id"], total, advance, balance, "Anticipo 50%", int(existing_billing["id"])))
    else:
        cur.execute("""
            INSERT INTO billing (sale_id, client_id, total, advance_50, balance_50, payment_status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sale_id, quote["client_id"], total, advance, balance, "Anticipo 50%"))
    cur.execute("UPDATE quotes SET status = 'Vendida' WHERE id = ?", (quote_id,))
    conn.commit()
    conn.close()
    create_warranty_for_sale(sale_id, quote["client_id"])
    recalc_stock()
    return True, f"Venta #{sale_id} creada desde cotización #{quote_id}."

def kit_sale_price(kit_id):
    conn = get_conn()
    row = conn.execute("SELECT sale_price FROM kits WHERE id = ?", (kit_id,)).fetchone()
    conn.close()
    return int(row["sale_price"] or 0) if row else 0

def kit_components_df(kit_id):
    return get_df("""
        SELECT ki.sku, inv.description, ki.quantity, inv.stock_current, inv.sale_price, inv.cost_unit
        FROM kit_items ki
        LEFT JOIN inventory inv ON inv.sku = ki.sku
        WHERE ki.kit_id = ?
        ORDER BY ki.id
    """, (kit_id,))

def add_wo_item(work_order_id, sku, description, quantity, cost_unit):
    conn = get_conn()
    line_cost = int(quantity) * int(cost_unit)
    q(conn, """
        INSERT INTO work_order_items (work_order_id, sku, description, quantity, cost_unit, line_cost)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (work_order_id, sku, description, int(quantity), int(cost_unit), int(line_cost)))
    conn.close()


def calc_monthly_tool_cost(cost_unit, quantity, useful_life_months):
    qty = max(int(quantity or 0), 1)
    life = max(int(useful_life_months or 0), 1)
    total = int(cost_unit or 0) * qty
    return int(round(total / life, 0))


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
        provider = str(row.get("provider", "") or "").strip()
        quantity = int(row.get("quantity", 1) or 1)
        cost_unit = int(row.get("cost_unit", 0) or 0)
        category = str(row.get("category", "Herramienta") or "Herramienta").strip()
        purchase_date = str(row.get("purchase_date", "") or "").strip()
        useful_life_months = int(row.get("useful_life_months", 12) or 12)
        status = str(row.get("status", "Activa") or "Activa").strip()
        notes = str(row.get("notes", "") or "").strip()
        monthly_cost = calc_monthly_tool_cost(cost_unit, quantity, useful_life_months)
        cur.execute("""
            INSERT INTO tools_assets (
                asset_id, tool_name, category, provider, quantity, cost_unit,
                purchase_date, useful_life_months, monthly_cost, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                tool_name=excluded.tool_name,
                category=excluded.category,
                provider=excluded.provider,
                quantity=excluded.quantity,
                cost_unit=excluded.cost_unit,
                purchase_date=excluded.purchase_date,
                useful_life_months=excluded.useful_life_months,
                monthly_cost=excluded.monthly_cost,
                status=excluded.status,
                notes=excluded.notes
        """, (
            asset_id, tool_name, category, provider, quantity, cost_unit,
            purchase_date, useful_life_months, monthly_cost, status, notes
        ))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


# ── Utilidades de cotización ──────────────────────────────────────────────────
def merge_lines(lines):
    """Fusiona líneas con mismo SKU sumando cantidades."""
    merged = {}
    for l in lines:
        sku = l.get("sku")
        if not sku:
            continue
        if sku in merged:
            merged[sku]["quantity"] += l.get("quantity", 1)
        else:
            merged[sku] = l.copy()
    return list(merged.values())


def validate_price(p):
    return p is not None and p > 0


def fmt_df_money(df, cols):
    """Formatea columnas numéricas de precios con la función money() para display."""
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(money)
    return df


# ── Inicio de la aplicación ───────────────────────────────────────────────────
apply_theme()
init_db()
ensure_app_settings()
migrate_inventory_skus()
normalize_services_and_seed_abaroa_kits()
remove_duplicate_rows()
recalc_all_sale_prices()
recalc_stock()



def inject_sidebar_final_css(sidebar_open=True):
    if sidebar_open:
        st.markdown("""
        <style>
        [data-testid="collapsedControl"] { display: none !important; }
        section[data-testid="stSidebar"] {
            width: 18rem !important;
            min-width: 18rem !important;
            transform: translateX(0) !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        .block-container {
            max-width: 100% !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        [data-testid="collapsedControl"] { display: none !important; }
        section[data-testid="stSidebar"] {
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: hidden !important;
            transform: translateX(-100%) !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }
        .block-container {
            max-width: 100% !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            margin-left: 0 !important;
            padding-left: 0 !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        </style>
        """, unsafe_allow_html=True)


def render_app_header(current_tab):
    if "top_nav_current" not in st.session_state:
        st.session_state["top_nav_current"] = current_tab if current_tab in ["Inicio", "Flujo Guiado", "Inventario", "Cotización", "OT", "Proyectos"] else "Inicio"

    header_left, header_search, header_actions, header_status, header_user = st.columns([1.0, 4.2, 5.4, 0.8, 0.8])
    with header_left:
        sidebar_label = "✕" if st.session_state.get("sidebar_open", True) else "☰"
        if st.button(sidebar_label, key="toggle_sidebar", use_container_width=True):
            st.session_state["sidebar_open"] = not st.session_state.get("sidebar_open", True)
            st.rerun()
    with header_search:
        st.text_input(
            "Buscar",
            value=st.session_state.get("global_search", ""),
            key="global_search",
            label_visibility="collapsed",
            placeholder="Buscar clientes, SKU, cotizaciones, OT...",
        )
    with header_actions:
        quick_tabs = [
            ("Inicio", "Inicio"),
            ("Flujo Guiado", "Flujo"),
            ("Inventario", "Inventario"),
            ("Cotización", "Cotizar"),
            ("OT", "OT"),
            ("Proyectos", "Proyectos"),
        ]
        qa1, qa2, qa3, qa4, qa5 = st.columns(5)
        for col, (value, label) in zip([qa1, qa2, qa3, qa4, qa5], quick_tabs):
            with col:
                btn_type = "primary" if st.session_state.get("current_tab") == value else "secondary"
                if st.button(label, key=f"header_quick_{value}", use_container_width=True, type=btn_type):
                    st.session_state["current_tab"] = value
                    st.session_state["top_nav_current"] = value
                    st.rerun()

    with header_status:
        alerts = get_alerts_data()
        bell_label = f"🔔 {len(alerts)}" if alerts else "🔔"
        with st.popover(bell_label, use_container_width=True):
            st.markdown("### Alertas del sistema")
            if alerts:
                for alert in alerts:
                    if alert['level'] == 'warning':
                        st.warning(f"**{alert['title']}**\n\n{alert['detail']}")
                    else:
                        st.info(f"**{alert['title']}**\n\n{alert['detail']}")
            else:
                st.success("Sin alertas por revisar.")
            if st.button("Abrir Respaldos", key="alerts_open_backup", use_container_width=True):
                st.session_state["current_tab"] = "Respaldo y Restauración"
                st.rerun()
    with header_user:
        with st.popover("👤", use_container_width=True):
            st.markdown("### Administración")
            if admin_logged_in():
                st.success(f"Sesión iniciada como **{get_setting('admin_username', 'admin')}**")
                if st.button("Abrir panel de administración", key="popover_open_admin", use_container_width=True):
                    st.session_state["current_tab"] = "Administración"
                    st.rerun()
                if st.button("Abrir respaldos", key="popover_open_backups", use_container_width=True):
                    st.session_state["current_tab"] = "Respaldo y Restauración"
                    st.rerun()
                if st.button("Cerrar sesión", key="popover_admin_logout", use_container_width=True):
                    st.session_state["admin_logged_in"] = False
                    st.rerun()
            else:
                pop_user = st.text_input("Usuario", key="popover_admin_user")
                pop_pass = st.text_input("Contraseña", type="password", key="popover_admin_pass")
                if st.button("Ingresar", key="popover_admin_login", use_container_width=True):
                    if verify_admin_credentials(pop_user, pop_pass):
                        st.session_state["admin_logged_in"] = True
                        st.success("Acceso concedido.")
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
                st.caption("Credenciales iniciales: admin / admin123")

    st.markdown(
        f"""
        <div class="app-shell-header">
            <div class="title">Abaroa Smart ERP</div>
            <div class="subtitle">Vista {current_tab} · Panel comercial, técnico e inventario con navegación persistente, accesos rápidos superiores y sidebar recuperable.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_final_sidebar():
    if "current_tab" not in st.session_state:
        st.session_state["current_tab"] = "Inicio"
    if "sidebar_open" not in st.session_state:
        st.session_state["sidebar_open"] = True

    nav = {
        "Principal": [("Inicio", "🏠 Inicio"), ("Flujo Guiado", "🧭 Flujo Guiado"), ("Buscador", "🔎 Buscador")],
        "Operación": [("Proyectos", "🛠️ Proyectos"), ("OT", "📋 Órdenes de Trabajo"), ("Garantías", "🛡️ Garantías")],
        "Comercial": [("Cotización", "🧾 Cotización"), ("Historial Cotizaciones", "📚 Historial"), ("Ventas", "💳 Ventas"), ("Facturación", "🧮 Facturación")],
        "Inventario": [("Inventario", "📦 Inventario"), ("Herramientas", "🛠️ Herramientas"), ("Insumos", "🧰 Insumos"), ("Kits", "🧩 Kits"), ("Proveedores", "🚚 Proveedores")],
        "CRM": [("Clientes", "👤 Clientes"), ("Vendedores", "🤝 Vendedores")],
        "Sistema": [("Respaldo y Restauración", "⚙️ Respaldos"), ("Administración", "🔐 Administración")],
    }

    inject_sidebar_final_css(st.session_state.get("sidebar_open", True))
    render_app_header(st.session_state["current_tab"])

    if st.session_state.get("sidebar_open", True):
        with st.sidebar:
            st.markdown(
                """
                <div class="sidebar-brand">
                    <div class="sidebar-brand-title">Abaroa Smart</div>
                    <div class="sidebar-brand-sub">ERP operativo local</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("🏠 Volver al inicio", key="sidebar_go_home", use_container_width=True, type="primary"):
                st.session_state["current_tab"] = "Inicio"
                st.session_state["top_nav_current"] = "Inicio"
                st.rerun()

            for section, items in nav.items():
                st.markdown(f"<div class='sidebar-section-title'>{section}</div>", unsafe_allow_html=True)
                for value, label in items:
                    button_type = "primary" if st.session_state.get("current_tab") == value else "secondary"
                    if st.button(label, key=f"nav_btn_{value}", use_container_width=True, type=button_type):
                        st.session_state["current_tab"] = value
                        if value in ["Inicio", "Flujo Guiado", "Buscador", "Inventario", "Cotización", "OT", "Proyectos"]:
                            st.session_state["top_nav_current"] = value
                        st.rerun()

    return st.session_state["current_tab"]


def dashboard_kpi_card(label, value, delta=""):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-delta">{delta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def landed_cost_per_unit(unit_price, customs_cost, shipping_cost, other_costs, quantity):
    quantity = max(int(quantity or 0), 1)
    total = int(unit_price or 0) * quantity + int(customs_cost or 0) + int(shipping_cost or 0) + int(other_costs or 0)
    return int(round(total / quantity, 0))


def project_exists_for_quote(quote_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM projects WHERE quotation_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1", (quote_id,)).fetchone()
    conn.close()
    return int(row["id"]) if row else None


def create_project_checklist(project_id, template_id=None):
    conn = get_conn()
    cur = conn.cursor()
    if template_id is None:
        tpl = cur.execute("SELECT id FROM checklist_templates WHERE is_active = 1 ORDER BY id LIMIT 1").fetchone()
        template_id = int(tpl["id"]) if tpl else None
    cur.execute("INSERT INTO project_checklists (project_id, template_id, status) VALUES (?, ?, 'Pendiente')", (project_id, template_id))
    checklist_id = cur.lastrowid
    if template_id:
        items = cur.execute("SELECT item_text, is_required FROM checklist_template_items WHERE template_id = ? ORDER BY item_order, id", (template_id,)).fetchall()
        for item in items:
            cur.execute(
                "INSERT INTO project_checklist_items (project_checklist_id, item_text, is_required) VALUES (?, ?, ?)",
                (checklist_id, item["item_text"], int(item["is_required"] or 0))
            )
    conn.commit()
    conn.close()
    return checklist_id


def reserve_inventory_for_project(project_id):
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT * FROM project_items WHERE project_id = ?", (project_id,)).fetchall()
    for item in items:
        if item["item_type"] not in ("producto", "kit_component"):
            continue
        sku = item["sku"]
        qty = int(item["quantity"] or 0)
        inv = cur.execute("SELECT stock_current, stock_reserved FROM inventory WHERE sku = ?", (sku,)).fetchone()
        if not inv:
            continue
        stock_current = int(inv["stock_current"] or 0)
        stock_reserved = int(inv["stock_reserved"] or 0)
        available = max(stock_current - stock_reserved, 0)
        reserve_qty = min(qty, available)
        if reserve_qty <= 0:
            continue
        cur.execute("UPDATE inventory SET stock_reserved = COALESCE(stock_reserved,0) + ? WHERE sku = ?", (reserve_qty, sku))
        cur.execute("UPDATE project_items SET reserved_quantity = COALESCE(reserved_quantity,0) + ? WHERE id = ?", (reserve_qty, item["id"]))
        cur.execute(
            "INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?, 'RESERVE', ?, 'project', ?, ?)",
            (sku, reserve_qty, project_id, f"Reserva por proyecto #{project_id}")
        )
    conn.commit()
    conn.close()


def release_reserved_stock_for_project(project_id):
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT id, sku, reserved_quantity FROM project_items WHERE project_id = ?", (project_id,)).fetchall()
    for item in items:
        qty = int(item["reserved_quantity"] or 0)
        if not item["sku"] or qty <= 0:
            continue
        cur.execute("UPDATE inventory SET stock_reserved = MAX(COALESCE(stock_reserved,0) - ?, 0) WHERE sku = ?", (qty, item["sku"]))
        cur.execute("UPDATE project_items SET reserved_quantity = 0 WHERE id = ?", (item["id"],))
        cur.execute(
            "INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?, 'RELEASE_RESERVE', ?, 'project', ?, ?)",
            (item["sku"], qty, project_id, f"Liberación de reserva proyecto #{project_id}")
        )
    conn.commit()
    conn.close()


def consume_inventory_for_project(project_id):
    conn = get_conn()
    cur = conn.cursor()
    items = cur.execute("SELECT id, sku, quantity, reserved_quantity, used_quantity FROM project_items WHERE project_id = ?", (project_id,)).fetchall()
    for item in items:
        sku = item["sku"]
        if not sku:
            continue
        target_qty = int(item["quantity"] or 0)
        already_used = int(item["used_quantity"] or 0)
        consume_qty = max(target_qty - already_used, 0)
        if consume_qty <= 0:
            continue
        inv = cur.execute("SELECT stock_current, stock_reserved FROM inventory WHERE sku = ?", (sku,)).fetchone()
        if not inv:
            continue
        stock_current = int(inv["stock_current"] or 0)
        stock_reserved = int(inv["stock_reserved"] or 0)
        consume_qty = min(consume_qty, stock_current)
        release_qty = min(consume_qty, stock_reserved)
        cur.execute(
            "UPDATE inventory SET stock_current = MAX(COALESCE(stock_current,0) - ?, 0), stock_reserved = MAX(COALESCE(stock_reserved,0) - ?, 0) WHERE sku = ?",
            (consume_qty, release_qty, sku)
        )
        cur.execute(
            "UPDATE project_items SET used_quantity = COALESCE(used_quantity,0) + ?, reserved_quantity = MAX(COALESCE(reserved_quantity,0) - ?, 0) WHERE id = ?",
            (consume_qty, release_qty, item["id"])
        )
        cur.execute(
            "INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?, 'PROJECT_CONSUMPTION', ?, 'project', ?, ?)",
            (sku, consume_qty, project_id, f"Consumo real proyecto #{project_id}")
        )
    conn.commit()
    conn.close()


def sync_project_item_usage(item_id, new_used_quantity):
    conn = get_conn()
    cur = conn.cursor()
    item = cur.execute(
        "SELECT id, project_id, sku, quantity, reserved_quantity, used_quantity, item_type FROM project_items WHERE id = ?",
        (item_id,)
    ).fetchone()
    if not item:
        conn.close()
        return False, "Ítem no encontrado."
    if item["item_type"] not in ("producto", "kit_component", "insumo"):
        cur.execute("UPDATE project_items SET used_quantity = ? WHERE id = ?", (int(max(new_used_quantity, 0)), item_id))
        conn.commit()
        conn.close()
        return True, "Uso actualizado."
    target_qty = max(0, min(int(new_used_quantity or 0), int(item["quantity"] or 0)))
    current_used = int(item["used_quantity"] or 0)
    delta = target_qty - current_used
    if delta == 0:
        conn.close()
        return True, "Sin cambios en la cantidad usada."
    sku = item["sku"]
    inv = cur.execute("SELECT stock_current, stock_reserved FROM inventory WHERE sku = ?", (sku,)).fetchone() if sku else None
    if not inv:
        cur.execute("UPDATE project_items SET used_quantity = ? WHERE id = ?", (target_qty, item_id))
        conn.commit()
        conn.close()
        return True, "Uso actualizado sin impacto de inventario."
    stock_current = int(inv["stock_current"] or 0)
    stock_reserved = int(inv["stock_reserved"] or 0)
    if delta > 0:
        consume_qty = min(delta, stock_current)
        release_qty = min(consume_qty, stock_reserved, max(int(item["reserved_quantity"] or 0), 0))
        cur.execute(
            "UPDATE inventory SET stock_current = MAX(COALESCE(stock_current,0) - ?, 0), stock_reserved = MAX(COALESCE(stock_reserved,0) - ?, 0) WHERE sku = ?",
            (consume_qty, release_qty, sku)
        )
        cur.execute(
            "UPDATE project_items SET used_quantity = COALESCE(used_quantity,0) + ?, reserved_quantity = MAX(COALESCE(reserved_quantity,0) - ?, 0) WHERE id = ?",
            (consume_qty, release_qty, item_id)
        )
        cur.execute(
            "INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?, 'PROJECT_CONSUMPTION', ?, 'project', ?, ?)",
            (sku, consume_qty, item["project_id"], f"Consumo manual proyecto #{item['project_id']}")
        )
    else:
        restore_qty = abs(delta)
        cur.execute(
            "UPDATE inventory SET stock_current = COALESCE(stock_current,0) + ?, stock_reserved = COALESCE(stock_reserved,0) + ? WHERE sku = ?",
            (restore_qty, restore_qty, sku)
        )
        cur.execute(
            "UPDATE project_items SET used_quantity = MAX(COALESCE(used_quantity,0) - ?, 0), reserved_quantity = COALESCE(reserved_quantity,0) + ? WHERE id = ?",
            (restore_qty, restore_qty, item_id)
        )
        cur.execute(
            "INSERT INTO inventory_movements (sku, movement_type, quantity, reference_type, reference_id, notes) VALUES (?, 'USAGE_ADJUSTMENT', ?, 'project', ?, ?)",
            (sku, restore_qty, item["project_id"], f"Ajuste manual de uso proyecto #{item['project_id']}")
        )
    conn.commit()
    conn.close()
    return True, "Uso actualizado correctamente."


def validate_project_completion(project_id):
    conn = get_conn()
    checklist = conn.execute("SELECT id FROM project_checklists WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    if not checklist:
        conn.close()
        return False, "Proyecto sin checklist."
    pending = conn.execute(
        "SELECT COUNT(*) AS c FROM project_checklist_items WHERE project_checklist_id = ? AND is_required = 1 AND COALESCE(is_checked,0) = 0",
        (int(checklist["id"]),)
    ).fetchone()
    conn.close()
    if int(pending["c"] or 0) > 0:
        return False, "Checklist incompleto."
    return True, "Checklist completo."


def create_project_from_quote(quote_id, installation_date=None, configuration_url="", notes=""):
    existing = project_exists_for_quote(quote_id)
    if existing:
        return False, existing, "La cotización ya tiene un proyecto asociado."
    conn = get_conn()
    cur = conn.cursor()
    quote = cur.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    if not quote:
        conn.close()
        return False, None, "No se encontró la cotización."
    client = cur.execute("SELECT * FROM clients WHERE id = ?", (quote["client_id"],)).fetchone()
    quote_items = cur.execute("SELECT * FROM quote_items WHERE quote_id = ? ORDER BY id", (quote_id,)).fetchall()
    project_number = f"PROY-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    project_name = f"{client['name'] if client else 'Cliente'} · {quote['quote_number']}"
    cur.execute(
        """INSERT INTO projects (
            project_number, quotation_id, client_id, name, description, status, technical_status,
            installation_date, configuration_url, notes, checklist_required, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'Aprobado', 'Pendiente', ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
        (project_number, quote_id, quote["client_id"], project_name, f"Proyecto generado desde cotización {quote['quote_number']}", installation_date, configuration_url, notes)
    )
    project_id = cur.lastrowid
    for item in quote_items:
        item_type = item["item_type"]
        if item_type == "kit":
            comps = cur.execute("SELECT ki.sku, ki.quantity, i.description, i.cost_unit FROM kit_items ki LEFT JOIN inventory i ON i.sku = ki.sku WHERE ki.kit_id = (SELECT id FROM kits WHERE code = ? LIMIT 1)", (item["sku"],)).fetchall()
            for comp in comps:
                qty = int(item["quantity"] or 0) * int(comp["quantity"] or 0)
                unit_cost = int(comp["cost_unit"] or 0)
                cur.execute(
                    """INSERT INTO project_items (project_id, item_type, sku, description, quantity, unit_cost, unit_price, total_price)
                    VALUES (?, 'kit_component', ?, ?, ?, ?, 0, 0)""",
                    (project_id, comp["sku"], comp["description"] or comp["sku"], qty, unit_cost)
                )
        else:
            inv = cur.execute("SELECT cost_unit FROM inventory WHERE sku = ?", (item["sku"],)).fetchone()
            unit_cost = int(inv["cost_unit"] or 0) if inv else 0
            cur.execute(
                """INSERT INTO project_items (project_id, item_type, sku, description, quantity, unit_cost, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (project_id, item_type, item["sku"], item["description"], int(item["quantity"] or 0), unit_cost, int(item["unit_price"] or 0), int(item["line_total"] or 0))
            )
    cur.execute("UPDATE quotes SET status = 'Aprobada' WHERE id = ?", (quote_id,))
    conn.commit()
    conn.close()
    create_project_checklist(project_id)
    reserve_inventory_for_project(project_id)
    return True, project_id, f"Proyecto #{project_id} creado desde la cotización."





def initialize_workflow_state():
    defaults = {
        "workflow_active": False,
        "workflow_step": "cliente",
        "workflow_client_id": None,
        "workflow_quote_id": None,
        "workflow_project_id": None,
        "workflow_ot_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def workflow_go(step):
    st.session_state["workflow_active"] = True
    st.session_state["workflow_step"] = step
    st.session_state["current_tab"] = "Flujo Guiado"


def workflow_reset():
    for key, value in {
        "workflow_active": False,
        "workflow_step": "cliente",
        "workflow_client_id": None,
        "workflow_quote_id": None,
        "workflow_project_id": None,
        "workflow_ot_id": None,
    }.items():
        st.session_state[key] = value


def get_workflow_ot(project_id):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT wo.*
        FROM work_orders wo
        JOIN projects p ON p.quotation_id = wo.quote_id AND p.client_id = wo.client_id
        WHERE p.id = ?
        ORDER BY wo.id DESC
        LIMIT 1
        """,
        (project_id,)
    ).fetchone()
    conn.close()
    return row


def create_work_order_from_project(project_id, scheduled_date=None):
    conn = get_conn()
    cur = conn.cursor()
    project = cur.execute(
        """
        SELECT p.*, c.address AS client_address
        FROM projects p
        LEFT JOIN clients c ON c.id = p.client_id
        WHERE p.id = ?
        """,
        (project_id,)
    ).fetchone()
    if not project:
        conn.close()
        return False, None, "Proyecto no encontrado."
    existing = cur.execute(
        "SELECT id, ot_number FROM work_orders WHERE quote_id = ? AND client_id = ? ORDER BY id DESC LIMIT 1",
        (project["quotation_id"], project["client_id"])
    ).fetchone()
    if existing:
        conn.close()
        return True, int(existing["id"]), f"OT existente {existing['ot_number']}."
    ot_number = f"OT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    cur.execute(
        """
        INSERT INTO work_orders (
            ot_number, client_id, vendor_id, quote_id, status, scheduled_date, address,
            hours_work, labor_cost, travel_cost, extra_material_cost, notes
        ) VALUES (?, ?, ?, ?, 'Pendiente', ?, ?, 0, 0, 0, 0, ?)
        """,
        (
            ot_number,
            project["client_id"],
            None,
            project["quotation_id"],
            scheduled_date or project["installation_date"] or date.today().isoformat(),
            project["client_address"] or "",
            f"OT generada desde proyecto {project['project_number']}"
        )
    )
    ot_id = cur.lastrowid
    conn.commit()
    conn.close()
    return True, ot_id, f"OT {ot_number} creada correctamente."


def close_project_workflow(project_id):
    ok, msg = validate_project_completion(project_id)
    if not ok:
        return False, msg
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE projects SET status = 'Entregado', technical_status = 'Cerrado', delivery_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (date.today().isoformat(), project_id)
    )
    cur.execute(
        """
        UPDATE work_orders
        SET status = 'Cerrada'
        WHERE quote_id = (SELECT quotation_id FROM projects WHERE id = ?)
          AND client_id = (SELECT client_id FROM projects WHERE id = ?)
          AND COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso')
        """,
        (project_id, project_id)
    )
    conn.commit()
    conn.close()
    recalc_stock()
    return True, "Proyecto, acta y OT cerrados correctamente."


def render_workflow_progress():
    steps = [
        ("cliente", "Cliente"),
        ("cotizacion", "Cotización"),
        ("proyecto", "Proyecto"),
        ("ot", "OT"),
        ("cierre", "Acta / Cierre"),
    ]
    current = st.session_state.get("workflow_step", "cliente")
    current_index = next((idx for idx, row in enumerate(steps) if row[0] == current), 0)
    parts = []
    for idx, (key, label) in enumerate(steps, start=1):
        active = key == current
        done = (idx - 1) < current_index
        bg = "rgba(37,99,235,.22)" if active else ("rgba(34,197,94,.16)" if done else "rgba(148,163,184,.10)")
        color = "#e5e7eb" if active else ("#bbf7d0" if done else "#94a3b8")
        parts.append(f"<div style='padding:.55rem .8rem;border-radius:14px;background:{bg};color:{color};font-weight:700;'>Paso {idx} · {label}</div>")
    st.markdown(
        "<div style='display:flex;gap:.55rem;flex-wrap:wrap;margin:.4rem 0 1rem 0;'>" + "".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


initialize_workflow_state()

current_tab = render_final_sidebar()




if current_tab == "Flujo Guiado":
    st.subheader("Flujo Guiado")
    render_workflow_progress()

    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.markdown(
            """
            <div class="hero">
                <div class="status-pill">Asistente comercial + técnico</div>
                <h2 style="margin:.65rem 0 .35rem 0;">Recorrido guiado de operación</h2>
                <div style="color:#94a3b8; font-size:.95rem; max-width:880px;">
                    Este módulo te lleva paso a paso desde cliente y cotización hasta proyecto, OT y cierre técnico, sin abrir ventanas nuevas.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown("<div class='panel-card'><div class='panel-title'>Control rápido</div><div class='panel-subtitle'>Estado del flujo actual.</div></div>", unsafe_allow_html=True)
        st.write(f"Cliente ID: {st.session_state.get('workflow_client_id') or '-'}")
        st.write(f"Cotización ID: {st.session_state.get('workflow_quote_id') or '-'}")
        st.write(f"Proyecto ID: {st.session_state.get('workflow_project_id') or '-'}")
        st.write(f"OT ID: {st.session_state.get('workflow_ot_id') or '-'}")
        a1, a2 = st.columns(2)
        if a1.button("Reiniciar flujo", use_container_width=True):
            workflow_reset()
            st.rerun()
        if a2.button("Ir a cotización", use_container_width=True):
            st.session_state["current_tab"] = "Cotización"
            st.rerun()

    step = st.session_state.get("workflow_step", "cliente")

    if step == "cliente":
        clients_df = get_df("SELECT id, name, phone, email, address FROM clients ORDER BY name")
        if clients_df.empty:
            st.warning("No hay clientes cargados. Primero crea un cliente.")
            if st.button("Abrir módulo Clientes", type="primary"):
                st.session_state["current_tab"] = "Clientes"
                st.rerun()
        else:
            options = [f"{int(r['id'])} · {r['name']}" for _, r in clients_df.iterrows()]
            selected_cli = st.selectbox("Selecciona cliente para iniciar el flujo", options, key="workflow_client_selector")
            cli_id = int(selected_cli.split(" · ")[0])
            client_row = clients_df[clients_df["id"] == cli_id].iloc[0].to_dict()
            st.info(f"{client_row['name']} · {client_row.get('phone','') or '-'} · {client_row.get('email','') or '-'}")
            if st.button("Continuar a Cotización", type="primary"):
                st.session_state["workflow_client_id"] = cli_id
                workflow_go("cotizacion")
                st.rerun()

    elif step == "cotizacion":
        client_id = st.session_state.get("workflow_client_id")
        if not client_id:
            workflow_go("cliente")
            st.rerun()
        quotes_df = get_df(
            """
            SELECT q.id, q.quote_number, q.quote_date, q.status, q.total
            FROM quotes q
            WHERE q.client_id = ?
            ORDER BY q.id DESC
            """,
            (client_id,)
        )
        st.markdown("### 1) Crear o seleccionar cotización")
        left, right = st.columns([1.2, 1])
        with left:
            st.write("Puedes abrir el módulo Cotización para crear una nueva propuesta y luego volver aquí.")
            if st.button("Abrir módulo Cotización", type="primary", key="workflow_open_quote_module"):
                st.session_state["current_tab"] = "Cotización"
                st.rerun()
        with right:
            if quotes_df.empty:
                st.warning("Aún no existen cotizaciones para este cliente.")
            else:
                quote_options = [f"{int(r['id'])} · {r['quote_number']} · {r['status']} · {money(r['total'] or 0)}" for _, r in quotes_df.iterrows()]
                selected_quote = st.selectbox("Cotización disponible", quote_options, key="workflow_quote_selector")
                quote_id = int(selected_quote.split(" · ")[0])
                st.session_state["workflow_quote_id"] = quote_id
                st.caption("Usa una cotización existente o crea una nueva en el módulo comercial.")
                b1, b2 = st.columns(2)
                if b1.button("Continuar a Proyecto", type="primary"):
                    workflow_go("proyecto")
                    st.rerun()
                if b2.button("Volver", use_container_width=True):
                    workflow_go("cliente")
                    st.rerun()

    elif step == "proyecto":
        quote_id = st.session_state.get("workflow_quote_id")
        if not quote_id:
            workflow_go("cotizacion")
            st.rerun()
        existing_project_id = project_exists_for_quote(quote_id)
        if existing_project_id:
            st.session_state["workflow_project_id"] = existing_project_id
            st.success(f"Proyecto existente detectado: #{existing_project_id}")
        else:
            st.info("Aún no existe proyecto para esta cotización.")
            px1, px2, px3 = st.columns(3)
            install_date = px1.date_input("Fecha instalación", value=date.today(), key="workflow_install_date")
            config_url = px2.text_input("URL configuración", key="workflow_config_url")
            notes = px3.text_input("Notas proyecto", key="workflow_project_notes")
            if st.button("Crear proyecto desde cotización", type="primary"):
                ok, project_id, msg = create_project_from_quote(quote_id, installation_date=install_date.isoformat(), configuration_url=config_url.strip(), notes=notes.strip())
                if ok:
                    st.session_state["workflow_project_id"] = project_id
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

        project_id = st.session_state.get("workflow_project_id")
        if project_id:
            p_df = get_df("SELECT project_number, name, status, technical_status, installation_date FROM projects WHERE id = ?", (project_id,))
            if not p_df.empty:
                st.dataframe(p_df, use_container_width=True, hide_index=True)
            items_df = get_df(
                """
                SELECT item_type, sku, description, quantity, reserved_quantity, used_quantity
                FROM project_items
                WHERE project_id = ?
                ORDER BY id
                """,
                (project_id,)
            )
            if not items_df.empty:
                st.markdown("### Material planificado y uso real")
                st.dataframe(items_df, use_container_width=True, hide_index=True)
            p1, p2, p3 = st.columns(3)
            if p1.button("Abrir módulo Proyectos", use_container_width=True):
                st.session_state["current_tab"] = "Proyectos"
                st.rerun()
            if p2.button("Continuar a OT", type="primary", use_container_width=True):
                workflow_go("ot")
                st.rerun()
            if p3.button("Volver", use_container_width=True):
                workflow_go("cotizacion")
                st.rerun()

    elif step == "ot":
        project_id = st.session_state.get("workflow_project_id")
        if not project_id:
            workflow_go("proyecto")
            st.rerun()
        existing_ot = get_workflow_ot(project_id)
        if existing_ot:
            st.session_state["workflow_ot_id"] = int(existing_ot["id"])
            st.success(f"OT disponible: {existing_ot['ot_number']}")
            st.dataframe(pd.DataFrame([{
                "ID": int(existing_ot["id"]),
                "OT": existing_ot["ot_number"],
                "Estado": existing_ot["status"],
                "Fecha": existing_ot["scheduled_date"],
                "Dirección": existing_ot["address"],
            }]), use_container_width=True, hide_index=True)
        else:
            st.info("No existe OT para este proyecto.")
            ot_date = st.date_input("Fecha OT", value=date.today(), key="workflow_ot_date")
            if st.button("Crear OT desde proyecto", type="primary"):
                ok, ot_id, msg = create_work_order_from_project(project_id, ot_date.isoformat())
                if ok:
                    st.session_state["workflow_ot_id"] = ot_id
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)
        o1, o2, o3 = st.columns(3)
        if o1.button("Abrir módulo OT", use_container_width=True):
            st.session_state["current_tab"] = "OT"
            st.rerun()
        if o2.button("Continuar a Acta / Cierre", type="primary", use_container_width=True):
            workflow_go("cierre")
            st.rerun()
        if o3.button("Volver", use_container_width=True):
            workflow_go("proyecto")
            st.rerun()

    elif step == "cierre":
        project_id = st.session_state.get("workflow_project_id")
        if not project_id:
            workflow_go("proyecto")
            st.rerun()
        st.markdown("### Cierre técnico")
        valid, msg = validate_project_completion(project_id)
        if valid:
            st.success(msg)
        else:
            st.warning(msg)
        pdf_bytes = make_project_delivery_pdf(project_id)
        if pdf_bytes:
            st.download_button(
                "Descargar acta de entrega",
                data=pdf_bytes,
                file_name=f"acta_entrega_proyecto_{project_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        z1, z2, z3 = st.columns(3)
        if z1.button("Abrir módulo Proyectos", use_container_width=True):
            st.session_state["current_tab"] = "Proyectos"
            st.rerun()
        if z2.button("Cerrar proyecto y OT", type="primary", use_container_width=True):
            ok, close_msg = close_project_workflow(project_id)
            if ok:
                st.success(close_msg)
                workflow_reset()
                st.rerun()
            else:
                st.warning(close_msg)
        if z3.button("Volver", use_container_width=True):
            workflow_go("ot")
            st.rerun()


if current_tab == "Inicio":
    conn = get_conn()
    sales_total_row = conn.execute("SELECT COALESCE(SUM(total),0) AS total, COALESCE(SUM(material_cost),0) AS cost, COALESCE(SUM(gross_margin),0) AS margin, COALESCE(AVG(gross_margin_pct),0) AS avg FROM sales").fetchone()
    if int(sales_total_row["total"] or 0) > 0:
        total_sales = sales_total_row["total"]
        total_cost = sales_total_row["cost"]
        total_margin = sales_total_row["margin"]
        avg_margin = sales_total_row["avg"]
    else:
        # Dashboard operativo: si aún no se convirtió a venta, usa cotizaciones aceptadas/vendidas como venta comprometida.
        total_sales = conn.execute("SELECT COALESCE(SUM(total),0) FROM quotes WHERE COALESCE(status,'') IN ('Aprobada','Aprobado','Aceptada','Vendida','Facturada','Cerrada')").fetchone()[0]
        total_cost = conn.execute("""
            SELECT COALESCE(SUM(qi.quantity * COALESCE(inv.cost_unit,0)),0)
            FROM quote_items qi
            JOIN quotes q ON q.id = qi.quote_id
            LEFT JOIN inventory inv ON inv.sku = qi.sku
            WHERE COALESCE(q.status,'') IN ('Aprobada','Aprobado','Aceptada','Vendida','Facturada','Cerrada')
              AND qi.item_type IN ('producto','insumo')
        """).fetchone()[0]
        total_margin = int(total_sales or 0) - int(total_cost or 0)
        avg_margin = (float(total_margin) / float(total_sales)) if total_sales else 0
    low_stock = conn.execute("SELECT COUNT(*) FROM inventory WHERE COALESCE(is_service,0)=0 AND COALESCE(stock_min,0)>0 AND stock_current <= stock_min").fetchone()[0]
    open_ot = conn.execute("SELECT COUNT(*) FROM work_orders WHERE COALESCE(status,'Pendiente') IN ('Pendiente','Agendada','En ejecución','Abierta','En proceso')").fetchone()[0] + conn.execute("SELECT COUNT(*) FROM projects WHERE COALESCE(status,'Pendiente') IN ('Aprobado','Aprobada','En ejecución','Pendiente')").fetchone()[0]
    total_inventory = conn.execute("SELECT COUNT(*) FROM inventory WHERE is_service = 0").fetchone()[0]
    total_clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    conn.close()

    st.markdown(
        """
        <div class="hero">
            <div style="display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; flex-wrap:wrap;">
                <div>
                    <div class="status-pill">Dashboard ejecutivo</div>
                    <h2 style="margin:.7rem 0 .35rem 0;">Panel de control Abaroa Smart</h2>
                    <div style="color:#94a3b8; font-size:.95rem; max-width:860px;">Vista consolidada para ventas, operación técnica e inventario. Desde aquí puedes monitorear métricas clave, alertas y carga operativa sin depender de la barra lateral oculta.</div>
                </div>
                <div style="color:#cbd5e1; font-size:.86rem; line-height:1.8; min-width:220px;">
                    <div><strong>Módulo activo:</strong> Inicio</div>
                    <div><strong>Sidebar:</strong> fija y recuperable</div>
                    <div><strong>Modo:</strong> escritorio premium</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    a, b, c, d = st.columns(4)
    with a:
        dashboard_kpi_card("Ventas totales", money(total_sales), "Resumen comercial acumulado")
    with b:
        dashboard_kpi_card("Margen bruto", money(total_margin), "Rentabilidad generada")
    with c:
        dashboard_kpi_card("Margen promedio", f"{avg_margin*100:.1f}%", "Promedio histórico de ventas")
    with d:
        dashboard_kpi_card("OT abiertas", str(int(open_ot)), "Carga técnica en proceso")

    e, f, g, h = st.columns(4)
    with e:
        dashboard_kpi_card("Costo materiales", money(total_cost), "Costo directo acumulado")
    with f:
        dashboard_kpi_card("Alertas stock", str(int(low_stock)), "Productos bajo mínimo")
    with g:
        dashboard_kpi_card("Productos", str(int(total_inventory)), "Ítems físicos registrados")
    with h:
        dashboard_kpi_card("Clientes", str(int(total_clients)), "Base comercial activa")

    left_panel, right_panel = st.columns([1.2, 1])
    with left_panel:
        st.markdown("<div class='panel-card'><div class='panel-title'>Stock bajo mínimo</div><div class='panel-subtitle'>Priorización de reposición para productos críticos.</div></div>", unsafe_allow_html=True)
        low_df = get_df("SELECT sku AS SKU, description AS Descripción, stock_current AS 'Stock actual', stock_min AS 'Stock mínimo', sale_price AS 'Precio venta' FROM inventory WHERE COALESCE(is_service,0) = 0 AND COALESCE(stock_min,0)>0 AND stock_current <= stock_min ORDER BY stock_current ASC, sku")
        st.dataframe(
            low_df,
            use_container_width=True,
            hide_index=True,
            height=320,
            column_config={
                "SKU":          st.column_config.TextColumn("SKU"),
                "Descripción":  st.column_config.TextColumn("Descripción"),
                "Stock actual": st.column_config.NumberColumn("Stock actual",  format="%d"),
                "Stock mínimo": st.column_config.NumberColumn("Stock mínimo", format="%d"),
                "Precio venta": st.column_config.NumberColumn("Precio venta", format="$ %d"),
            }
        )
    with right_panel:
        st.markdown("<div class='panel-card'><div class='panel-title'>Accesos rápidos</div><div class='panel-subtitle'>Atajos para las áreas que más vas a usar en operación.</div></div>", unsafe_allow_html=True)
        quick1, quick2 = st.columns(2)
        with quick1:
            if st.button("📦 Abrir inventario", use_container_width=True, key="home_go_inventory"):
                st.session_state["current_tab"] = "Inventario"
                st.rerun()
            if st.button("🧾 Nueva cotización", use_container_width=True, key="home_go_quote"):
                st.session_state["current_tab"] = "Cotización"
                st.rerun()
            if st.button("🧭 Flujo guiado", use_container_width=True, key="home_go_workflow"):
                workflow_go("cliente")
                st.rerun()
            if st.button("👤 Clientes", use_container_width=True, key="home_go_clients"):
                st.session_state["current_tab"] = "Clientes"
                st.rerun()
        with quick2:
            if st.button("📋 Ver OT", use_container_width=True, key="home_go_ot"):
                st.session_state["current_tab"] = "OT"
                st.rerun()
            if st.button("🛠️ Proyectos", use_container_width=True, key="home_go_projects"):
                st.session_state["current_tab"] = "Proyectos"
                st.rerun()
            if st.button("🚚 Proveedores", use_container_width=True, key="home_go_suppliers"):
                st.session_state["current_tab"] = "Proveedores"
                st.rerun()
        st.markdown("<div style='height:.5rem;'></div>", unsafe_allow_html=True)
        ot_df = get_dashboard_work_orders_df(8)
        if ot_df.empty:
            st.info("Aún no hay órdenes de trabajo cargadas.")
        else:
            st.dataframe(ot_df, use_container_width=True, hide_index=True, height=260)



if current_tab == "Buscador":
    st.subheader("Buscador global")
    st.caption("Búsqueda transversal sobre la base completa: inventario, herramientas, clientes, cotizaciones, proyectos, OT, ventas, garantías, instalaciones, insumos, kits y proveedores.")

    q1, q2 = st.columns([3,1])
    global_term = q1.text_input("Buscar en toda la base", value=st.session_state.get("global_search_term", ""), placeholder="Ej: SKU, nombre cliente, OT-0001, proveedor, proyecto...")
    only_with_results = q2.checkbox("Solo módulos con resultados", value=True)
    st.session_state["global_search_term"] = global_term

    if not str(global_term).strip():
        st.info("Escribe un término para buscar en toda la base de datos.")
    else:
        search_results = run_global_search(global_term)
        total_hits = int(sum(len(df.index) for df in search_results.values()))
        st.metric("Coincidencias totales", total_hits)
        order = ["Inventario","Herramientas","Clientes","Cotizaciones","Proyectos","OT","Ventas","Garantías","Instalaciones","Insumos","Kits","Proveedores","Vendedores"]
        for module_name in order:
            df = search_results.get(module_name, pd.DataFrame())
            if only_with_results and df.empty:
                continue
            st.markdown(f"### {module_name}")
            if df.empty:
                st.caption("Sin resultados.")
            else:
                view_df = df.copy()
                if "monto" in view_df.columns:
                    view_df["monto"] = view_df["monto"].apply(lambda x: money(x) if pd.notna(x) and str(x) != '' else "")
                view_df.columns = ["Código", "Título", "Detalle 1", "Detalle 2", "Monto"]
                st.dataframe(view_df, use_container_width=True, hide_index=True)

if current_tab == "Inventario":
    st.subheader("DB Inventario")

    def reset_inventory_editor():
        st.session_state["inventory_selected_pending"] = "Nuevo"
        st.session_state["inventory_image_uploader_key"] = st.session_state.get("inventory_image_uploader_key", 0) + 1
        st.session_state["inventory_form_version"] = st.session_state.get("inventory_form_version", 0) + 1

    if "inventory_selected" not in st.session_state:
        st.session_state["inventory_selected"] = "Nuevo"
    if "inventory_selected_pending" not in st.session_state:
        st.session_state["inventory_selected_pending"] = None
    if "inventory_image_uploader_key" not in st.session_state:
        st.session_state["inventory_image_uploader_key"] = 0
    if "inventory_form_version" not in st.session_state:
        st.session_state["inventory_form_version"] = 0

    inv_df = get_df("SELECT * FROM inventory ORDER BY category, sku")
    for col in ["image_path", "location"]:
        if col not in inv_df.columns:
            inv_df[col] = ""

    search_left, search_right = st.columns([2, 1])
    inventory_find = search_left.text_input("Buscar por SKU o descripción para editar", value=st.session_state.get("inventory_find", ""), placeholder="Ej: PRD-SEN-0001 o sensor puerta")
    if search_right.button("Ir al primero", use_container_width=True, key="inventory_go_first"):
        if str(inventory_find).strip() and not inv_df.empty:
            needle = inventory_find.strip().lower()
            matches = inv_df[
                inv_df["sku"].astype(str).str.lower().str.contains(needle, na=False)
                | inv_df["description"].astype(str).str.lower().str.contains(needle, na=False)
            ]
            if not matches.empty:
                st.session_state["inventory_selected_pending"] = str(matches.iloc[0]["sku"])
                st.session_state["inventory_find"] = inventory_find
                st.rerun()
            else:
                st.warning("No encontré coincidencias para ese SKU o descripción.")
    st.session_state["inventory_find"] = inventory_find

    if str(inventory_find).strip() and not inv_df.empty:
        needle = inventory_find.strip().lower()
        inv_matches = inv_df[
            inv_df["sku"].astype(str).str.lower().str.contains(needle, na=False)
            | inv_df["description"].astype(str).str.lower().str.contains(needle, na=False)
        ].copy()
        if not inv_matches.empty:
            st.caption(f"Coincidencias para edición: {len(inv_matches.index)}")
            options = inv_matches["sku"].tolist()
            preview_choice = st.selectbox(
                "Resultados encontrados",
                options,
                format_func=lambda sku: f"{sku} · {inv_matches.loc[inv_matches['sku'] == sku, 'description'].iloc[0]}",
                key="inventory_match_select"
            )
            if st.button("Cargar item seleccionado", use_container_width=True, key="inventory_load_match"):
                st.session_state["inventory_selected_pending"] = preview_choice
                st.rerun()
        else:
            st.caption("Sin coincidencias. Puedes dejar 'Nuevo' y crear el producto.")

    inv_options = ["Nuevo"] + inv_df["sku"].tolist()
    if st.session_state.get("inventory_selected_pending") in inv_options:
        st.session_state["inventory_selected"] = st.session_state.get("inventory_selected_pending")
        st.session_state["inventory_selected_pending"] = None
    if st.session_state.get("inventory_selected") not in inv_options:
        st.session_state["inventory_selected"] = "Nuevo"
    selected = st.selectbox("Selecciona item para editar", inv_options, key="inventory_selected", format_func=lambda sku: "Nuevo" if sku == "Nuevo" else f"{sku} · {inv_df.loc[inv_df['sku'] == sku, 'description'].iloc[0]}")
    current = inv_df[inv_df["sku"] == selected].iloc[0].to_dict() if selected != "Nuevo" else {}

    if selected != "Nuevo":
        with st.expander("Edición rápida del item seleccionado", expanded=False):
            st.caption("Modifica solo los campos necesarios. El resto queda intacto.")
            q1, q2, q3, q4 = st.columns(4)
            quick_cost = q1.number_input("Costo unitario", min_value=0, value=int(current.get("cost_unit") or 0), step=100, key=f"quick_cost_{selected}")
            quick_margin = q2.number_input("Margen %", min_value=0, max_value=100, value=int(current.get("margin_pct") or 0), step=1, key=f"quick_margin_{selected}")
            quick_stock_min = q3.number_input("Stock mínimo", min_value=0, value=int(current.get("stock_min") or 0), step=1, key=f"quick_stock_min_{selected}")
            quick_stock_initial = q4.number_input("Stock inicial", min_value=0, value=int(current.get("stock_initial") or 0), step=1, key=f"quick_stock_initial_{selected}")
            q5, q6, q7 = st.columns(3)
            quick_provider = q5.text_input("Proveedor", value=str(current.get("provider", "") or ""), key=f"quick_provider_{selected}")
            quick_location = q6.text_input("Ubicación", value=str(current.get("location", "") or ""), key=f"quick_location_{selected}")
            quick_protocol = q7.text_input("Protocolo", value=str(current.get("protocol", "") or ""), key=f"quick_protocol_{selected}")
            quick_description = st.text_input("Descripción", value=str(current.get("description", "") or ""), key=f"quick_description_{selected}")
            qi1, qi2 = st.columns([1, 1])
            with qi1:
                quick_current_image = inventory_image_web_path(current.get("image_path", ""))
                if quick_current_image:
                    st.image(quick_current_image, caption=f"Imagen actual · {selected}", use_container_width=True)
                else:
                    st.caption("Sin imagen actual")
            with qi2:
                quick_image_path = st.text_input("Ruta imagen", value=str(current.get("image_path", "") or ""), key=f"quick_image_path_{selected}")
                quick_image_file = st.file_uploader(
                    "Subir nueva imagen",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"quick_image_file_{selected}"
                )
                quick_remove_image = st.checkbox("Quitar imagen actual", value=False, key=f"quick_remove_image_{selected}")
            suggested_quick_price = calc_sale_price(quick_cost, quick_margin) if quick_cost else int(current.get("sale_price") or 0)
            st.info(f"Precio sugerido resultante: {money(suggested_quick_price)}")
            qc1, qc2 = st.columns(2)
            if qc1.button("Guardar edición rápida", key=f"quick_save_{selected}", type="primary", use_container_width=True):
                conn = get_conn()
                current_stock = int(current.get("stock_current") or 0)
                current_reserved = int(current.get("stock_reserved") or 0)
                is_service_quick = bool(current.get("is_service", 0))
                if is_service_quick:
                    quick_stock_current = 0
                else:
                    delta_initial = int(quick_stock_initial) - int(current.get("stock_initial") or 0)
                    quick_stock_current = max(current_stock + delta_initial, current_reserved, 0)
                final_quick_image_path = "" if quick_remove_image else str(quick_image_path).strip()
                if quick_image_file is not None:
                    final_quick_image_path = save_inventory_image(quick_image_file, selected)
                conn.execute(
                    """
                    UPDATE inventory
                    SET description=?, protocol=?, stock_initial=?, stock_current=?, cost_unit=?, margin_pct=?, sale_price=?, provider=?, stock_min=?, location=?, image_path=?
                    WHERE sku=?
                    """,
                    (str(quick_description).strip(), str(quick_protocol).strip(), int(quick_stock_initial), int(quick_stock_current), int(quick_cost), int(quick_margin), int(suggested_quick_price), str(quick_provider).strip(), int(quick_stock_min), str(quick_location).strip(), final_quick_image_path, selected)
                )
                if str(quick_provider).strip():
                    conn.execute("INSERT OR IGNORE INTO suppliers (name) VALUES (?)", (str(quick_provider).strip(),))
                conn.commit()
                conn.close()
                recalc_stock()
                st.success(f"Cambios rápidos guardados para {selected}.")
                st.rerun()
            if qc2.button("Cancelar edición rápida", key=f"quick_cancel_{selected}", use_container_width=True):
                st.rerun()

    existing_categories = sorted([c for c in inv_df["category"].dropna().astype(str).unique().tolist() if c])
    category_options = existing_categories + (["Otra..."] if "Otra..." not in existing_categories else [])
    current_category = str(current.get("category", "")) if current else ""
    default_choice = current_category if current_category in existing_categories else ("Otra..." if current_category else (existing_categories[0] if existing_categories else "Otra..."))

    current_image = inventory_image_web_path(current.get("image_path", "")) if current else ""
    if selected != "Nuevo":
        preview_col, data_col = st.columns([1, 2])
        with preview_col:
            if current_image:
                st.image(current_image, caption=f"Foto actual · {selected}", use_container_width=True)
            else:
                st.caption("Sin foto cargada")
        with data_col:
            st.markdown(f"**SKU:** {selected}")
            st.markdown(f"**Ubicación:** {current.get('location', '') or 'Sin definir'}")
            st.markdown(f"**Proveedor:** {current.get('provider', '') or 'Sin proveedor'}")

    form_version = st.session_state.get("inventory_form_version", 0)
    with st.form(f"inventory_form_{form_version}"):
        a,b,c,d = st.columns(4)
        description = a.text_input("Descripción", value=str(current.get("description", "")), key=f"inventory_description_{form_version}")
        category_choice = b.selectbox("Categoría", category_options if category_options else ["Otra..."], index=((category_options if category_options else ["Otra..."]).index(default_choice) if default_choice in (category_options if category_options else ["Otra..."]) else 0), key=f"inventory_category_choice_{form_version}")
        category_custom = c.text_input("Nueva categoría", value=(current_category if default_choice == "Otra..." else ""), key=f"inventory_category_custom_{form_version}")
        protocols = ["Zigbee", "Wi-Fi", "Configuración", "Servicios", "Auditoria", "Otro..."]
        current_protocol = str(current.get("protocol", "") or "")
        protocol_choice = d.selectbox("Protocolo", protocols, index=(protocols.index(current_protocol) if current_protocol in protocols else (protocols.index("Otro...") if current_protocol else 0)), key=f"inventory_protocol_choice_{form_version}")
        protocol_custom = st.text_input(
            "Otro protocolo (solo se usa si eliges 'Otro...')",
            value=(current_protocol if current_protocol and current_protocol not in protocols[:-1] else ""),
            key=f"inventory_protocol_custom_{form_version}"
        )

        category = category_custom.strip() if category_choice == "Otra..." else category_choice
        protocol = protocol_custom.strip() if protocol_choice == "Otro..." else protocol_choice
        is_service = st.checkbox("Es servicio", value=bool(current.get("is_service", 0)), key=f"inventory_is_service_{form_version}")
        existing_skus = inv_df["sku"].tolist()
        if selected != "Nuevo" and current.get("sku") in existing_skus:
            existing_skus.remove(current.get("sku"))
        auto_sku = current.get("sku", "") if selected != "Nuevo" else next_sku_for_category(category or "General", existing_skus, is_service)

        e,f,g,h,i,j = st.columns(6)
        sku_show = e.text_input("SKU", value=str(auto_sku), disabled=True, key=f"inventory_sku_show_{form_version}")
        stock_initial = f.number_input("Stock inicial", min_value=0, value=int(current.get("stock_initial") or 0), step=1, key=f"inventory_stock_initial_{form_version}")
        stock_min = g.number_input("Stock mínimo", min_value=0, value=int(current.get("stock_min") or 0), step=1, key=f"inventory_stock_min_{form_version}")
        cost_unit = h.number_input("Costo unitario", min_value=0, value=int(current.get("cost_unit") or 0), step=100, key=f"inventory_cost_unit_{form_version}")
        margin_pct = i.number_input("Margen %", min_value=0, max_value=100, value=int(current.get("margin_pct") or 0), step=1, key=f"inventory_margin_pct_{form_version}")
        provider = j.text_input("Proveedor", value=str(current.get("provider", "")), key=f"inventory_provider_{form_version}")

        l1, l2 = st.columns(2)
        location = l1.text_input("Ubicación en bodega", value=str(current.get("location", "") or ""), placeholder="Ej: Estante A1 / Caja 2", key=f"inventory_location_{form_version}")
        image_file = l2.file_uploader("Foto del producto", type=["png", "jpg", "jpeg", "webp"], help="La imagen se guardará automáticamente con el nombre del SKU.", key=f"inventory_image_uploader_{st.session_state.get('inventory_image_uploader_key', 0)}")

        st.info(f"SKU automático por categoría: {auto_sku}  |  Precio venta sugerido (margen comercial real): {money(calc_sale_price(cost_unit, margin_pct) if cost_unit else 0)}")
        recalc_btn = st.form_submit_button("Recalcular todos los precios sugeridos del inventario")
        if recalc_btn:
            recalc_all_sale_prices()
            st.success("Precios sugeridos recalculados en todo el inventario.")

        s1, s2, s3 = st.columns(3)
        save_btn = s1.form_submit_button("Guardar nuevo")
        edit_btn = s2.form_submit_button("Editar")
        delete_btn = s3.form_submit_button("Eliminar")

        submit_inventory = save_btn or edit_btn
        if submit_inventory:
            if save_btn and selected != "Nuevo":
                st.error("Para crear un producto nuevo, primero deja la selección en 'Nuevo'.")
            elif edit_btn and selected == "Nuevo":
                st.error("Selecciona un item existente para editarlo.")
            elif not description or not category or not protocol:
                st.error("Descripción, categoría y protocolo son obligatorios.")
            else:
                sale_price = calc_sale_price(cost_unit, margin_pct) if cost_unit else 0
                final_sku = current.get("sku", "") if selected != "Nuevo" else auto_sku
                image_path = current.get("image_path", "") or ""
                if image_file is not None:
                    image_path = save_inventory_image(image_file, final_sku)
                conn = get_conn()
                existing_row = conn.execute("SELECT sku, stock_current, stock_reserved FROM inventory WHERE sku = ?", (final_sku,)).fetchone()
                if save_btn and existing_row is not None:
                    conn.close()
                    st.error(f"Ya existe un item con el SKU {final_sku}. No se guardó para evitar duplicados.")
                else:
                    if provider:
                        q(conn, "INSERT OR IGNORE INTO suppliers (name) VALUES (?)", (provider,))
                    if save_btn:
                        stock_current = 0 if is_service else int(stock_initial)
                        q(conn, """
                            INSERT INTO inventory (
                                sku, description, category, protocol, stock_initial, stock_current,
                                cost_unit, margin_pct, sale_price, provider, is_service, stock_min, image_path, location
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (final_sku, description, category, protocol, int(stock_initial), int(stock_current), int(cost_unit), int(margin_pct), int(sale_price), provider, 1 if is_service else 0, int(stock_min), image_path, location.strip()))
                    else:
                        current_stock = int(current.get("stock_current") or 0)
                        current_reserved = int(current.get("stock_reserved") or 0)
                        if is_service:
                            stock_current = 0
                        else:
                            delta_initial = int(stock_initial) - int(current.get("stock_initial") or 0)
                            stock_current = max(current_stock + delta_initial, current_reserved, 0)
                        q(conn, """
                            UPDATE inventory
                            SET description=?, category=?, protocol=?, stock_initial=?, stock_current=?,
                                cost_unit=?, margin_pct=?, sale_price=?, provider=?, is_service=?, stock_min=?, image_path=?, location=?
                            WHERE sku=?
                        """, (description, category, protocol, int(stock_initial), int(stock_current), int(cost_unit), int(margin_pct), int(sale_price), provider, 1 if is_service else 0, int(stock_min), image_path, location.strip(), final_sku))
                    conn.close()
                    recalc_stock()
                    reset_inventory_editor()
                    st.success(f"Item {'creado' if save_btn else 'editado'} con SKU {final_sku}.")
                    st.rerun()
        if delete_btn and selected != "Nuevo":
            conn = get_conn()
            q(conn, "DELETE FROM inventory WHERE sku = ?", (selected,))
            conn.close()
            reset_inventory_editor()
            st.success("Item eliminado.")
            st.rerun()

    st.markdown("### Vista tabular del inventario")
    inv_table = get_df("""
        SELECT
            i.category,
            i.sku,
            i.description,
            i.protocol,
            i.location,
            i.stock_initial,
            i.stock_current,
            COALESCE(i.stock_reserved,0) AS stock_reserved,
            i.stock_min,
            i.cost_unit,
            i.margin_pct,
            i.sale_price,
            i.provider,
            i.is_service,
            i.image_path,
            COALESCE(SUM(v.sold_qty),0) AS sold_qty,
            COALESCE(u.used_qty,0) AS used_qty
        FROM inventory i
        LEFT JOIN (
            SELECT qi.sku, SUM(qi.quantity) AS sold_qty
            FROM quote_items qi
            JOIN quotes q ON q.id = qi.quote_id
            WHERE qi.item_type = 'producto' AND q.status IN ('Aprobada','Aceptada','Vendida','Facturada')
            GROUP BY qi.sku
            UNION ALL
            SELECT ki.sku, SUM(qi.quantity * ki.quantity) AS sold_qty
            FROM quote_items qi
            JOIN quotes q ON q.id = qi.quote_id
            JOIN kits k ON k.code = qi.sku
            JOIN kit_items ki ON ki.kit_id = k.id
            WHERE qi.item_type = 'kit' AND q.status IN ('Aprobada','Aceptada','Vendida','Facturada')
            GROUP BY ki.sku
        ) v ON v.sku = i.sku
        LEFT JOIN (
            SELECT sku, SUM(used_quantity) AS used_qty
            FROM project_items
            WHERE item_type IN ('producto','kit_component')
            GROUP BY sku
        ) u ON u.sku = i.sku
        GROUP BY i.category, i.sku, i.description, i.protocol, i.location, i.stock_initial, i.stock_current, i.stock_reserved, i.stock_min, i.cost_unit, i.margin_pct, i.sale_price, i.provider, i.is_service, i.image_path, u.used_qty
        ORDER BY i.category, i.sku
    """)
    if not inv_table.empty:
        numeric_cols = ["stock_current", "stock_reserved", "sold_qty", "used_qty"]
        for col in numeric_cols:
            inv_table[col] = inv_table[col].fillna(0).astype(int)
        inv_table["stock_disponible"] = inv_table["stock_current"] - inv_table["stock_reserved"]
    st.dataframe(
        inv_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "category":       st.column_config.TextColumn("Categoría"),
            "sku":            st.column_config.TextColumn("SKU"),
            "description":    st.column_config.TextColumn("Descripción"),
            "protocol":       st.column_config.TextColumn("Protocolo"),
            "location":       st.column_config.TextColumn("Ubicación"),
            "stock_initial":  st.column_config.NumberColumn("Stock inicial", format="%d"),
            "stock_current":  st.column_config.NumberColumn("Stock actual",  format="%d"),
            "stock_reserved": st.column_config.NumberColumn("Reservado",     format="%d"),
            "stock_min":      st.column_config.NumberColumn("Stock mínimo",  format="%d"),
            "stock_disponible": st.column_config.NumberColumn("Disponible",  format="%d"),
            "cost_unit":      st.column_config.NumberColumn("Costo unit.",   format="$ %d"),
            "margin_pct":     st.column_config.NumberColumn("Margen %",      format="%d%%"),
            "sale_price":     st.column_config.NumberColumn("Precio venta",  format="$ %d"),
            "provider":       st.column_config.TextColumn("Proveedor"),
            "is_service":     st.column_config.CheckboxColumn("Servicio"),
            "image_path":     st.column_config.TextColumn("Foto", width="small"),
            "sold_qty":       st.column_config.NumberColumn("Vendido",       format="%d"),
            "used_qty":       st.column_config.NumberColumn("Usado",         format="%d"),
        }
    )

    st.markdown("### Catálogo visual de bodega")
    catalog_df = get_df("SELECT sku, description, category, protocol, location, stock_current, stock_min, sale_price, image_path FROM inventory WHERE is_service = 0 ORDER BY category, description")
    if catalog_df.empty:
        st.info("Aún no hay productos cargados en el inventario.")
    else:
        search_col, cat_col = st.columns([2, 1])
        search_text = search_col.text_input("Buscar producto", value="")
        categories_catalog = ["Todas"] + sorted([c for c in catalog_df["category"].dropna().astype(str).unique().tolist() if c])
        selected_catalog_category = cat_col.selectbox("Filtrar categoría", categories_catalog)
        filtered_catalog = catalog_df.copy()
        if search_text.strip():
            needle = search_text.strip().lower()
            filtered_catalog = filtered_catalog[
                filtered_catalog["sku"].astype(str).str.lower().str.contains(needle, na=False)
                | filtered_catalog["description"].astype(str).str.lower().str.contains(needle, na=False)
                | filtered_catalog["location"].astype(str).str.lower().str.contains(needle, na=False)
            ]
        if selected_catalog_category != "Todas":
            filtered_catalog = filtered_catalog[filtered_catalog["category"] == selected_catalog_category]

        cols = st.columns(3)
        for idx, row in filtered_catalog.reset_index(drop=True).iterrows():
            with cols[idx % 3]:
                with st.container(border=True):
                    image_path = inventory_image_web_path(row.get("image_path", ""))
                    if image_path:
                        st.image(image_path, use_container_width=True)
                    else:
                        st.caption("Sin foto")
                    st.markdown(f"**{row['description']}**")
                    st.caption(f"SKU: {row['sku']} · Categoría: {row['category']}")
                    st.write(f"Protocolo: {row['protocol'] or '-'}")
                    st.write(f"Ubicación: {row['location'] or 'Sin definir'}")
                    st.write(f"Stock actual: {int(row['stock_current'] or 0)} / mínimo {int(row['stock_min'] or 0)}")
                    st.write(f"Precio sugerido: {money(row['sale_price'] or 0)}")
if current_tab == "Herramientas":
    st.subheader("Herramientas")
    st.caption("Activos de trabajo separados del inventario vendible. No afectan stock comercial ni dashboard de ventas.")

    tools_df = normalize_tools_df(get_df("SELECT * FROM tools_assets ORDER BY tool_name, asset_id"))
    tool_search = st.text_input("Buscar herramienta", value=st.session_state.get("tool_search", ""), placeholder="Asset ID, nombre, proveedor, estado...")
    st.session_state["tool_search"] = tool_search
    if str(tool_search).strip() and not tools_df.empty:
        tneedle = tool_search.strip().lower()
        tools_df = tools_df[
            tools_df["asset_id"].astype(str).str.lower().str.contains(tneedle, na=False)
            | tools_df["tool_name"].astype(str).str.lower().str.contains(tneedle, na=False)
            | tools_df["provider"].astype(str).str.lower().str.contains(tneedle, na=False)
            | tools_df["category"].astype(str).str.lower().str.contains(tneedle, na=False)
            | tools_df["status"].astype(str).str.lower().str.contains(tneedle, na=False)
        ].copy()
    total_inversion = int(((tools_df["cost_unit"] * tools_df["quantity"]).sum()) if not tools_df.empty else 0)
    total_monthly = int((tools_df["monthly_cost"].sum()) if not tools_df.empty and "monthly_cost" in tools_df.columns else 0)
    activas = int((tools_df[tools_df["status"].fillna("Activa") == "Activa"].shape[0]) if not tools_df.empty else 0)
    c1, c2, c3 = st.columns(3)
    c1.metric("Herramientas registradas", int(len(tools_df.index)))
    c2.metric("Inversión total", money(total_inversion))
    c3.metric("Costo mensual estimado", money(total_monthly))
    st.caption(f"Herramientas activas: {activas}")

    with st.expander("Importar herramientas desde CSV", expanded=False):
        up = st.file_uploader("CSV herramientas", type=["csv"], key="tools_csv_upload")
        if st.button("Importar herramientas", key="tools_csv_btn"):
            if up is None:
                st.warning("Selecciona un archivo CSV primero.")
            else:
                try:
                    inserted = import_tools_csv(up)
                    st.success(f"Herramientas importadas/actualizadas: {inserted}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error importando herramientas: {e}")

    st.markdown("### Registrar / editar herramienta")
    tool_options = ["Nueva"] + tools_df["asset_id"].astype(str).tolist() if not tools_df.empty else ["Nueva"]
    selected_tool = st.selectbox("Selecciona herramienta", tool_options, key="tool_asset_selected")
    current_tool = tools_df[tools_df["asset_id"].astype(str) == selected_tool].iloc[0].to_dict() if selected_tool != "Nueva" and not tools_df.empty else {}

    with st.form("tool_asset_form"):
        t1, t2, t3, t4 = st.columns(4)
        asset_id = t1.text_input("Asset ID", value=str(current_tool.get("asset_id", "")))
        tool_name = t2.text_input("Nombre herramienta", value=str(current_tool.get("tool_name", "")))
        provider = t3.text_input("Proveedor", value=str(current_tool.get("provider", "")))
        status = t4.selectbox("Estado", ["Activa", "En mantención", "Baja"], index=(["Activa", "En mantención", "Baja"].index(str(current_tool.get("status", "Activa"))) if str(current_tool.get("status", "Activa")) in ["Activa", "En mantención", "Baja"] else 0))
        t5, t6, t7, t8 = st.columns(4)
        category = t5.text_input("Categoría", value=str(current_tool.get("category", "Herramienta")) or "Herramienta")
        quantity = int(t6.number_input("Cantidad", min_value=1, value=int(current_tool.get("quantity", 1) or 1), step=1))
        cost_unit = int(t7.number_input("Costo unitario", min_value=0, value=int(current_tool.get("cost_unit", 0) or 0), step=100))
        useful_life_months = int(t8.number_input("Vida útil (meses)", min_value=1, value=int(current_tool.get("useful_life_months", 12) or 12), step=1))
        t9, t10 = st.columns(2)
        purchase_date = t9.text_input("Fecha compra", value=str(current_tool.get("purchase_date", "")), placeholder="YYYY-MM-DD")
        notes = t10.text_input("Notas", value=str(current_tool.get("notes", "")))
        monthly_cost = calc_monthly_tool_cost(cost_unit, quantity, useful_life_months)
        st.info(f"Costo mensual estimado: {money(monthly_cost)}")
        s1, s2, s3 = st.columns(3)
        save_tool = s1.form_submit_button("Guardar herramienta", type="primary", use_container_width=True)
        delete_tool = s2.form_submit_button("Eliminar herramienta", use_container_width=True)
        clear_tool = s3.form_submit_button("Limpiar", use_container_width=True)

    if save_tool:
        if not str(asset_id).strip() or not str(tool_name).strip():
            st.error("Asset ID y Nombre herramienta son obligatorios.")
        else:
            conn = get_conn()
            conn.execute("""
                INSERT INTO tools_assets (
                    asset_id, tool_name, category, provider, quantity, cost_unit,
                    purchase_date, useful_life_months, monthly_cost, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    tool_name=excluded.tool_name,
                    category=excluded.category,
                    provider=excluded.provider,
                    quantity=excluded.quantity,
                    cost_unit=excluded.cost_unit,
                    purchase_date=excluded.purchase_date,
                    useful_life_months=excluded.useful_life_months,
                    monthly_cost=excluded.monthly_cost,
                    status=excluded.status,
                    notes=excluded.notes
            """, (
                str(asset_id).strip(), str(tool_name).strip(), str(category).strip() or "Herramienta", str(provider).strip(),
                int(quantity), int(cost_unit), str(purchase_date).strip(), int(useful_life_months), int(monthly_cost), str(status).strip(), str(notes).strip()
            ))
            conn.commit()
            conn.close()
            st.success("Herramienta guardada.")
            st.rerun()
    if delete_tool and selected_tool != "Nueva":
        conn = get_conn()
        conn.execute("DELETE FROM tools_assets WHERE asset_id = ?", (selected_tool,))
        conn.commit()
        conn.close()
        st.success("Herramienta eliminada.")
        st.rerun()
    if clear_tool:
        st.rerun()

    st.markdown("### Listado de herramientas")
    if tools_df.empty:
        st.info("No hay herramientas registradas todavía.")
    else:
        display_df = tools_df.copy()
        display_df["inversion_total"] = display_df["cost_unit"].fillna(0).astype(int) * display_df["quantity"].fillna(0).astype(int)
        st.dataframe(
            display_df[["asset_id", "tool_name", "category", "provider", "quantity", "cost_unit", "monthly_cost", "inversion_total", "status", "purchase_date", "notes"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "asset_id":       st.column_config.TextColumn("Asset ID"),
                "tool_name":      st.column_config.TextColumn("Herramienta"),
                "category":       st.column_config.TextColumn("Categoría"),
                "provider":       st.column_config.TextColumn("Proveedor"),
                "quantity":       st.column_config.NumberColumn("Cantidad",       format="%d"),
                "cost_unit":      st.column_config.NumberColumn("Costo unitario", format="$ %d"),
                "monthly_cost":   st.column_config.NumberColumn("Costo mensual",  format="$ %d"),
                "inversion_total":st.column_config.NumberColumn("Inversión total",format="$ %d"),
                "status":         st.column_config.TextColumn("Estado"),
                "purchase_date":  st.column_config.TextColumn("Fecha compra"),
                "notes":          st.column_config.TextColumn("Notas"),
            }
        )

if current_tab == "Clientes":
    st.subheader("DB Clientes")
    cli_df = get_df("SELECT * FROM clients ORDER BY id DESC")
    cli_options = ["Nuevo"] + [f'{row["id"]} · {row["name"]}' for _, row in cli_df.iterrows()]
    cli_sel = st.selectbox("Selecciona cliente para editar", cli_options)
    cli_current = cli_df[cli_df["id"] == int(cli_sel.split(" · ")[0])].iloc[0].to_dict() if cli_sel != "Nuevo" else {}
    with st.form("client_form"):
        a,b = st.columns(2)
        name = a.text_input("Nombre", value=str(cli_current.get("name","")))
        phone = b.text_input("Teléfono", value=str(cli_current.get("phone","") or ""))
        c,d = st.columns(2)
        email = c.text_input("Correo", value=str(cli_current.get("email","") or ""))
        address = d.text_input("Dirección", value=str(cli_current.get("address","") or ""))
        s1,s2,s3 = st.columns(3)
        save_btn = s1.form_submit_button("Guardar")
        edit_btn = s2.form_submit_button("Editar")
        delete_btn = s3.form_submit_button("Eliminar")
        checks = {"name": name.strip(), "phone": phone.strip(), "email": email.strip(), "address": address.strip()}
        if save_btn:
            if not name:
                st.error("El nombre es obligatorio.")
            elif exists_duplicate("clients", checks):
                st.error("Ya existe un cliente con los mismos datos.")
            else:
                conn = get_conn()
                q(conn, "INSERT INTO clients (name, phone, email, address) VALUES (?, ?, ?, ?)", (name, phone, email, address))
                conn.close()
                st.success("Cliente guardado.")
                st.rerun()
        if edit_btn:
            if cli_sel == "Nuevo":
                st.error("Selecciona un cliente existente para editar.")
            elif not name:
                st.error("El nombre es obligatorio.")
            else:
                cli_id = int(cli_sel.split(" · ")[0])
                if exists_duplicate("clients", checks, exclude_id=cli_id):
                    st.error("La edición generaría un cliente duplicado.")
                else:
                    conn = get_conn()
                    q(conn, "UPDATE clients SET name=?, phone=?, email=?, address=? WHERE id=?", (name, phone, email, address, cli_id))
                    conn.close()
                    st.success("Cliente editado.")
                    st.rerun()
        if delete_btn and cli_sel != "Nuevo":
            cli_id = int(cli_sel.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM clients WHERE id = ?", (cli_id,))
            conn.close()
            st.success("Cliente eliminado.")
            st.rerun()
    st.dataframe(get_df("SELECT * FROM clients ORDER BY id DESC"), use_container_width=True, hide_index=True)
if current_tab == "Vendedores":
    st.subheader("DB Vendedores")
    ven_df = get_df("SELECT * FROM vendors ORDER BY id DESC")
    ven_options = ["Nuevo"] + [f'{row["id"]} · {row["name"]}' for _, row in ven_df.iterrows()]
    ven_sel = st.selectbox("Selecciona vendedor para editar", ven_options)
    ven_current = ven_df[ven_df["id"] == int(ven_sel.split(" · ")[0])].iloc[0].to_dict() if ven_sel != "Nuevo" else {}
    with st.form("vendor_form"):
        a,b = st.columns(2)
        name = a.text_input("Nombre", value=str(ven_current.get("name","")))
        email = b.text_input("Correo", value=str(ven_current.get("email","") or ""))
        c,d = st.columns(2)
        phone = c.text_input("Teléfono", value=str(ven_current.get("phone","") or ""))
        role = d.text_input("Cargo", value=str(ven_current.get("role","Ventas") or "Ventas"))
        s1,s2,s3 = st.columns(3)
        save_btn = s1.form_submit_button("Guardar")
        edit_btn = s2.form_submit_button("Editar")
        delete_btn = s3.form_submit_button("Eliminar")
        checks = {"name": name.strip(), "email": email.strip(), "phone": phone.strip(), "role": role.strip()}
        if save_btn:
            if not name:
                st.error("El nombre es obligatorio.")
            elif exists_duplicate("vendors", checks):
                st.error("Ya existe un vendedor con los mismos datos.")
            else:
                conn = get_conn()
                q(conn, "INSERT INTO vendors (name, email, phone, role) VALUES (?, ?, ?, ?)", (name, email, phone, role))
                conn.close()
                st.success("Vendedor guardado.")
                st.rerun()
        if edit_btn:
            if ven_sel == "Nuevo":
                st.error("Selecciona un vendedor existente para editar.")
            elif not name:
                st.error("El nombre es obligatorio.")
            else:
                ven_id = int(ven_sel.split(" · ")[0])
                if exists_duplicate("vendors", checks, exclude_id=ven_id):
                    st.error("La edición generaría un vendedor duplicado.")
                else:
                    conn = get_conn()
                    q(conn, "UPDATE vendors SET name=?, email=?, phone=?, role=? WHERE id=?", (name, email, phone, role, ven_id))
                    conn.close()
                    st.success("Vendedor editado.")
                    st.rerun()
        if delete_btn and ven_sel != "Nuevo":
            ven_id = int(ven_sel.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM vendors WHERE id = ?", (ven_id,))
            conn.close()
            st.success("Vendedor eliminado.")
            st.rerun()
    st.dataframe(get_df("SELECT * FROM vendors ORDER BY id DESC"), use_container_width=True, hide_index=True)
if current_tab == "Proveedores":
    st.subheader("DB Proveedores")
    sup_df = get_df("SELECT * FROM suppliers ORDER BY name")
    sup_options = ["Nuevo"] + [f'{row["id"]} · {row["name"]}' for _, row in sup_df.iterrows()]
    sup_sel = st.selectbox("Selecciona proveedor para editar", sup_options)
    sup_current = sup_df[sup_df["id"] == int(sup_sel.split(" · ")[0])].iloc[0].to_dict() if sup_sel != "Nuevo" else {}
    with st.form("supplier_form"):
        a,b = st.columns(2)
        name = a.text_input("Nombre proveedor", value=str(sup_current.get("name","")))
        phone = b.text_input("Teléfono", value=str(sup_current.get("phone","") or ""))
        c,d = st.columns(2)
        email = c.text_input("Correo", value=str(sup_current.get("email","") or ""))
        contact_person = d.text_input("Contacto", value=str(sup_current.get("contact_person","") or ""))
        notes = st.text_area("Notas", value=str(sup_current.get("notes","") or ""))
        s1,s2,s3 = st.columns(3)
        save_btn = s1.form_submit_button("Guardar")
        edit_btn = s2.form_submit_button("Editar")
        delete_btn = s3.form_submit_button("Eliminar")
        if save_btn:
            if not name:
                st.error("El nombre es obligatorio.")
            elif exists_duplicate("suppliers", {"name": name.strip()}):
                st.error("Ya existe un proveedor con ese nombre.")
            else:
                conn = get_conn()
                q(conn, "INSERT INTO suppliers (name, phone, email, contact_person, notes) VALUES (?, ?, ?, ?, ?)", (name, phone, email, contact_person, notes))
                conn.close()
                st.success("Proveedor guardado.")
        if edit_btn:
            if sup_sel == "Nuevo":
                st.error("Selecciona un proveedor existente para editar.")
            elif not name:
                st.error("El nombre es obligatorio.")
            else:
                sup_id = int(sup_sel.split(" · ")[0])
                if exists_duplicate("suppliers", {"name": name.strip()}, exclude_id=sup_id):
                    st.error("Ya existe otro proveedor con ese nombre.")
                else:
                    conn = get_conn()
                    q(conn, "UPDATE suppliers SET name=?, phone=?, email=?, contact_person=?, notes=? WHERE id=?", (name, phone, email, contact_person, notes, sup_id))
                    conn.close()
                    st.success("Proveedor editado.")
        if delete_btn and sup_sel != "Nuevo":
            sup_id = int(sup_sel.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM suppliers WHERE id = ?", (sup_id,))
            conn.close()
            st.success("Proveedor eliminado.")
    st.dataframe(sup_df, use_container_width=True, hide_index=True)
if current_tab == "Insumos":
    st.subheader("DB Insumos")
    ins_df = get_df("SELECT * FROM supplies_catalog ORDER BY description")
    ins_opts = ["Nuevo"] + [f'{row["id"]} · {row["description"]}' for _, row in ins_df.iterrows()]
    ins_sel = st.selectbox("Selecciona insumo para editar", ins_opts)
    ins_cur = ins_df[ins_df["id"] == int(ins_sel.split(" · ")[0])].iloc[0].to_dict() if ins_sel != "Nuevo" else {}
    with st.form("supply_catalog_form"):
        a,b = st.columns(2)
        desc = a.text_input("Descripción", value=str(ins_cur.get("description","")))
        price = b.number_input("Precio referencial", min_value=0, value=int(ins_cur.get("default_unit_price") or 0), step=100)
        s1,s2 = st.columns(2)
        save_btn = s1.form_submit_button("Guardar")
        del_btn = s2.form_submit_button("Eliminar")
        desc = desc.strip()
        if save_btn:
            if not desc:
                st.error("La descripción del insumo es obligatoria.")
            else:
                conn = get_conn()
                if ins_sel == "Nuevo":
                    q(conn, "INSERT OR IGNORE INTO supplies_catalog (description, default_unit_price) VALUES (?, ?)", (desc, int(price)))
                    q(conn, "UPDATE supplies_catalog SET default_unit_price=? WHERE description=?", (int(price), desc))
                else:
                    iid = int(ins_sel.split(" · ")[0])
                    q(conn, "UPDATE supplies_catalog SET description=?, default_unit_price=? WHERE id=?", (desc, int(price), iid))
                conn.close()
                st.success("Insumo guardado.")
                st.rerun()
        if del_btn and ins_sel != "Nuevo":
            iid = int(ins_sel.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM supplies_catalog WHERE id=?", (iid,))
            conn.close()
            st.success("Insumo eliminado.")
            st.rerun()
    st.dataframe(ins_df, use_container_width=True, hide_index=True)

if current_tab == "Kits":
    st.subheader("Kits / Bundles")
    kits_df = get_df("SELECT * FROM kits ORDER BY id DESC")
    kit_options = ["Nuevo"] + [f'{row["id"]} · {row["code"]} · {row["name"]}' for _, row in kits_df.iterrows()]
    kit_sel = st.selectbox("Selecciona kit para editar", kit_options)
    kit_current = kits_df[kits_df["id"] == int(kit_sel.split(" · ")[0])].iloc[0].to_dict() if kit_sel != "Nuevo" else {}
    with st.form("kit_form"):
        a,b,c = st.columns(3)
        code = a.text_input("Código kit", value=str(kit_current.get("code","KIT-001")))
        name = b.text_input("Nombre kit", value=str(kit_current.get("name","")))
        sale_price = c.number_input("Precio venta kit", min_value=0, value=int(kit_current.get("sale_price") or 0), step=1000)
        notes = st.text_area("Notas", value=str(kit_current.get("notes","") or ""))
        s1,s2 = st.columns(2)
        save_btn = s1.form_submit_button("Guardar kit")
        delete_btn = s2.form_submit_button("Eliminar kit")
        if save_btn:
            if not code or not name:
                st.error("Código y nombre son obligatorios.")
            else:
                conn = get_conn()
                if kit_sel == "Nuevo":
                    q(conn, "INSERT OR REPLACE INTO kits (code, name, sale_price, notes) VALUES (?, ?, ?, ?)", (code, name, int(sale_price), notes))
                else:
                    kit_id = int(kit_sel.split(" · ")[0])
                    q(conn, "UPDATE kits SET code=?, name=?, sale_price=?, notes=? WHERE id=?", (code, name, int(sale_price), notes, kit_id))
                conn.close()
                st.success("Kit guardado.")
                st.rerun()
        if delete_btn and kit_sel != "Nuevo":
            kit_id = int(kit_sel.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM kit_items WHERE kit_id = ?", (kit_id,))
            q(conn, "DELETE FROM kits WHERE id = ?", (kit_id,))
            conn.close()
            st.success("Kit eliminado.")
            st.rerun()

    st.markdown("### Componentes del kit")
    kits_df = get_df("SELECT * FROM kits ORDER BY id DESC")
    if not kits_df.empty:
        sel = st.selectbox("Kit para agregar componentes", [f'{row["id"]} · {row["code"]} · {row["name"]}' for _, row in kits_df.iterrows()], key="kit_comp")
        kit_id = int(sel.split(" · ")[0])
        inv_products = get_df("SELECT sku, description, stock_current, sale_price, cost_unit FROM inventory WHERE is_service = 0 ORDER BY description")
        options = [""] + [f'{row["sku"]} · {row["description"]}' for _, row in inv_products.iterrows()]
        with st.form("kit_items_form"):
            p1,p2 = st.columns(2)
            item = p1.selectbox("Producto componente", options)
            qty = p2.number_input("Cantidad componente", min_value=1, value=1, step=1)
            save_comp = st.form_submit_button("Agregar componente")
            if save_comp and item:
                sku, _ = item.split(" · ", 1)
                conn = get_conn()
                q(conn, "INSERT INTO kit_items (kit_id, sku, quantity) VALUES (?, ?, ?)", (kit_id, sku, int(qty)))
                conn.close()
                st.success("Componente agregado.")
                st.rerun()
        comps = kit_components_df(kit_id)
        st.dataframe(comps, use_container_width=True, hide_index=True)
        if not comps.empty:
            del_comp = st.selectbox("Eliminar componente", [""] + [f'{row["sku"]} · {row["description"]}' for _, row in comps.iterrows()])
            if st.button("Eliminar componente") and del_comp:
                sku = del_comp.split(" · ")[0]
                conn = get_conn()
                q(conn, "DELETE FROM kit_items WHERE kit_id = ? AND sku = ? LIMIT 1", (kit_id, sku))
                conn.close()
                st.success("Componente eliminado.")
                st.rerun()
    st.dataframe(get_df("SELECT * FROM kits ORDER BY id DESC"), use_container_width=True, hide_index=True)


if current_tab == "Cotización":
    st.subheader("Cotización")
    if st.session_state.get("reset_quote_qty"):
        st.session_state["add_prod_qty"] = 1
        st.session_state["add_kit_qty"] = 1
        st.session_state["add_serv_qty"] = 1
        st.session_state["add_supply_qty"] = 1
        st.session_state["reset_quote_qty"] = False
    qcol1, qcol2 = st.columns([1,3])
    with qcol1:
        logo(180)
    with qcol2:
        st.markdown("<h3 style='margin-bottom:0.2rem;'>Cotización</h3>", unsafe_allow_html=True)
        st.caption("Agrega productos, kits y servicios uno por uno. Productos y kits con IVA, servicios exentos.")

    clients_df = get_df("SELECT * FROM clients ORDER BY name")
    vendors_df = get_df("SELECT * FROM vendors ORDER BY name")
    inv_df = get_df("SELECT * FROM inventory ORDER BY description")
    kits_df = get_df("SELECT * FROM kits ORDER BY name")
    products_df = inv_df[inv_df["is_service"] == 0].copy()
    services_df = inv_df[inv_df["is_service"] == 1].copy()
    supplies_db_df = get_df("SELECT * FROM supplies_catalog ORDER BY description")

    if "quote_products" not in st.session_state:
        st.session_state.quote_products = []
    if "quote_services" not in st.session_state:
        st.session_state.quote_services = []
    if "quote_kits" not in st.session_state:
        st.session_state.quote_kits = []
    if "quote_supplies" not in st.session_state:
        st.session_state.quote_supplies = []

    if clients_df.empty:
        st.warning("Primero crea al menos un cliente.")
    else:
        a,b,c = st.columns(3)
        quote_number = a.text_input("N° Cotización", value=f"COT-{pd.Timestamp.now().strftime('%Y%m%d-%H%M')}")
        quote_date = b.date_input("Fecha", value=date.today())
        validity_days = c.number_input("Validez (días)", min_value=1, value=10, step=1)

        c1,c2 = st.columns(2)
        client_name = c1.selectbox("Cliente", clients_df["name"].tolist())
        vendor_name = c2.selectbox("Vendedor", vendors_df["name"].tolist() if not vendors_df.empty else ["Abaroa Smart"])
        client_row = clients_df.loc[clients_df["name"] == client_name].iloc[0].to_dict()
        vendor_row = vendors_df.loc[vendors_df["name"] == vendor_name].iloc[0].to_dict() if not vendors_df.empty else {"id": None}

        d1,d2,d3,d4 = st.columns(4)
        d1.text_input("Nombre", value=str(client_row.get("name","")), disabled=True)
        d2.text_input("Teléfono", value=str(client_row.get("phone","") or ""), disabled=True)
        d3.text_input("Correo", value=str(client_row.get("email","") or ""), disabled=True)
        d4.text_input("Dirección", value=str(client_row.get("address","") or ""), disabled=True)

        st.markdown("### Agregar producto")
        p1,p2,p3 = st.columns([5,1.5,1.5])
        prod_desc = p1.selectbox("Producto", [""] + products_df["description"].tolist(), key="add_prod_desc")
        prod_qty = p2.number_input("Cantidad", min_value=1, value=1, step=1, key="add_prod_qty")
        prow = None
        if prod_desc:
            prow = products_df.loc[products_df["description"] == prod_desc].iloc[0]
            p3.text_input("Precio", value=money(int(prow["sale_price"] or 0)), disabled=True, key="add_prod_price")
        else:
            p3.text_input("Precio", value="", disabled=True, key="add_prod_price")
        if st.button("Agregar producto"):
            if prow is not None:
                unit_price = int(prow["sale_price"] or 0)
                st.session_state.quote_products.append({"sku": prow["sku"], "description": prod_desc, "quantity": int(prod_qty), "unit_price": unit_price, "line_total": int(prod_qty * unit_price)})

        if st.session_state.quote_products:
            stock_alerts = []
            for line in st.session_state.quote_products:
                prod = products_df.loc[products_df["sku"] == line["sku"]]
                if not prod.empty:
                    available = int(prod.iloc[0]["stock_current"] or 0)
                    if int(line["quantity"]) > available:
                        stock_alerts.append(f"Stock insuficiente para {line['description']}: disponible {available}, solicitado {int(line['quantity'])}.")
            for msg in stock_alerts:
                st.warning(msg)
            st.markdown("#### Productos agregados")
            prod_table = pd.DataFrame(st.session_state.quote_products)
            prod_table["unit_price_fmt"] = prod_table["unit_price"].apply(money)
            prod_table["line_total_fmt"] = prod_table["line_total"].apply(money)
            st.dataframe(prod_table[["sku","description","quantity","unit_price_fmt","line_total_fmt"]], use_container_width=True, hide_index=True)
            p1,p2,p3,p4 = st.columns(4)
            options_prod = [""] + [f'{i+1} · {x["description"]}' for i,x in enumerate(st.session_state.quote_products)]
            edit_idx = p1.selectbox("Editar producto", options_prod, key="edit_prod")
            if edit_idx:
                idx = int(edit_idx.split(" · ")[0]) - 1
                new_qty = p2.number_input("Nueva cantidad", min_value=1, value=int(st.session_state.quote_products[idx]["quantity"]), step=1, key="edit_prod_qty")
                if p3.button("Guardar edición"):
                    st.session_state.quote_products[idx]["quantity"] = int(new_qty)
                    st.session_state.quote_products[idx]["line_total"] = int(new_qty) * int(st.session_state.quote_products[idx]["unit_price"])
                    st.success("Producto actualizado.")
            del_idx = p4.selectbox("Eliminar producto", options_prod, key="del_prod")
            if st.button("Quitar producto") and del_idx:
                st.session_state.quote_products.pop(int(del_idx.split(" · ")[0]) - 1)

        st.markdown("### Agregar kit")
        k1,k2,k3 = st.columns([5,1.5,1.5])
        kit_name = k1.selectbox("Kit", [""] + kits_df["name"].tolist(), key="add_kit_name")
        kit_qty = k2.number_input("Cantidad kit", min_value=1, value=1, step=1, key="add_kit_qty")
        krow = None
        if kit_name:
            krow = kits_df.loc[kits_df["name"] == kit_name].iloc[0]
            k3.text_input("Precio kit", value=money(int(krow["sale_price"] or 0)), disabled=True, key="add_kit_price")
        else:
            k3.text_input("Precio kit", value="", disabled=True, key="add_kit_price")
        if st.button("Agregar kit"):
            if krow is not None:
                unit_price = int(krow["sale_price"] or 0)
                st.session_state.quote_kits.append({"code": krow["code"], "name": kit_name, "quantity": int(kit_qty), "unit_price": unit_price, "line_total": int(kit_qty * unit_price)})

        if st.session_state.quote_kits:
            st.markdown("#### Kits agregados")
            kit_table = pd.DataFrame(st.session_state.quote_kits)
            kit_table["unit_price"] = kit_table["unit_price"].apply(money)
            kit_table["line_total"] = kit_table["line_total"].apply(money)
            st.dataframe(kit_table, use_container_width=True, hide_index=True)
            del_idx = st.selectbox("Quitar kit", [""] + [f'{i+1} · {x["name"]}' for i,x in enumerate(st.session_state.quote_kits)], key="del_kit")
            if st.button("Eliminar kit") and del_idx:
                st.session_state.quote_kits.pop(int(del_idx.split(" · ")[0]) - 1)

        st.markdown("### Agregar servicio")
        s1,s2,s3 = st.columns([5,1.5,1.5])
        services_df = services_df.sort_values(["description", "sku"]).drop_duplicates(subset=["sku"]) if not services_df.empty else services_df
        service_options = [""] + [f'{r["sku"]} · {r["description"]}' for _, r in services_df.iterrows()]
        serv_choice = s1.selectbox("Servicio", service_options, key="add_serv_desc")
        serv_qty = s2.number_input("Cantidad servicio", min_value=1, value=1, step=1, key="add_serv_qty")
        srow = None
        if serv_choice:
            serv_sku = serv_choice.split(" · ")[0]
            srow = services_df.loc[services_df["sku"] == serv_sku].iloc[0]
            s3.text_input("Precio servicio", value=money(int(srow["sale_price"] or 0)), disabled=True, key="add_serv_price")
        else:
            s3.text_input("Precio servicio", value="", disabled=True, key="add_serv_price")
        if st.button("Agregar servicio"):
            if srow is not None:
                unit_price = int(srow["sale_price"] or 0)
                st.session_state.quote_services.append({"sku": srow["sku"], "description": str(srow["description"]), "quantity": int(serv_qty), "unit_price": unit_price, "line_total": int(serv_qty * unit_price)})

        if st.session_state.quote_services:
            st.markdown("#### Servicios agregados")
            detail_table = pd.DataFrame(st.session_state.quote_services)
            detail_table["unit_price_fmt"] = detail_table["unit_price"].apply(money)
            detail_table["line_total_fmt"] = detail_table["line_total"].apply(money)
            st.dataframe(detail_table[["sku","description","quantity","unit_price_fmt","line_total_fmt"]], use_container_width=True, hide_index=True)
            st.caption(f"Total servicios: {money(int(sum(int(x['line_total']) for x in st.session_state.quote_services)))}")
            del_idx = st.selectbox("Quitar servicio", [""] + [f'{i+1} · {x["description"]}' for i,x in enumerate(st.session_state.quote_services)], key="del_serv")
            if st.button("Eliminar servicio") and del_idx:
                st.session_state.quote_services.pop(int(del_idx.split(" · ")[0]) - 1)

        st.markdown("### Agregar insumo")
        supply_names = supplies_db_df["description"].tolist() if not supplies_db_df.empty else []
        if st.session_state.pop("quote_supply_reset_pending", False):
            st.session_state["add_supply_desc_sel"] = ""
            st.session_state["add_supply_desc_new"] = ""
            st.session_state["add_supply_qty"] = 1
            st.session_state["add_supply_unit"] = 0
        if "add_supply_unit" not in st.session_state:
            st.session_state["add_supply_unit"] = 0
        if "add_supply_desc_new" not in st.session_state:
            st.session_state["add_supply_desc_new"] = ""
        if "add_supply_qty" not in st.session_state:
            st.session_state["add_supply_qty"] = 1
        if "add_supply_desc_sel" not in st.session_state:
            st.session_state["add_supply_desc_sel"] = ""
        i1,i2,i3,i4 = st.columns([4,2,2,1.5])
        supply_desc = i1.selectbox("Insumo", [""] + supply_names + ["Nuevo insumo..."], key="add_supply_desc_sel", on_change=refresh_quote_supply_unit_from_master)
        custom_supply_desc = ""
        if supply_desc == "Nuevo insumo...":
            custom_supply_desc = st.text_input("Descripción nuevo insumo", key="add_supply_desc_new")
        supply_qty = i2.number_input("Cantidad insumo", min_value=1, value=int(st.session_state.get("add_supply_qty", 1)), step=1, key="add_supply_qty")
        supply_unit = i3.number_input("Precio unitario insumo", min_value=0, step=100, key="add_supply_unit")
        i4.write("")
        i4.write("")
        if i4.button("Agregar insumo"):
            final_desc = custom_supply_desc.strip() if supply_desc == "Nuevo insumo..." else str(supply_desc or "").strip()
            if final_desc:
                st.session_state.quote_supplies.append({
                    "sku": "INSUMO",
                    "description": final_desc,
                    "quantity": int(supply_qty),
                    "unit_price": int(supply_unit),
                    "line_total": int(supply_qty) * int(supply_unit)
                })
                conn = get_conn()
                q(conn, "INSERT OR IGNORE INTO supplies_catalog (description, default_unit_price) VALUES (?, ?)", (final_desc, int(supply_unit)))
                q(conn, "UPDATE supplies_catalog SET default_unit_price=? WHERE description=?", (int(supply_unit), final_desc))
                conn.close()
                reset_quote_supply_inputs()
                st.success("Insumo agregado a la cotización.")
                st.rerun()

        if st.session_state.quote_supplies:
            st.markdown("#### Insumos agregados")
            sup_table = pd.DataFrame(st.session_state.quote_supplies)
            sup_table["unit_price_fmt"] = sup_table["unit_price"].apply(money)
            sup_table["line_total_fmt"] = sup_table["line_total"].apply(money)
            st.dataframe(sup_table[["sku","description","quantity","unit_price_fmt","line_total_fmt"]], use_container_width=True, hide_index=True)
            s1,s2,s3,s4 = st.columns(4)
            options_supply = [""] + [f'{i+1} · {x["description"]}' for i,x in enumerate(st.session_state.quote_supplies)]
            edit_idx = s1.selectbox("Editar insumo", options_supply, key="edit_supply")
            if edit_idx:
                idx = int(edit_idx.split(" · ")[0]) - 1
                new_qty = s2.number_input("Nueva cantidad insumo", min_value=1, value=int(st.session_state.quote_supplies[idx]["quantity"]), step=1, key="edit_supply_qty")
                if s3.button("Guardar edición insumo"):
                    st.session_state.quote_supplies[idx]["quantity"] = int(new_qty)
                    st.session_state.quote_supplies[idx]["line_total"] = int(new_qty) * int(st.session_state.quote_supplies[idx]["unit_price"])
                    st.success("Insumo actualizado.")
            del_idx = s4.selectbox("Eliminar insumo", options_supply, key="del_supply")
            if st.button("Quitar insumo") and del_idx:
                st.session_state.quote_supplies.pop(int(del_idx.split(" · ")[0]) - 1)

        product_lines = st.session_state.quote_products
        service_lines = st.session_state.quote_services
        kit_lines = st.session_state.quote_kits
        supply_lines = st.session_state.quote_supplies
        subtotal_products = int(sum(x["line_total"] for x in product_lines))
        subtotal_kits = int(sum(x["line_total"] for x in kit_lines))
        subtotal_services = int(sum(x["line_total"] for x in service_lines))
        subtotal_supplies = int(sum(x["line_total"] for x in supply_lines))
        vat_products = int(round((subtotal_products + subtotal_kits + subtotal_supplies) * IVA_RATE, 0))
        total = int(subtotal_products + subtotal_kits + subtotal_services + subtotal_supplies + vat_products)
        product_cost_total = int(sum(int(x["quantity"]) * int(products_df.loc[products_df["sku"] == x["sku"], "cost_unit"].iloc[0]) for x in product_lines if not products_df.loc[products_df["sku"] == x["sku"]].empty))
        kit_cost_total = 0
        for k in kit_lines:
            kcode = k.get("code")
            qty = int(k.get("quantity",1))
            costdf = get_df("SELECT COALESCE(SUM(i.cost_unit * ki.quantity),0) AS cost FROM kit_items ki JOIN kits k2 ON k2.id = ki.kit_id LEFT JOIN inventory i ON i.sku = ki.sku WHERE k2.code = ?", (kcode,))
            if not costdf.empty:
                kit_cost_total += int(costdf.iloc[0]["cost"] or 0) * qty
        supplies_cost_total = int(sum(int(x["line_total"]) for x in supply_lines))
        estimated_cost_total = product_cost_total + kit_cost_total + supplies_cost_total
        estimated_margin = int(total - estimated_cost_total)
        estimated_margin_pct = ((estimated_margin / total) * 100) if total else 0

        r1,r2,r3,r4,r5,r6,r7 = st.columns(7)
        afecto_iva_total = subtotal_products + subtotal_kits + subtotal_supplies
        exento_total = subtotal_services
        r1.metric("Total afecto IVA", money(afecto_iva_total))
        r2.metric("Total exento (servicios)", money(exento_total))
        r3.metric("Subtotal servicios", money(subtotal_services))
        r4.metric("Subtotal insumos", money(subtotal_supplies))
        r5.metric("IVA", money(vat_products))
        r6.metric("TOTAL", money(total))
        r7.metric("Margen Ganancia", f"{money(estimated_margin)} ({estimated_margin_pct:,.1f}%)".replace(",", "."))
        st.caption(f"Costo estimado interno: {money(estimated_cost_total)} | Venta estimada: {money(total)}")

        notes = st.text_area("Términos / notas", value="• Productos, kits e insumos afectos a IVA.\n• Servicios exentos de IVA.")
        internal_notes = st.text_area("Notas internas (no aparecen en PDF)", value="", help="Observaciones internas solo para uso del ERP.")
        status = st.selectbox("Estado", ["Borrador","Enviada","Aceptada","Rechazada","Facturada"])
        g1,g2,g3,g4 = st.columns(4)
        current_quote_pdf = make_quote_pdf(
            quote_number=quote_number,
            quote_date=quote_date,
            client_row=client_row,
            vendor_name=vendor_name,
            product_lines=product_lines,
            kit_lines=kit_lines,
            service_lines=service_lines,
            supply_lines=supply_lines,
            notes=notes,
            subtotal_products=subtotal_products,
            subtotal_kits=subtotal_kits,
            subtotal_services=subtotal_services,
            subtotal_supplies=subtotal_supplies,
            vat_products=vat_products,
            total=total,
        )
        g1.download_button("Descargar PDF cotización", data=current_quote_pdf, file_name=f"{quote_number}.pdf", mime="application/pdf")
        if g2.button("Guardar cotización"):
            validation_errors = validate_quote_before_save(client_row, product_lines, service_lines, kit_lines, supply_lines, products_df)
            stock_warnings = get_quote_stock_warnings(product_lines, products_df)
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
            else:
                for warn in stock_warnings:
                    st.warning(warn)
                final_notes = notes
                if internal_notes.strip():
                    final_notes = final_notes + "\n\n[NOTA INTERNA ERP]\n" + internal_notes.strip()
                quote_id, total_saved = save_quote(quote_number, quote_date.isoformat(), int(client_row["id"]), int(vendor_row["id"]) if vendor_row is not None else None, int(validity_days), status, final_notes, product_lines, service_lines, kit_lines, supply_lines)
                st.session_state["reset_quote_qty"] = True
                st.success(f"Cotización guardada con ID {quote_id}. Total: {money(total_saved)}")
                st.rerun()
        if g3.button("Limpiar cotización"):
            st.session_state.quote_products = []
            st.session_state.quote_services = []
            st.session_state.quote_kits = []
            st.session_state.quote_supplies = []
            st.session_state["reset_quote_qty"] = True
            st.success("Cotización limpia.")
            st.rerun()
        quote_df = get_df("""
            SELECT q.id, q.quote_number, q.quote_date, c.name AS cliente, v.name AS vendedor, q.status, q.total
            FROM quotes q
            LEFT JOIN clients c ON c.id = q.client_id
            LEFT JOIN vendors v ON v.id = q.vendor_id
            ORDER BY q.id DESC
        """)
        if not quote_df.empty:
            q_options = [f'{row["id"]} · {row["quote_number"]} · {row["cliente"]}' for _, row in quote_df.iterrows()]
            q_delete = g4.selectbox("Eliminar cotización guardada", [""] + q_options)
            if g4.button("Eliminar cotización") and q_delete:
                delete_quote(int(q_delete.split(" · ")[0]))
                st.success("Cotización eliminada.")
        st.dataframe(
            quote_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id":           st.column_config.NumberColumn("ID",         format="%d"),
                "quote_number": st.column_config.TextColumn("N° Cotización"),
                "quote_date":   st.column_config.DateColumn("Fecha"),
                "cliente":      st.column_config.TextColumn("Cliente"),
                "vendedor":     st.column_config.TextColumn("Vendedor"),
                "status":       st.column_config.TextColumn("Estado"),
                "total":        st.column_config.NumberColumn("Total CLP",  format="$ %d"),
            }
        )


if current_tab == "Historial Cotizaciones":
    st.subheader("Historial de Cotizaciones")
    quotes_hist = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, c.name AS cliente, v.name AS vendedor, q.status, q.total
        FROM quotes q
        LEFT JOIN clients c ON c.id = q.client_id
        LEFT JOIN vendors v ON v.id = q.vendor_id
        ORDER BY q.id DESC
    """)
    if quotes_hist.empty:
        st.info("No hay cotizaciones guardadas.")
    else:
        st.dataframe(
            quotes_hist,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id":           st.column_config.NumberColumn("ID",         format="%d"),
                "quote_number": st.column_config.TextColumn("N° Cotización"),
                "quote_date":   st.column_config.DateColumn("Fecha"),
                "cliente":      st.column_config.TextColumn("Cliente"),
                "vendedor":     st.column_config.TextColumn("Vendedor"),
                "status":       st.column_config.TextColumn("Estado"),
                "total":        st.column_config.NumberColumn("Total CLP",  format="$ %d"),
            }
        )
        options = [f'{row["id"]} · {row["quote_number"]} · {row["cliente"]}' for _, row in quotes_hist.iterrows()]
        selected_hist = st.selectbox("Selecciona cotización", options)
        quote_id = int(selected_hist.split(" · ")[0]) if selected_hist else None
        ctx = load_quote_context(quote_id) if quote_id else None
        if ctx:
            h = ctx["header"]
            product_lines = ctx["product_lines"]
            service_lines = ctx["service_lines"]
            kit_lines = ctx["kit_lines"]
            supply_lines = ctx["supply_lines"]

            rows = []
            for x in product_lines:
                rows.append({"Tipo":"Producto","Descripción":x["description"],"Cantidad":x["quantity"],"Unitario":money(x["unit_price"]),"Total":money(x["line_total"])})
            for x in kit_lines:
                rows.append({"Tipo":"Kit","Descripción":x["name"],"Cantidad":x["quantity"],"Unitario":money(x["unit_price"]),"Total":money(x["line_total"])})
            for x in supply_lines:
                rows.append({"Tipo":"Insumo","Descripción":x["description"],"Cantidad":x["quantity"],"Unitario":money(x["unit_price"]),"Total":money(x["line_total"])})
            if service_lines:
                service_total = sum(int(x["line_total"]) for x in service_lines)
                rows.append({"Tipo":"Servicio","Descripción":"Servicio Integral de Instalación y Configuración","Cantidad":1,"Unitario":money(service_total),"Total":money(service_total)})

            st.markdown(f"**Estado:** {h.get('status','')}  |  **Cliente:** {ctx['client_row']['name']}  |  **Fecha:** {h.get('quote_date','')}")
            status_options = ["Borrador","Enviada","Aceptada","Rechazada","Facturada"]
            current_status = h.get("status","Borrador")
            hs1, hs2 = st.columns([2,1])
            new_status = hs1.selectbox("Cambiar estado", status_options, index=(status_options.index(current_status) if current_status in status_options else 0))
            if hs2.button("Actualizar estado"):
                conn = get_conn()
                q(conn, "UPDATE quotes SET status=? WHERE id=?", (new_status, quote_id))
                conn.close()
                st.success("Estado actualizado.")
                st.rerun()
            if h.get("notes"):
                notes_clean = str(h.get("notes","")).split("[NOTA INTERNA ERP]")[0].strip()
                if notes_clean:
                    st.caption(notes_clean)
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            current_quote_pdf = make_quote_pdf(
                quote_number=h["quote_number"],
                quote_date=h["quote_date"],
                client_row=ctx["client_row"],
                vendor_name=ctx["vendor_name"],
                product_lines=product_lines,
                kit_lines=kit_lines,
                service_lines=service_lines,
                supply_lines=supply_lines,
                notes=h.get("notes",""),
                subtotal_products=int(h.get("subtotal_products",0)) - int(sum(x["line_total"] for x in kit_lines)) - int(sum(x["line_total"] for x in supply_lines)),
                subtotal_kits=int(sum(x["line_total"] for x in kit_lines)),
                subtotal_services=int(h.get("subtotal_services_exempt",0)),
                subtotal_supplies=int(sum(x["line_total"] for x in supply_lines)),
                vat_products=int(h.get("vat_products",0)),
                total=int(h.get("total",0)),
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.download_button("Descargar PDF", data=current_quote_pdf, file_name=f"{h['quote_number']}.pdf", mime="application/pdf")
            if c2.button("Duplicar cotización"):
                ok, msg = duplicate_quote(quote_id)
                (st.success if ok else st.error)(msg)
            if c3.button("Convertir a venta"):
                ok, msg = convert_quote_to_sale(quote_id)
                (st.success if ok else st.error)(msg)
            if c4.button("Aprobar + crear proyecto"):
                ok, project_id, msg = create_project_from_quote(quote_id)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

if current_tab == "OT":
    st.subheader("Órdenes de Trabajo (OT)")
    ot_df = get_df("""
        SELECT wo.id, wo.ot_number, c.name AS cliente, v.name AS tecnico, wo.status, wo.scheduled_date,
               wo.hours_work, wo.labor_cost, wo.travel_cost, wo.extra_material_cost
        FROM work_orders wo
        LEFT JOIN clients c ON c.id = wo.client_id
        LEFT JOIN vendors v ON v.id = wo.vendor_id
        ORDER BY wo.id DESC
    """)
    clients_df = get_df("SELECT * FROM clients ORDER BY name")
    vendors_df = get_df("SELECT * FROM vendors ORDER BY name")
    quotes_df = get_df("SELECT id, quote_number FROM quotes ORDER BY id DESC")
    ot_options = ["Nueva"] + [f'{row["id"]} · {row["ot_number"]}' for _, row in ot_df.iterrows()]
    ot_sel = st.selectbox("Selecciona OT para editar", ot_options)
    current = ot_df[ot_df["id"] == int(ot_sel.split(" · ")[0])].iloc[0].to_dict() if ot_sel != "Nueva" else {}
    with st.form("wo_form"):
        a,b,c,d = st.columns(4)
        ot_number = a.text_input("N° OT", value=str(current.get("ot_number", f"OT-{pd.Timestamp.now().strftime('%Y%m%d-%H%M')}")))
        client_name = b.selectbox("Cliente", clients_df["name"].tolist() if not clients_df.empty else [], index=0 if clients_df.empty else 0)
        vendor_name = c.selectbox("Técnico / Vendedor", vendors_df["name"].tolist() if not vendors_df.empty else [], index=0 if vendors_df.empty else 0)
        quote_opt = d.selectbox("Cotización asociada", [""] + quotes_df["quote_number"].tolist())
        e,f,g,h = st.columns(4)
        status = e.selectbox("Estado", ["Pendiente","Agendada","En ejecución","Finalizada","Cancelada"], index=0)
        scheduled_date = f.date_input("Fecha programada", value=date.today())
        hours_work = g.number_input("Horas hombre", min_value=0.0, value=float(current.get("hours_work") or 0), step=0.5)
        address = h.text_input("Dirección", value=str(current.get("address","") or ""))
        i,j,k = st.columns(3)
        labor_cost = i.number_input("Costo mano de obra", min_value=0, value=int(current.get("labor_cost") or 0), step=1000)
        travel_cost = j.number_input("Viáticos / traslado", min_value=0, value=int(current.get("travel_cost") or 0), step=1000)
        extra_material_cost = k.number_input("Materiales adicionales", min_value=0, value=int(current.get("extra_material_cost") or 0), step=1000)
        notes = st.text_area("Observaciones")
        s1,s2 = st.columns(2)
        save_btn = s1.form_submit_button("Guardar OT")
        delete_btn = s2.form_submit_button("Eliminar OT")
        if save_btn:
            conn = get_conn()
            client_id = int(clients_df.loc[clients_df["name"] == client_name].iloc[0]["id"]) if not clients_df.empty else None
            vendor_id = int(vendors_df.loc[vendors_df["name"] == vendor_name].iloc[0]["id"]) if not vendors_df.empty else None
            quote_id = int(quotes_df.loc[quotes_df["quote_number"] == quote_opt].iloc[0]["id"]) if quote_opt else None
            if ot_sel == "Nueva":
                q(conn, """
                    INSERT INTO work_orders (ot_number, client_id, vendor_id, quote_id, status, scheduled_date, address, hours_work, labor_cost, travel_cost, extra_material_cost, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ot_number, client_id, vendor_id, quote_id, status, scheduled_date.isoformat(), address, float(hours_work), int(labor_cost), int(travel_cost), int(extra_material_cost), notes))
            else:
                ot_id = int(ot_sel.split(" · ")[0])
                q(conn, """
                    UPDATE work_orders
                    SET ot_number=?, client_id=?, vendor_id=?, quote_id=?, status=?, scheduled_date=?, address=?, hours_work=?, labor_cost=?, travel_cost=?, extra_material_cost=?, notes=?
                    WHERE id=?
                """, (ot_number, client_id, vendor_id, quote_id, status, scheduled_date.isoformat(), address, float(hours_work), int(labor_cost), int(travel_cost), int(extra_material_cost), notes, ot_id))
            conn.close()
            st.success("OT guardada.")
            st.rerun()
        if delete_btn and ot_sel != "Nueva":
            ot_id = int(ot_sel.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM work_order_items WHERE work_order_id = ?", (ot_id,))
            q(conn, "DELETE FROM work_orders WHERE id = ?", (ot_id,))
            conn.close()
            st.success("OT eliminada.")
            st.rerun()

    ot_df2 = get_df("""
        SELECT wo.id, wo.ot_number, c.name AS cliente, v.name AS tecnico, wo.status, wo.scheduled_date,
               wo.address, wo.hours_work, wo.labor_cost, wo.travel_cost, wo.extra_material_cost, wo.quote_id
        FROM work_orders wo
        LEFT JOIN clients c ON c.id = wo.client_id
        LEFT JOIN vendors v ON v.id = wo.vendor_id
        ORDER BY wo.id DESC
    """)
    if not ot_df2.empty:
        ot_choose = st.selectbox("OT para materiales usados", [f'{row["id"]} · {row["ot_number"]}' for _, row in ot_df2.iterrows()])
        ot_id = int(ot_choose.split(" · ")[0])
        inv_products = get_df("SELECT sku, description, cost_unit FROM inventory WHERE is_service = 0 ORDER BY description")
        item_opt = [""] + [f'{row["sku"]} · {row["description"]}' for _, row in inv_products.iterrows()]
        with st.form("wo_item_form"):
            p1,p2 = st.columns(2)
            item = p1.selectbox("Producto usado", item_opt)
            qty = p2.number_input("Cantidad usada", min_value=1, value=1, step=1)
            add_item = st.form_submit_button("Agregar material a OT")
            if add_item and item:
                sku, desc = item.split(" · ", 1)
                row = inv_products.loc[inv_products["sku"] == sku].iloc[0]
                add_wo_item(ot_id, sku, desc, int(qty), int(row["cost_unit"] or 0))
                st.success("Material agregado.")
                st.rerun()
        wo_items_df = get_df("SELECT sku, description, quantity, cost_unit, line_cost FROM work_order_items WHERE work_order_id = ? ORDER BY id DESC", (ot_id,))
        st.dataframe(wo_items_df, use_container_width=True, hide_index=True)
        base_ot = ot_df2.loc[ot_df2["id"] == ot_id].iloc[0]
        materials_cost = int(wo_items_df["line_cost"].sum()) if not wo_items_df.empty else 0
        total_ot_cost = int(base_ot["labor_cost"] or 0) + int(base_ot["travel_cost"] or 0) + int(base_ot["extra_material_cost"] or 0) + materials_cost
        quote_total = 0
        if pd.notna(base_ot["quote_id"]):
            qrow = get_df("SELECT total FROM quotes WHERE id = ?", (int(base_ot["quote_id"]),))
            if not qrow.empty:
                quote_total = int(qrow.iloc[0]["total"] or 0)
        real_margin = quote_total - total_ot_cost
        st.markdown("### Rentabilidad OT")
        r1,r2,r3,r4 = st.columns(4)
        r1.metric("Costo materiales OT", money(materials_cost))
        r2.metric("Costo operativo total", money(total_ot_cost))
        r3.metric("Venta asociada", money(quote_total))
        r4.metric("Margen real OT", money(real_margin))
        ot_pdf = make_pdf(
            title=f"Orden de Trabajo {base_ot['ot_number']}",
            subtitle=f"Cliente: {base_ot['cliente']} | Técnico: {base_ot['tecnico']} | Fecha: {base_ot['scheduled_date']}",
            sections=[
                ("Datos OT", [f"Estado: {base_ot['status']}", f"Dirección: {base_ot['address'] or ''}", f"Horas hombre: {base_ot['hours_work']}", f"Mano de obra: {money(base_ot['labor_cost'] or 0)}", f"Viáticos: {money(base_ot['travel_cost'] or 0)}", f"Materiales adicionales: {money(base_ot['extra_material_cost'] or 0)}"]),
                ("Materiales usados", [f"{row['description']} | Cant: {int(row['quantity'])} | Costo: {money(row['line_cost'])}" for _, row in wo_items_df.iterrows()] or ["Sin materiales"]),
                ("Rentabilidad", [f"Costo materiales OT: {money(materials_cost)}", f"Costo operativo total: {money(total_ot_cost)}", f"Venta asociada: {money(quote_total)}", f"Margen real OT: {money(real_margin)}"])
            ],
        )
        st.download_button("Descargar PDF OT", data=ot_pdf, file_name=f"{base_ot['ot_number']}.pdf", mime="application/pdf")
    st.dataframe(
        ot_df2,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id":                   st.column_config.NumberColumn("ID",          format="%d"),
            "ot_number":            st.column_config.TextColumn("N° OT"),
            "cliente":              st.column_config.TextColumn("Cliente"),
            "tecnico":              st.column_config.TextColumn("Técnico"),
            "status":               st.column_config.TextColumn("Estado"),
            "scheduled_date":       st.column_config.DateColumn("Fecha prog."),
            "address":              st.column_config.TextColumn("Dirección"),
            "hours_work":           st.column_config.NumberColumn("Horas",        format="%.1f hrs"),
            "labor_cost":           st.column_config.NumberColumn("Mano de obra", format="$ %d"),
            "travel_cost":          st.column_config.NumberColumn("Viáticos",     format="$ %d"),
            "extra_material_cost":  st.column_config.NumberColumn("Mat. extra",   format="$ %d"),
            "quote_id":             st.column_config.NumberColumn("Cotización ID", format="%d"),
        }
    )

if current_tab == "Ventas":
    st.subheader("Ventas")
    quotes_df = get_df("""
        SELECT q.id, q.quote_number, c.name AS cliente, q.total, q.status
        FROM quotes q LEFT JOIN clients c ON c.id = q.client_id ORDER BY q.id DESC
    """)
    eligible = quotes_df[quotes_df["status"].isin(["Aceptada","Facturada","Pendiente","Enviada","Borrador"])]
    a,b = st.columns(2)
    if not eligible.empty:
        labels = eligible.apply(lambda x: f'{x["id"]} · {x["quote_number"]} · {x["cliente"]} · {money(x["total"])}', axis=1).tolist()
        selected = a.selectbox("Convertir cotización en venta", [""] + labels)
        if a.button("Registrar venta") and selected:
            quote_id = int(selected.split(" · ")[0])
            ok, msg = convert_quote_to_sale(quote_id)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    sales_df = get_df("""
        SELECT s.id, s.sale_date, c.name AS cliente, s.total, s.material_cost, s.gross_margin, s.gross_margin_pct
        FROM sales s LEFT JOIN clients c ON c.id = s.client_id ORDER BY s.id DESC
    """)
    if not sales_df.empty:
        del_sale = b.selectbox("Eliminar venta", [""] + [f'{row["id"]} · {row["cliente"]}' for _, row in sales_df.iterrows()])
        if b.button("Eliminar venta") and del_sale:
            sale_id = int(del_sale.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM billing WHERE sale_id = ?", (sale_id,))
            q(conn, "DELETE FROM sales WHERE id = ?", (sale_id,))
            conn.close()
            st.success("Venta eliminada.")
            st.rerun()
    st.dataframe(
        sales_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id":               st.column_config.NumberColumn("ID",          format="%d"),
            "sale_date":        st.column_config.DateColumn("Fecha"),
            "cliente":          st.column_config.TextColumn("Cliente"),
            "total":            st.column_config.NumberColumn("Total CLP",   format="$ %d"),
            "material_cost":    st.column_config.NumberColumn("Costo mat.",  format="$ %d"),
            "gross_margin":     st.column_config.NumberColumn("Margen bruto",format="$ %d"),
            "gross_margin_pct": st.column_config.NumberColumn("Margen %",    format="%.1f%%"),
        }
    )

if current_tab == "Facturación":
    st.subheader("Facturación")
    bill_df = get_df("""
        SELECT b.id, b.sale_id, c.name AS cliente, b.total, b.advance_50, b.balance_50, b.payment_status
        FROM billing b LEFT JOIN clients c ON c.id = b.client_id ORDER BY b.id DESC
    """)
    if not bill_df.empty:
        a,b,c = st.columns(3)
        bill_sel = a.selectbox("Selecciona registro", [f'{row["id"]} · {row["cliente"]}' for _, row in bill_df.iterrows()])
        bill_id = int(bill_sel.split(" · ")[0]) if bill_sel else None
        current = bill_df[bill_df["id"] == bill_id].iloc[0].to_dict() if bill_id else {}
        states = ["Pendiente","Anticipo 50%","Pagado"]
        status = b.selectbox("Estado", states, index=(states.index(current.get("payment_status")) if current.get("payment_status") in states else 0))
        if c.button("Guardar estado") and bill_id:
            conn = get_conn()
            q(conn, "UPDATE billing SET payment_status = ? WHERE id = ?", (status, bill_id))
            conn.close()
            st.success("Estado actualizado.")
            st.rerun()
        if bill_id:
            pdf_row = current
            sale_items = get_df("""
                SELECT qi.item_type, qi.description, qi.quantity, qi.unit_price, qi.line_total
                FROM sales s
                LEFT JOIN quotes q ON q.id = s.quote_id
                LEFT JOIN quote_items qi ON qi.quote_id = q.id
                WHERE s.id = ?
            """, (int(pdf_row.get('sale_id')),))
            service_total_pdf = int(sale_items.loc[sale_items["item_type"] == "servicio", "line_total"].sum()) if not sale_items.empty else 0
            item_lines_pdf = [f"{r['description']} | Cant: {int(r['quantity'])} | Total: {money(r['line_total'])}" for _, r in sale_items[sale_items["item_type"].isin(["producto","kit","insumo"])].iterrows()] if not sale_items.empty else []
            if service_total_pdf:
                item_lines_pdf.append(f"Servicio Integral de Instalación y Configuración | Cant: 1 | Total: {money(service_total_pdf)}")
            bill_pdf = make_pdf(
                title=f"Orden de Compra - Facturación #{pdf_row.get('id')}",
                subtitle=f"Cliente: {pdf_row.get('cliente')} | Venta: {pdf_row.get('sale_id')}",
                sections=[
                    ("Cobros", item_lines_pdf or ["Sin detalle"]),
                    ("Resumen", [f"Total: {money(pdf_row.get('total',0))}", f"Anticipo 50%: {money(pdf_row.get('advance_50',0))}", f"Saldo 50%: {money(pdf_row.get('balance_50',0))}", f"Estado: {pdf_row.get('payment_status','')}"])
                ],
            )
            st.download_button("Descargar PDF facturación", data=bill_pdf, file_name=f"facturacion_{bill_id}.pdf", mime="application/pdf")
        if st.button("Eliminar facturación") and bill_id:
            conn = get_conn()
            q(conn, "DELETE FROM billing WHERE id = ?", (bill_id,))
            conn.close()
            st.success("Registro eliminado.")
            st.rerun()
    st.dataframe(
        bill_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id":             st.column_config.NumberColumn("ID",         format="%d"),
            "sale_id":        st.column_config.NumberColumn("Venta ID",   format="%d"),
            "cliente":        st.column_config.TextColumn("Cliente"),
            "total":          st.column_config.NumberColumn("Total",      format="$ %d"),
            "advance_50":     st.column_config.NumberColumn("Anticipo 50%", format="$ %d"),
            "balance_50":     st.column_config.NumberColumn("Saldo 50%",  format="$ %d"),
            "payment_status": st.column_config.TextColumn("Estado pago"),
        }
    )
    if not bill_df.empty and bill_id:
        sale_items = get_df("""
            SELECT qi.item_type, qi.description, qi.quantity, qi.unit_price, qi.line_total
            FROM billing b
            LEFT JOIN sales s ON s.id = b.sale_id
            LEFT JOIN quotes q ON q.id = s.quote_id
            LEFT JOIN quote_items qi ON qi.quote_id = q.id
            WHERE b.id = ?
        """, (bill_id,))
        if not sale_items.empty:
            grouped_rows = sale_items[sale_items["item_type"].isin(["producto","kit","insumo"])][["description","quantity","unit_price","line_total"]].copy()
            service_total = int(sale_items.loc[sale_items["item_type"]=="servicio","line_total"].sum())
            if service_total:
                grouped_rows.loc[len(grouped_rows)] = ["Servicio Integral de Instalación y Configuración", 1, service_total, service_total]
            grouped_rows["unit_price"] = grouped_rows["unit_price"].apply(money)
            grouped_rows["line_total"] = grouped_rows["line_total"].apply(money)
            st.markdown("**Cobros incluidos en la facturación**")
            st.dataframe(grouped_rows, use_container_width=True, hide_index=True)




if current_tab == "Administración":
    st.subheader("Administración")
    if not admin_logged_in():
        st.warning("Debes iniciar sesión para acceder al panel de administración.")
        a1, a2 = st.columns([1,1])
        with a1:
            admin_user = st.text_input("Usuario administrador", key="admin_login_user")
            admin_pass = st.text_input("Contraseña administrador", type="password", key="admin_login_pass")
            if st.button("Ingresar al panel", key="admin_login_button"):
                if verify_admin_credentials(admin_user, admin_pass):
                    st.session_state["admin_logged_in"] = True
                    st.success("Sesión iniciada correctamente.")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
            st.caption("Credenciales iniciales: admin / admin123")
    else:
        st.success(f"Sesión activa como {get_setting('admin_username', 'admin')}")
        t1, t2 = st.tabs(["Credenciales", "Mantenimiento"])
        with t1:
            c1, c2 = st.columns(2)
            with c1:
                current_user = get_setting('admin_username', 'admin')
                new_user = st.text_input("Usuario", value=current_user, key="admin_new_user")
                current_pass = st.text_input("Contraseña actual", type="password", key="admin_current_pass")
                new_pass = st.text_input("Nueva contraseña", type="password", key="admin_new_pass")
                confirm_pass = st.text_input("Confirmar nueva contraseña", type="password", key="admin_confirm_pass")
                if st.button("Guardar credenciales", key="admin_save_credentials"):
                    if not verify_admin_credentials(current_user, current_pass):
                        st.error("La contraseña actual no es válida.")
                    elif not new_user.strip():
                        st.error("El usuario no puede quedar vacío.")
                    elif new_pass and new_pass != confirm_pass:
                        st.error("La nueva contraseña y su confirmación no coinciden.")
                    else:
                        set_setting('admin_username', new_user.strip())
                        if new_pass:
                            set_setting('admin_password_hash', hash_password(new_pass))
                        st.success("Credenciales actualizadas.")
            with c2:
                st.markdown("### Restablecer acceso")
                st.info("Si necesitas volver al acceso base, puedes restaurar las credenciales por defecto.")
                if st.button("Restablecer a admin / admin123", key="admin_reset_default"):
                    set_setting('admin_username', 'admin')
                    set_setting('admin_password_hash', hash_password('admin123'))
                    st.success("Credenciales restablecidas.")
        with t2:
            m1, m2 = st.columns(2)
            with m1:
                if st.button("Ir a Respaldos", key="admin_go_backup", use_container_width=True):
                    st.session_state['current_tab'] = 'Respaldo y Restauración'
                    st.rerun()
                if st.button("Cerrar sesión administrativa", key="admin_logout_btn", use_container_width=True):
                    st.session_state['admin_logged_in'] = False
                    st.rerun()
            with m2:
                st.markdown("### Estado operativo")
                st.write(f"Base de datos: `{DB_PATH.name}`")
                st.write(f"Respaldos detectados: {len(list_backups())}")
                st.write(f"Exportaciones JSON: {len(list(APP_DIR.glob('export_abaroa_smart_*.json')))}")

if current_tab == "Garantías":
    st.subheader("Garantías")
    warranties_df = get_df("""
        SELECT w.id, c.name AS cliente, w.install_date, w.warranty_months, w.expiry_date, w.status, w.notes, w.sale_id
        FROM warranties w
        LEFT JOIN clients c ON c.id = w.client_id
        ORDER BY w.id DESC
    """)
    if warranties_df.empty:
        st.info("No hay garantías registradas.")
    else:
        today = date.today()
        def calc_status(expiry):
            try:
                exp = datetime.fromisoformat(str(expiry)).date()
                if exp < today:
                    return "Vencida"
                elif (exp - today).days <= 30:
                    return "Por vencer"
                return "Vigente"
            except Exception:
                return "Sin fecha"
        warranties_df["Estado actual"] = warranties_df["expiry_date"].apply(calc_status)
        st.dataframe(
            warranties_df[["id","cliente","sale_id","install_date","expiry_date","Estado actual","warranty_months","notes"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "id":              st.column_config.NumberColumn("ID",           format="%d"),
                "cliente":         st.column_config.TextColumn("Cliente"),
                "sale_id":         st.column_config.NumberColumn("Venta ID",     format="%d"),
                "install_date":    st.column_config.DateColumn("Fecha instalación"),
                "expiry_date":     st.column_config.DateColumn("Vence"),
                "Estado actual":   st.column_config.TextColumn("Estado"),
                "warranty_months": st.column_config.NumberColumn("Meses",        format="%d meses"),
                "notes":           st.column_config.TextColumn("Notas"),
            }
        )

if current_tab == "Respaldo y Restauración":
    st.subheader("Respaldo y Restauración")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### Crear respaldo")
        backup_name = st.text_input("Nombre opcional del respaldo", value="abaroa_smart")
        if st.button("Crear respaldo ahora"):
            bk = backup_database(backup_name.strip().replace(" ", "_"))
            if bk:
                st.success(f"Respaldo creado: {bk.name}")
            else:
                st.error("No se encontró la base de datos para respaldar.")

        backups = list_backups()
        if backups:
            latest = backups[0]
            st.markdown("### Descargar último respaldo")
            st.download_button(
                "Descargar respaldo .db",
                data=latest.read_bytes(),
                file_name=latest.name,
                mime="application/octet-stream"
            )
        else:
            st.info("Aún no hay respaldos creados.")

    with c2:
        st.markdown("### Restaurar respaldo")
        backups = list_backups()
        backup_names = [p.name for p in backups]
        sel_backup = st.selectbox("Selecciona respaldo guardado", [""] + backup_names)
        if st.button("Restaurar respaldo seleccionado"):
            if not sel_backup:
                st.error("Selecciona un respaldo.")
            else:
                ok, msg = restore_backup(sel_backup)
                (st.success if ok else st.error)(msg)

        st.markdown("### Restaurar desde archivo .db")
        up_db = st.file_uploader("Cargar respaldo SQLite", type=["db"], key="restore_db")
        if st.button("Restaurar desde archivo cargado"):
            if up_db is None:
                st.error("Debes cargar un archivo .db")
            else:
                ok, msg = restore_from_uploaded_db(up_db.getvalue())
                (st.success if ok else st.error)(msg)

    st.markdown("---")
    st.markdown("### Exportación adicional")
    e1, e2 = st.columns(2)
    with e1:
        if st.button("Exportar datos a JSON"):
            out = export_all_data_json()
            st.success(f"Exportación creada: {out.name}")
        exports = sorted(APP_DIR.glob("export_abaroa_smart_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if exports:
            st.download_button(
                "Descargar último JSON",
                data=exports[0].read_bytes(),
                file_name=exports[0].name,
                mime="application/json"
            )
    with e2:
        st.info("Consejo: antes de instalar una nueva versión, crea un respaldo .db. Luego prueba la nueva versión en otra carpeta y restaura el respaldo si hace falta.")

if current_tab == "Proyectos":
    st.subheader("Proyectos")
    st.caption("Flujo operacional llave en mano: proyecto, reserva de stock, checklist, acta de entrega y cierre técnico.")

    quotes_for_project = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, q.status, q.total, c.name AS cliente
        FROM quotes q
        LEFT JOIN clients c ON c.id = q.client_id
        ORDER BY q.id DESC
    """)
    projects_df = get_df("""
        SELECT p.id, p.project_number, p.name, p.status, p.technical_status, p.installation_date,
               p.configuration_url, c.name AS cliente, q.quote_number,
               COALESCE(SUM(pi.reserved_quantity),0) AS reservado,
               COALESCE(SUM(pi.used_quantity),0) AS consumido
        FROM projects p
        LEFT JOIN clients c ON c.id = p.client_id
        LEFT JOIN quotes q ON q.id = p.quotation_id
        LEFT JOIN project_items pi ON pi.project_id = p.id
        WHERE COALESCE(p.is_active,1) = 1
        GROUP BY p.id, p.project_number, p.name, p.status, p.technical_status, p.installation_date,
                 p.configuration_url, c.name, q.quote_number
        ORDER BY p.id DESC
    """)

    with st.expander("Crear proyecto desde cotización aprobada", expanded=False):
        if quotes_for_project.empty:
            st.info("No hay cotizaciones disponibles.")
        else:
            available_rows = []
            for _, row in quotes_for_project.iterrows():
                pid = project_exists_for_quote(int(row["id"]))
                if not pid:
                    available_rows.append(row)
            if not available_rows:
                st.info("Todas las cotizaciones ya tienen proyecto asociado.")
            else:
                options = [f'{int(r["id"])} · {r["quote_number"]} · {r["cliente"]} · {r["status"]}' for r in available_rows]
                a,b = st.columns(2)
                selected = a.selectbox("Cotización", options)
                inst_date = b.date_input("Fecha instalación", value=date.today(), key="proj_install_date")
                config_url = st.text_input("URL configuración / respaldo", key="proj_config_url")
                proj_notes = st.text_area("Notas del proyecto", key="proj_notes")
                if st.button("Crear proyecto desde cotización", key="create_project_btn"):
                    qid = int(selected.split(" · ")[0])
                    ok, project_id, msg = create_project_from_quote(qid, installation_date=inst_date.isoformat(), configuration_url=config_url, notes=proj_notes)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

    st.markdown("### Listado de proyectos")
    if projects_df.empty:
        st.info("Aún no hay proyectos.")
    else:
        st.dataframe(
            projects_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id":                st.column_config.NumberColumn("ID",       format="%d"),
                "project_number":    st.column_config.TextColumn("N° Proyecto"),
                "name":              st.column_config.TextColumn("Nombre"),
                "status":            st.column_config.TextColumn("Estado"),
                "technical_status":  st.column_config.TextColumn("Estado técnico"),
                "installation_date": st.column_config.DateColumn("Fecha instalación"),
                "cliente":           st.column_config.TextColumn("Cliente"),
                "quote_number":      st.column_config.TextColumn("Cotización"),
                "reservado":         st.column_config.NumberColumn("Reservado", format="%d"),
                "consumido":         st.column_config.NumberColumn("Consumido", format="%d"),
                "configuration_url": st.column_config.LinkColumn("URL Config.", display_text="Abrir"),
            }
        )
        selected_project = st.selectbox(
            "Selecciona proyecto",
            [f'{int(r["id"])} · {r["project_number"]} · {r["cliente"]}' for _, r in projects_df.iterrows()],
            key="selected_project"
        )
        project_id = int(selected_project.split(" · ")[0]) if selected_project else None

        if project_id:
            project = get_df("""
                SELECT p.*, c.name AS cliente, c.address, c.phone, q.quote_number
                FROM projects p
                LEFT JOIN clients c ON c.id = p.client_id
                LEFT JOIN quotes q ON q.id = p.quotation_id
                WHERE p.id = ?
            """, (project_id,)).iloc[0].to_dict()
            items_df = get_df("SELECT * FROM project_items WHERE project_id = ? ORDER BY id", (project_id,))
            checklist_df = get_df("""
                SELECT pci.id, pci.item_text, pci.is_required, pci.is_checked, pci.evidence_note
                FROM project_checklists pc
                JOIN project_checklist_items pci ON pci.project_checklist_id = pc.id
                WHERE pc.id = (SELECT id FROM project_checklists WHERE project_id = ? ORDER BY id DESC LIMIT 1)
                ORDER BY pci.id
            """, (project_id,))
            move_df = get_df("""
                SELECT created_at, sku, movement_type, quantity, notes
                FROM inventory_movements
                WHERE reference_type = 'project' AND reference_id = ?
                ORDER BY id DESC
            """, (project_id,))

            st.markdown(f"### {project['project_number']} · {project['cliente']}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Estado", str(project.get("status","")))
            m2.metric("Estado técnico", str(project.get("technical_status","")))
            m3.metric("Reservado", int(projects_df.loc[projects_df['id']==project_id, 'reservado'].iloc[0]))
            m4.metric("Consumido", int(projects_df.loc[projects_df['id']==project_id, 'consumido'].iloc[0]))
            st.caption(f"Cotización origen: {project.get('quote_number','')} · Fecha instalación: {project.get('installation_date','') or '-'}")

            with st.expander("Editar cabecera del proyecto", expanded=True):
                with st.form(f"project_header_{project_id}"):
                    c1, c2 = st.columns(2)
                    name = c1.text_input("Nombre del proyecto", value=str(project.get("name", "") or ""))
                    installation_date_val = c2.date_input("Fecha instalación", value=(datetime.fromisoformat(project["installation_date"]).date() if project.get("installation_date") else date.today()))
                    c3, c4 = st.columns(2)
                    delivery_date_raw = project.get("delivery_date")
                    delivery_date_val = datetime.fromisoformat(delivery_date_raw).date() if delivery_date_raw else date.today()
                    status_values = ["Pendiente","Aprobado","En ejecución","Cerrado","Cancelado"]
                    tech_values = ["Pendiente","En Proceso","Pruebas","Finalizado"]
                    status = c3.selectbox("Estado proyecto", status_values, index=(status_values.index(project.get("status","Pendiente")) if project.get("status","Pendiente") in status_values else 0))
                    technical_status = c4.selectbox("Estado técnico", tech_values, index=(tech_values.index(project.get("technical_status","Pendiente")) if project.get("technical_status","Pendiente") in tech_values else 0))
                    configuration_url = st.text_input("URL configuración / respaldo", value=str(project.get("configuration_url", "") or ""))
                    description = st.text_area("Descripción", value=str(project.get("description", "") or ""), height=80)
                    notes = st.text_area("Notas técnicas", value=str(project.get("notes", "") or ""), height=120)
                    save_header = st.form_submit_button("Guardar cabecera del proyecto")
                    if save_header:
                        conn = get_conn()
                        q(conn, """UPDATE projects SET name=?, installation_date=?, delivery_date=?, status=?, technical_status=?, configuration_url=?, description=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                          (name.strip(), installation_date_val.isoformat(), delivery_date_val.isoformat(), status, technical_status, configuration_url.strip(), description.strip(), notes.strip(), project_id))
                        conn.close()
                        st.success("Proyecto actualizado.")
                        st.rerun()

            st.markdown("#### Acciones rápidas")
            a,b,c,d,e = st.columns(5)
            if a.button("Guardar estado rápido", key=f"quick_status_{project_id}"):
                conn = get_conn()
                q(conn, "UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (project_id,))
                conn.close()
                st.success("Proyecto sincronizado.")
            if b.button("Liberar reserva", key=f"release_{project_id}"):
                release_reserved_stock_for_project(project_id)
                st.success("Reserva liberada.")
                st.rerun()
            if c.button("Consumir inventario", key=f"consume_{project_id}"):
                consume_inventory_for_project(project_id)
                st.success("Consumo real registrado.")
                st.rerun()
            valid, msg = validate_project_completion(project_id)
            acta_pdf = make_project_delivery_pdf(project_id)
            d.download_button("Descargar acta PDF", data=acta_pdf or b"", file_name=f"Acta_Entrega_{project['project_number']}.pdf", mime="application/pdf", disabled=acta_pdf is None, key=f"acta_{project_id}")
            if e.button("Cerrar proyecto", key=f"close_{project_id}"):
                valid, msg = validate_project_completion(project_id)
                if not valid:
                    st.error(msg)
                else:
                    conn = get_conn()
                    q(conn, "UPDATE projects SET status='Cerrado', technical_status='Finalizado', delivery_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (date.today().isoformat(), project_id))
                    q(conn, "UPDATE project_checklists SET status='Completo', completed_at=?, completed_by=? WHERE project_id=?", (datetime.now().isoformat(timespec='seconds'), 'Abaroa Smart', project_id))
                    conn.close()
                    st.success("Proyecto cerrado correctamente.")
                    st.rerun()
            st.info(msg)

            st.markdown("#### Ítems del proyecto")
            if items_df.empty:
                st.info("No hay ítems asociados.")
            else:
                items_show = items_df.copy()
                items_show['disponible_reserva'] = items_show.apply(lambda r: '' if str(r.get('item_type','')) == 'servicio' else int(r.get('quantity') or 0) - int(r.get('reserved_quantity') or 0), axis=1)
                items_show["unit_cost"] = items_show["unit_cost"].apply(money)
                items_show["unit_price"] = items_show["unit_price"].apply(money)
                items_show["total_price"] = items_show["total_price"].apply(money)
                st.dataframe(items_show[["id","item_type","sku","description","quantity","reserved_quantity","used_quantity","disponible_reserva","unit_cost","unit_price","total_price"]], use_container_width=True, hide_index=True)

                edit_options = [f'{int(r["id"])} · {r["description"]} · {r["sku"] or "-"}' for _, r in items_df.iterrows()]
                selected_item = st.selectbox("Editar ítem del proyecto", edit_options, key=f"project_item_select_{project_id}")
                item_id = int(selected_item.split(" · ")[0])
                item_row = items_df[items_df["id"] == item_id].iloc[0].to_dict()
                with st.form(f"project_item_form_{project_id}_{item_id}"):
                    i1, i2, i3, i4 = st.columns(4)
                    qty = i1.number_input("Cantidad comprada", min_value=0, value=int(item_row.get("quantity") or 0), step=1)
                    used_qty = i2.number_input("Cantidad usada real", min_value=0, value=int(item_row.get("used_quantity") or 0), step=1)
                    unit_cost = i3.number_input("Costo unitario", min_value=0, value=int(item_row.get("unit_cost") or 0), step=100)
                    unit_price = i4.number_input("Precio unitario", min_value=0, value=int(item_row.get("unit_price") or 0), step=100)
                    description = st.text_input("Descripción", value=str(item_row.get("description") or ""))
                    s1, s2 = st.columns(2)
                    save_item = s1.form_submit_button("Guardar ítem")
                    delete_item = s2.form_submit_button("Eliminar ítem")
                    if save_item:
                        total_price = int(qty) * int(unit_price)
                        conn = get_conn()
                        q(conn, "UPDATE project_items SET description=?, quantity=?, unit_cost=?, unit_price=?, total_price=? WHERE id=?", (description.strip(), int(qty), int(unit_cost), int(unit_price), int(total_price), item_id))
                        conn.close()
                        ok_usage, msg_usage = sync_project_item_usage(item_id, int(used_qty))
                        if not ok_usage:
                            st.error(msg_usage)
                        else:
                            st.success("Ítem actualizado.")
                            st.rerun()
                    if delete_item:
                        conn = get_conn()
                        q(conn, "DELETE FROM project_items WHERE id=?", (item_id,))
                        conn.close()
                        st.success("Ítem eliminado.")
                        st.rerun()

            st.markdown("#### Checklist de entrega")
            if checklist_df.empty:
                if st.button("Crear checklist", key=f"create_checklist_{project_id}"):
                    create_project_checklist(project_id)
                    st.success("Checklist creado.")
                    st.rerun()
            else:
                for _, row in checklist_df.iterrows():
                    ck = st.checkbox(
                        row["item_text"] + (" *" if int(row["is_required"] or 0) else ""),
                        value=bool(row["is_checked"]),
                        key=f"ck_{int(row['id'])}"
                    )
                    raw_note = row["evidence_note"]
                    note_value = "" if pd.isna(raw_note) else str(raw_note or "")
                    note = st.text_input("Evidencia / nota", value=note_value, key=f"ck_note_{int(row['id'])}")
                    if st.button("Guardar ítem", key=f"save_ck_{int(row['id'])}"):
                        conn = get_conn()
                        q(conn, "UPDATE project_checklist_items SET is_checked=?, checked_at=?, evidence_note=? WHERE id=?", (1 if ck else 0, datetime.now().isoformat(timespec='seconds') if ck else None, note, int(row["id"])))
                        conn.close()
                        st.success("Checklist actualizado.")
                        st.rerun()

            st.markdown("#### Movimientos del proyecto")
            if move_df.empty:
                st.caption("Aún no hay movimientos.")
            else:
                st.dataframe(
                    move_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "created_at":    st.column_config.TextColumn("Fecha/Hora"),
                        "sku":           st.column_config.TextColumn("SKU"),
                        "movement_type": st.column_config.TextColumn("Tipo movimiento"),
                        "quantity":      st.column_config.NumberColumn("Cantidad", format="%d"),
                        "notes":         st.column_config.TextColumn("Notas"),
                    }
                )

            st.markdown("#### Costeo real de compra (base)")
            inv_products = get_df("SELECT sku, description, cost_unit, average_landed_cost FROM inventory WHERE is_service = 0 ORDER BY description")
            if not inv_products.empty:
                opts = [f'{r["sku"]} · {r["description"]}' for _, r in inv_products.iterrows()]
                c1,c2,c3,c4,c5 = st.columns(5)
                selected_sku = c1.selectbox("Producto", opts, key="landed_sku")
                qty = c2.number_input("Cantidad lote", min_value=1, value=1, step=1, key="landed_qty")
                unit_price = c3.number_input("Precio compra unit.", min_value=0, value=0, step=100, key="landed_unit")
                shipping = c4.number_input("Envío total", min_value=0, value=0, step=100, key="landed_ship")
                customs = c5.number_input("Aduana / impuestos", min_value=0, value=0, step=100, key="landed_customs")
                other = st.number_input("Otros costos", min_value=0, value=0, step=100, key="landed_other")
                landed = landed_cost_per_unit(unit_price, customs, shipping, other, qty)
                st.metric("Costo real unitario", money(landed))
                if st.button("Guardar costo real del lote"):
                    sku = selected_sku.split(" · ")[0]
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO purchase_batches (supplier_name, purchase_date, shipping_cost, customs_cost, other_costs) VALUES (?, ?, ?, ?, ?)", ("Proveedor general", date.today().isoformat(), int(shipping), int(customs), int(other)))
                    batch_id = cur.lastrowid
                    cur.execute("INSERT INTO purchase_batch_items (batch_id, product_sku, quantity, unit_price, landed_cost) VALUES (?, ?, ?, ?, ?)", (batch_id, sku, int(qty), int(unit_price), int(landed)))
                    inv = cur.execute("SELECT stock_current, average_landed_cost FROM inventory WHERE sku = ?", (sku,)).fetchone()
                    current_stock = int(inv["stock_current"] or 0) if inv else 0
                    current_avg = int(inv["average_landed_cost"] or 0) if inv else 0
                    total_qty = current_stock + int(qty)
                    new_avg = landed if total_qty <= 0 else int(round(((current_stock * current_avg) + (int(qty) * landed)) / max(total_qty, 1), 0))
                    cur.execute("UPDATE inventory SET average_landed_cost = ? WHERE sku = ?", (new_avg, sku))
                    conn.commit()
                    conn.close()
                    st.success("Costo real guardado y costo promedio actualizado.")
                    st.rerun()



