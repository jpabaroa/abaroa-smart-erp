from datetime import date

import pandas as pd
import streamlit as st

from database import (
    get_conn, get_df, q, save_quote, validate_quote_before_save,
    get_quote_stock_warnings, IVA_RATE,
)
from utils import money, logo, make_quote_pdf

ESTADOS = ["Borrador", "Enviada", "Aprobada", "Rechazada", "Vendida", "Facturada"]
ESTADO_COLORS = {
    "Borrador":  "pill-borrador",
    "Enviada":   "pill-enviada",
    "Aprobada":  "pill-aprobada",
    "Rechazada": "pill-rechazada",
    "Vendida":   "pill-vendida",
    "Facturada": "pill-vendida",
}


def _reset_supply_inputs():
    st.session_state["quote_supply_reset_pending"] = True


def _refresh_supply_unit():
    selected_desc = st.session_state.get("add_supply_desc_sel", "")
    if not selected_desc or selected_desc in ("", "Nuevo insumo..."):
        return
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT default_unit_price FROM supplies_catalog WHERE description=? LIMIT 1", (selected_desc,)
        ).fetchone()
        conn.close()
        st.session_state["add_supply_unit"] = int(row["default_unit_price"] or 0) if row else 0
    except Exception:
        st.session_state["add_supply_unit"] = 0


def render():
    st.subheader("Cotización")

    # Reset qty flags
    if st.session_state.get("reset_quote_qty"):
        for k in ["add_prod_qty", "add_kit_qty", "add_serv_qty", "add_supply_qty"]:
            st.session_state[k] = 1
        st.session_state["reset_quote_qty"] = False

    # Inicializar listas
    for key in ["quote_products", "quote_services", "quote_kits", "quote_supplies"]:
        if key not in st.session_state:
            st.session_state[key] = []

    # Cargar datos
    clients_df = get_df("SELECT * FROM clients ORDER BY name")
    vendors_df = get_df("SELECT * FROM vendors ORDER BY name")
    inv_df = get_df("SELECT * FROM inventory ORDER BY description")
    kits_df = get_df("SELECT * FROM kits ORDER BY name")
    supplies_db_df = get_df("SELECT * FROM supplies_catalog ORDER BY description")
    products_df = inv_df[inv_df["is_service"] == 0].copy()
    services_df = inv_df[inv_df["is_service"] == 1].copy()

    if clients_df.empty:
        st.warning("Primero crea al menos un cliente en el módulo **Clientes**.")
        return

    # ── Cabecera ──────────────────────────────────────────────────────────────
    col_logo, col_title = st.columns([1, 3])
    with col_logo:
        logo(160)
    with col_title:
        st.markdown("### Nueva cotización")
        st.caption("Productos y kits con IVA · Servicios exentos")

    a, b, c = st.columns(3)
    quote_number = a.text_input("N° Cotización", value=f"COT-{pd.Timestamp.now().strftime('%Y%m%d-%H%M')}")
    quote_date = b.date_input("Fecha", value=date.today())
    validity_days = c.number_input("Validez (días)", min_value=1, value=10, step=1)

    c1, c2 = st.columns(2)
    client_name = c1.selectbox("Cliente", clients_df["name"].tolist())
    vendor_name = c2.selectbox("Vendedor", vendors_df["name"].tolist() if not vendors_df.empty else ["Abaroa Smart"])
    client_row = clients_df.loc[clients_df["name"] == client_name].iloc[0].to_dict()
    vendor_row = vendors_df.loc[vendors_df["name"] == vendor_name].iloc[0].to_dict() if not vendors_df.empty else {"id": None}

    d1, d2, d3, d4 = st.columns(4)
    d1.text_input("Nombre", value=str(client_row.get("name", "")), disabled=True)
    d2.text_input("Teléfono", value=str(client_row.get("phone", "") or ""), disabled=True)
    d3.text_input("Correo", value=str(client_row.get("email", "") or ""), disabled=True)
    d4.text_input("Dirección", value=str(client_row.get("address", "") or ""), disabled=True)

    # ── Agregar producto ──────────────────────────────────────────────────────
    st.markdown("### Agregar producto")
    p1, p2, p3 = st.columns([5, 1.5, 1.5])
    prod_desc = p1.selectbox("Producto", [""] + products_df["description"].tolist(), key="add_prod_desc")
    prod_qty = p2.number_input("Cantidad", min_value=1, value=1, step=1, key="add_prod_qty")
    prow = None
    if prod_desc:
        prow = products_df.loc[products_df["description"] == prod_desc].iloc[0]
        p3.text_input("Precio", value=money(int(prow["sale_price"] or 0)), disabled=True, key="add_prod_price")
    else:
        p3.text_input("Precio", value="", disabled=True, key="add_prod_price")
    if st.button("➕ Agregar producto"):
        if prow is not None:
            unit_price = int(prow["sale_price"] or 0)
            st.session_state.quote_products.append({
                "sku": prow["sku"], "description": prod_desc,
                "quantity": int(prod_qty), "unit_price": unit_price,
                "line_total": int(prod_qty * unit_price)
            })

    if st.session_state.quote_products:
        stock_alerts = []
        for line in st.session_state.quote_products:
            prod = products_df.loc[products_df["sku"] == line["sku"]]
            if not prod.empty:
                available = int(prod.iloc[0]["stock_current"] or 0)
                if int(line["quantity"]) > available:
                    stock_alerts.append(f"⚠️ Stock insuf. para **{line['description']}**: disponible {available}, solicitado {int(line['quantity'])}.")
        for msg in stock_alerts:
            st.warning(msg)
        st.markdown("#### Productos agregados")
        pt = pd.DataFrame(st.session_state.quote_products)
        pt["unit_price_fmt"] = pt["unit_price"].apply(money)
        pt["line_total_fmt"] = pt["line_total"].apply(money)
        st.dataframe(pt[["sku","description","quantity","unit_price_fmt","line_total_fmt"]], use_container_width=True, hide_index=True)
        ep1, ep2, ep3, ep4 = st.columns(4)
        opts_prod = [""] + [f'{i+1} · {x["description"]}' for i, x in enumerate(st.session_state.quote_products)]
        edit_idx = ep1.selectbox("Editar producto", opts_prod, key="edit_prod")
        if edit_idx:
            idx = int(edit_idx.split(" · ")[0]) - 1
            new_qty = ep2.number_input("Nueva cantidad", min_value=1, value=int(st.session_state.quote_products[idx]["quantity"]), step=1, key="edit_prod_qty")
            if ep3.button("Guardar"):
                st.session_state.quote_products[idx]["quantity"] = int(new_qty)
                st.session_state.quote_products[idx]["line_total"] = int(new_qty) * int(st.session_state.quote_products[idx]["unit_price"])
                st.success("Producto actualizado.")
        del_idx = ep4.selectbox("Eliminar producto", opts_prod, key="del_prod")
        if st.button("Quitar producto") and del_idx:
            st.session_state.quote_products.pop(int(del_idx.split(" · ")[0]) - 1)

    # ── Agregar kit ───────────────────────────────────────────────────────────
    st.markdown("### Agregar kit")
    k1, k2, k3 = st.columns([5, 1.5, 1.5])
    kit_name = k1.selectbox("Kit", [""] + kits_df["name"].tolist(), key="add_kit_name")
    kit_qty = k2.number_input("Cantidad", min_value=1, value=1, step=1, key="add_kit_qty")
    krow = None
    if kit_name:
        krow = kits_df.loc[kits_df["name"] == kit_name].iloc[0]
        k3.text_input("Precio kit", value=money(int(krow["sale_price"] or 0)), disabled=True, key="add_kit_price")
    else:
        k3.text_input("Precio kit", value="", disabled=True, key="add_kit_price")
    if st.button("➕ Agregar kit"):
        if krow is not None:
            unit_price = int(krow["sale_price"] or 0)
            st.session_state.quote_kits.append({
                "code": krow["code"], "name": kit_name,
                "quantity": int(kit_qty), "unit_price": unit_price,
                "line_total": int(kit_qty * unit_price)
            })
    if st.session_state.quote_kits:
        st.markdown("#### Kits agregados")
        kt = pd.DataFrame(st.session_state.quote_kits)
        kt["unit_price"] = kt["unit_price"].apply(money)
        kt["line_total"] = kt["line_total"].apply(money)
        st.dataframe(kt, use_container_width=True, hide_index=True)
        del_kit = st.selectbox("Quitar kit", [""] + [f'{i+1} · {x["name"]}' for i, x in enumerate(st.session_state.quote_kits)], key="del_kit")
        if st.button("Eliminar kit") and del_kit:
            st.session_state.quote_kits.pop(int(del_kit.split(" · ")[0]) - 1)

    # ── Agregar servicio ──────────────────────────────────────────────────────
    st.markdown("### Agregar servicio")
    s1, s2, s3 = st.columns([5, 1.5, 1.5])
    services_df = (services_df.sort_values(["description","sku"]).drop_duplicates(subset=["sku"])
                   if not services_df.empty else services_df)
    service_opts = [""] + [f'{r["sku"]} · {r["description"]}' for _, r in services_df.iterrows()]
    serv_choice = s1.selectbox("Servicio", service_opts, key="add_serv_desc")
    serv_qty = s2.number_input("Cantidad", min_value=1, value=1, step=1, key="add_serv_qty")
    srow = None
    if serv_choice:
        serv_sku = serv_choice.split(" · ")[0]
        srow = services_df.loc[services_df["sku"] == serv_sku].iloc[0]
        s3.text_input("Precio", value=money(int(srow["sale_price"] or 0)), disabled=True, key="add_serv_price")
    else:
        s3.text_input("Precio", value="", disabled=True, key="add_serv_price")
    if st.button("➕ Agregar servicio"):
        if srow is not None:
            unit_price = int(srow["sale_price"] or 0)
            st.session_state.quote_services.append({
                "sku": srow["sku"], "description": str(srow["description"]),
                "quantity": int(serv_qty), "unit_price": unit_price,
                "line_total": int(serv_qty * unit_price)
            })
    if st.session_state.quote_services:
        st.markdown("#### Servicios (exentos IVA)")
        dt = pd.DataFrame(st.session_state.quote_services)
        dt["unit_price_fmt"] = dt["unit_price"].apply(money)
        dt["line_total_fmt"] = dt["line_total"].apply(money)
        st.dataframe(dt[["sku","description","quantity","unit_price_fmt","line_total_fmt"]], use_container_width=True, hide_index=True)
        del_serv = st.selectbox("Quitar servicio", [""] + [f'{i+1} · {x["description"]}' for i, x in enumerate(st.session_state.quote_services)], key="del_serv")
        if st.button("Eliminar servicio") and del_serv:
            st.session_state.quote_services.pop(int(del_serv.split(" · ")[0]) - 1)

    # ── Agregar insumo ────────────────────────────────────────────────────────
    st.markdown("### Agregar insumo")
    supply_names = supplies_db_df["description"].tolist() if not supplies_db_df.empty else []
    if st.session_state.pop("quote_supply_reset_pending", False):
        for k in ["add_supply_desc_sel","add_supply_desc_new"]:
            st.session_state[k] = ""
        st.session_state["add_supply_qty"] = 1
        st.session_state["add_supply_unit"] = 0
    for k, v in [("add_supply_unit",0),("add_supply_desc_new",""),("add_supply_qty",1),("add_supply_desc_sel","")]:
        if k not in st.session_state:
            st.session_state[k] = v

    i1, i2, i3, i4 = st.columns([4, 2, 2, 1.5])
    supply_desc = i1.selectbox("Insumo", [""] + supply_names + ["Nuevo insumo..."],
                                key="add_supply_desc_sel", on_change=_refresh_supply_unit)
    custom_supply_desc = ""
    if supply_desc == "Nuevo insumo...":
        custom_supply_desc = st.text_input("Descripción nuevo insumo", key="add_supply_desc_new")
    supply_qty = i2.number_input("Cantidad", min_value=1, value=int(st.session_state.get("add_supply_qty",1)), step=1, key="add_supply_qty")
    supply_unit = i3.number_input("Precio unitario", min_value=0, step=100, key="add_supply_unit")
    i4.write("")
    i4.write("")
    if i4.button("➕ Insumo"):
        final_desc = custom_supply_desc.strip() if supply_desc == "Nuevo insumo..." else str(supply_desc or "").strip()
        if final_desc:
            st.session_state.quote_supplies.append({
                "sku": "INSUMO", "description": final_desc,
                "quantity": int(supply_qty), "unit_price": int(supply_unit),
                "line_total": int(supply_qty) * int(supply_unit)
            })
            conn = get_conn()
            q(conn, "INSERT OR IGNORE INTO supplies_catalog (description, default_unit_price) VALUES (?,?)", (final_desc, int(supply_unit)))
            q(conn, "UPDATE supplies_catalog SET default_unit_price=? WHERE description=?", (int(supply_unit), final_desc))
            conn.close()
            _reset_supply_inputs()
            st.rerun()

    if st.session_state.quote_supplies:
        st.markdown("#### Insumos agregados")
        st_table = pd.DataFrame(st.session_state.quote_supplies)
        st_table["unit_price_fmt"] = st_table["unit_price"].apply(money)
        st_table["line_total_fmt"] = st_table["line_total"].apply(money)
        st.dataframe(st_table[["sku","description","quantity","unit_price_fmt","line_total_fmt"]], use_container_width=True, hide_index=True)
        del_sup = st.selectbox("Quitar insumo", [""] + [f'{i+1} · {x["description"]}' for i, x in enumerate(st.session_state.quote_supplies)], key="del_supply")
        if st.button("Eliminar insumo") and del_sup:
            st.session_state.quote_supplies.pop(int(del_sup.split(" · ")[0]) - 1)

    # ── Totales ───────────────────────────────────────────────────────────────
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

    # Costo estimado
    product_cost_total = 0
    for x in product_lines:
        prod = products_df.loc[products_df["sku"] == x["sku"]]
        if not prod.empty:
            product_cost_total += int(x["quantity"]) * int(prod.iloc[0]["cost_unit"] or 0)
    kit_cost_total = 0
    for k in kit_lines:
        costdf = get_df("SELECT COALESCE(SUM(i.cost_unit * ki.quantity),0) AS cost FROM kit_items ki JOIN kits k2 ON k2.id=ki.kit_id LEFT JOIN inventory i ON i.sku=ki.sku WHERE k2.code=?", (k.get("code"),))
        if not costdf.empty:
            kit_cost_total += int(costdf.iloc[0]["cost"] or 0) * int(k.get("quantity",1))
    supplies_cost_total = int(sum(int(x["line_total"]) for x in supply_lines))
    estimated_cost = product_cost_total + kit_cost_total + supplies_cost_total
    estimated_margin = int(total - estimated_cost)
    estimated_margin_pct = (estimated_margin / total * 100) if total else 0

    st.markdown("---")
    r1, r2, r3, r4, r5, r6, r7 = st.columns(7)
    r1.metric("Afecto IVA", money(subtotal_products + subtotal_kits + subtotal_supplies))
    r2.metric("Exento (servicios)", money(subtotal_services))
    r3.metric("Subtotal servicios", money(subtotal_services))
    r4.metric("Subtotal insumos", money(subtotal_supplies))
    r5.metric("IVA 19%", money(vat_products))
    r6.metric("TOTAL", money(total))
    r7.metric("Margen est.", f"{estimated_margin_pct:.1f}%")

    # ── Estado + notas ────────────────────────────────────────────────────────
    notes = st.text_area("Términos / notas", value="• Productos, kits e insumos afectos a IVA.\n• Servicios exentos de IVA.")
    internal_notes = st.text_area("Notas internas (no aparecen en PDF)", value="")
    status = st.selectbox("Estado de la cotización", ESTADOS)

    # ── Acciones ──────────────────────────────────────────────────────────────
    g1, g2, g3, g4 = st.columns(4)

    # PDF preview
    current_quote_pdf = make_quote_pdf(
        quote_number=quote_number, quote_date=quote_date, client_row=client_row,
        vendor_name=vendor_name, product_lines=product_lines, kit_lines=kit_lines,
        service_lines=service_lines, supply_lines=supply_lines, notes=notes,
        subtotal_products=subtotal_products, subtotal_kits=subtotal_kits,
        subtotal_services=subtotal_services, subtotal_supplies=subtotal_supplies,
        vat_products=vat_products, total=total,
    )
    g1.download_button("📄 Descargar PDF", data=current_quote_pdf,
                       file_name=f"{quote_number}.pdf", mime="application/pdf",
                       use_container_width=True)

    if g2.button("💾 Guardar cotización", use_container_width=True):
        errors = validate_quote_before_save(client_row, product_lines, service_lines, kit_lines, supply_lines, products_df)
        warnings = get_quote_stock_warnings(product_lines, products_df)
        if errors:
            for err in errors:
                st.error(err)
        else:
            for warn in warnings:
                st.warning(warn)
            final_notes = notes
            if internal_notes.strip():
                final_notes += f"\n\n[NOTA INTERNA ERP]\n{internal_notes.strip()}"
            quote_id, total_saved = save_quote(
                quote_number, quote_date.isoformat(),
                int(client_row["id"]), int(vendor_row["id"]) if vendor_row.get("id") else None,
                int(validity_days), status, final_notes,
                product_lines, service_lines, kit_lines, supply_lines
            )
            st.session_state["reset_quote_qty"] = True
            st.success(f"Cotización guardada — ID {quote_id} · Total {money(total_saved)}")
            st.rerun()

    if g3.button("🗑️ Limpiar", use_container_width=True):
        st.session_state.quote_products = []
        st.session_state.quote_services = []
        st.session_state.quote_kits = []
        st.session_state.quote_supplies = []
        st.session_state["reset_quote_qty"] = True
        st.rerun()

    # Eliminar cotización guardada
    quote_df = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, c.name AS cliente, v.name AS vendedor, q.status, q.total
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id LEFT JOIN vendors v ON v.id=q.vendor_id
        ORDER BY q.id DESC
    """)
    if not quote_df.empty:
        q_opts = [""] + [f'{row["id"]} · {row["quote_number"]} · {row["cliente"]}' for _, row in quote_df.iterrows()]
        q_delete = g4.selectbox("Eliminar cotización guardada", q_opts, key="del_saved_quote")
        if g4.button("🗑️ Eliminar", use_container_width=True, key="btn_del_saved_quote") and q_delete:
            from database import delete_quote
            delete_quote(int(q_delete.split(" · ")[0]))
            st.success("Cotización eliminada.")
            st.rerun()
