"""
seed_data.py — Abaroa Smart ERP
Script para llenar la BD con datos de prueba realistas.
Ejecutar: python seed_data.py
"""

import sqlite3
from database import get_conn
from datetime import datetime, timedelta
import random

def seed_database(clear_first=False):
    conn = get_conn()
    cursor = conn.cursor()
    
    if clear_first:
        print("🗑️ Limpiando tablas...")
        tables = ["inventory_movements", "quote_items", "quotes", "billing", "sales", "kit_items", "kits",
                  "installations", "warranties", "purchase_batch_items", "purchase_batches", "tools_assets", 
                  "inventory", "clients", "vendors", "suppliers"]
        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
            except:
                pass
        conn.commit()
    
    print("📦 Cargando datos de prueba...")
    
    # CLIENTES
    print("👥 Insertando clientes...")
    clients = [
        ("Acme Corporation", "+56 9 1234 5678", "contacto@acme.cl", "Av. Principal 100", "12.345.678-9"),
        ("Tech Solutions Ltd", "+56 9 2345 6789", "info@techsol.cl", "Paseo Nortino 500", "98.765.432-1"),
        ("Industrial Chile", "+56 9 3456 7890", "ventas@industrial.cl", "Camino Antiguo 200", "45.678.901-2"),
        ("Smart Homes Inc", "+56 9 4567 8901", "contact@smarthomes.cl", "Calle Nueva 150", "34.567.890-3"),
        ("Energy Systems", "+56 9 5678 9012", "support@energy.cl", "Av. Libertad 300", "23.456.789-4"),
        ("Building Tech", "+56 9 6789 0123", "info@building.cl", "Diagonal Oriente 450", "11.234.567-8"),
        ("Automation Pro", "+56 9 7890 1234", "sales@autopro.cl", "Eje Central 600", "99.887.766-5"),
        ("Residential Solutions", "+56 9 8901 2345", "hello@residential.cl", "Pasaje Sur 75", "55.443.322-1"),
    ]
    
    for name, phone, email, address, rut in clients:
        cursor.execute("INSERT INTO clients(name, phone, email, address, rut) VALUES(?, ?, ?, ?, ?)",
                      (name, phone, email, address, rut))
    conn.commit()
    client_ids = [row[0] for row in cursor.execute("SELECT id FROM clients").fetchall()]
    print(f"✓ {len(client_ids)} clientes cargados")
    
    # PROVEEDORES
    print("🚚 Insertando proveedores...")
    suppliers = [
        ("Electroparts Global", "+56 2 5555 1111", "sales@electroparts.cl", "Juan García", "Distribuidor principal"),
        ("Smart Components Ltd", "+56 2 6666 2222", "info@smartcomp.cl", "María Rodríguez", "Especialista en sensores"),
        ("Security Systems Co", "+56 2 7777 3333", "contact@security.cl", "Carlos López", "Equipos de vigilancia"),
        ("Climate Control Plus", "+56 2 8888 4444", "sales@climate.cl", "Ana Martínez", "Sistemas de climatización"),
    ]
    
    for name, phone, email, contact, notes in suppliers:
        cursor.execute("INSERT INTO suppliers(name, phone, email, contact_person, notes) VALUES(?, ?, ?, ?, ?)",
                      (name, phone, email, contact, notes))
    conn.commit()
    supplier_names = [row[0] for row in cursor.execute("SELECT name FROM suppliers").fetchall()]
    print(f"✓ {len(supplier_names)} proveedores cargados")
    
    # VENDEDORES
    print("🤝 Insertando vendedores...")
    vendors = [
        ("Roberto Silva", "roberto@abaroa.cl", "+56 9 1111 1111", "Jefe Comercial"),
        ("Sandra Mendez", "sandra@abaroa.cl", "+56 9 2222 2222", "Ejecutiva Ventas"),
        ("Miguel Torres", "miguel@abaroa.cl", "+56 9 3333 3333", "Asesor Técnico"),
        ("Patricia Flores", "patricia@abaroa.cl", "+56 9 4444 4444", "Gerente Zona"),
    ]
    
    for name, email, phone, role in vendors:
        cursor.execute("INSERT INTO vendors(name, email, phone, role) VALUES(?, ?, ?, ?)",
                      (name, email, phone, role))
    conn.commit()
    vendor_ids = [row[0] for row in cursor.execute("SELECT id FROM vendors").fetchall()]
    print(f"✓ {len(vendor_ids)} vendedores cargados")
    
    # INVENTARIO
    print("📦 Insertando productos...")
    inventory_products = [
        ("PRD-INT-0001", "Switch Inteligente WiFi 16A", "Interruptores", "Domótica", 50, 0, 8500, 40, 1, supplier_names[0]),
        ("PRD-INT-0002", "Switch Táctil Doble 10A", "Interruptores", "Domótica", 30, 0, 12000, 35, 1, supplier_names[0]),
        ("PRD-CAM-0001", "Cámara 4K Indoor IP", "Cámaras", "Vigilancia", 15, 0, 45000, 30, 1, supplier_names[1]),
        ("PRD-CAM-0002", "Cámara Domo Exterior 2MP", "Cámaras", "Vigilancia", 20, 0, 28000, 35, 1, supplier_names[1]),
        ("PRD-SEN-0001", "Sensor Movimiento PIR", "Sensores", "Detección", 100, 0, 3500, 60, 1, supplier_names[1]),
        ("PRD-SEN-0002", "Sensor Temperatura/Humedad", "Sensores", "Ambiental", 75, 0, 5500, 50, 1, supplier_names[1]),
        ("PRD-SEN-0003", "Sensor Puerta/Ventana", "Sensores", "Acceso", 200, 0, 2500, 70, 1, supplier_names[1]),
        ("PRD-CLI-0001", "Split Inverter 12000BTU", "Clima", "Climatización", 8, 0, 350000, 25, 1, supplier_names[3]),
        ("PRD-CLI-0002", "Termostato Inteligente WiFi", "Clima", "Control", 25, 0, 45000, 40, 1, supplier_names[3]),
        ("PRD-CFG-0001", "Panel de Control Centralizado", "Configuraciones", "Control", 5, 0, 180000, 22, 1, supplier_names[2]),
        ("PRD-CFG-0002", "Hub Conectividad WiFi 6", "Configuraciones", "Redes", 12, 0, 65000, 35, 1, supplier_names[0]),
        ("INS-0001", "Cable UTP Cat6 x 100m", "Insumos", "Cableado", 500, 0, 12000, 50, 1, supplier_names[0]),
        ("INS-0002", "Conectores RJ45 (caja 50)", "Insumos", "Conectores", 200, 0, 8000, 60, 1, supplier_names[0]),
        ("INS-0003", "Placa de 2 Espacios", "Insumos", "Placas", 150, 0, 4500, 55, 1, supplier_names[0]),
        ("INS-0004", "Tornillería Acero Inox (kg)", "Insumos", "Hardware", 50, 0, 3500, 70, 1, supplier_names[0]),
        ("SRV-0001", "Instalación Básica Domótica", "Servicios", "Instalación", 0, 0, 50000, 35, 1, supplier_names[0]),
    ]
    
    for sku, desc, cat, proto, stock_init, stock_cur, cost, margin, is_srv, prov in inventory_products:
        sale_price = round(cost * (1 + margin / 100))
        cursor.execute("""INSERT INTO inventory(sku, description, category, protocol, stock_initial, stock_current, cost_unit, margin_pct, sale_price, provider, is_service, stock_min) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (sku, desc, cat, proto, stock_init, stock_cur, cost, margin, sale_price, prov, is_srv, 15))
    
    conn.commit()
    sku_list = [row[0] for row in cursor.execute("SELECT sku FROM inventory").fetchall()]
    print(f"✓ {len(sku_list)} productos cargados")
    
    # COTIZACIONES
    print("🧾 Creando cotizaciones...")
    quote_number = 1
    for i in range(5):
        client_id = random.choice(client_ids)
        vendor_id = random.choice(vendor_ids)
        quote_date = (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d")
        cursor.execute("""INSERT INTO quotes(quote_number, quote_date, client_id, vendor_id, status, subtotal_products, vat_products, total) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""", 
                      (f"COT-2024-{quote_number:04d}", quote_date, client_id, vendor_id, random.choice(["Pendiente", "Aprobada", "Rechazada"]), 
                       random.randint(500000, 5000000), random.randint(50000, 500000), random.randint(550000, 5500000)))
        quote_number += 1
    
    conn.commit()
    quote_ids = [row[0] for row in cursor.execute("SELECT id FROM quotes").fetchall()]
    print(f"✓ {len(quote_ids)} cotizaciones creadas")
    
    # VENTAS
    print("💳 Registrando ventas...")
    for i in range(8):
        client_id = random.choice(client_ids)
        quote_id = random.choice(quote_ids) if quote_ids else None
        total = random.randint(500000, 3000000)
        material_cost = round(total * 0.4)
        gross_margin = total - material_cost
        margin_pct = (gross_margin / total * 100) if total > 0 else 0
        sale_date = (datetime.now() - timedelta(days=random.randint(0, 60))).strftime("%Y-%m-%d")
        cursor.execute("""INSERT INTO sales(sale_date, client_id, quote_id, total, material_cost, gross_margin, gross_margin_pct) VALUES(?, ?, ?, ?, ?, ?, ?)""", 
                      (sale_date, client_id, quote_id, total, material_cost, gross_margin, margin_pct))
    
    conn.commit()
    sale_ids = [row[0] for row in cursor.execute("SELECT id FROM sales").fetchall()]
    print(f"✓ {len(sale_ids)} ventas registradas")
    
    print("\n" + "="*60)
    print("✅ CARGA DE DATOS COMPLETADA EXITOSAMENTE")
    print("="*60)
    conn.close()

if __name__ == "__main__":
    seed_database()
