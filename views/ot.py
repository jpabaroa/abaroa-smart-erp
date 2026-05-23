from datetime import date
import streamlit as st
from database import get_df, get_conn, q, add_wo_item
from utils import money, make_pdf


def render():
    st.subheader("Órdenes de Trabajo (OT)")

    clients_df = get_df("SELECT * FROM clients ORDER BY name")
    vendors_df = get_df("SELECT * FROM vendors ORDER BY name")
    quotes_df = get_df("SELECT id, quote_number FROM quotes ORDER BY id DESC")
    ot_df = get_df("""
        SELECT wo.id, wo.ot_number, c.name AS cliente, v.name AS tecnico, wo.status,
               wo.scheduled_date, wo.address, wo.hours_work,
               wo.labor_cost, wo.travel_cost, wo.extra_material_cost, wo.quote_id
        FROM work_orders wo
        LEFT JOIN clients c ON c.id=wo.client_id
        LEFT JOIN vendors v ON v.id=wo.vendor_id
        ORDER BY wo.id DESC
    """)

    # Métricas
    if not ot_df.empty:
        abiertas = int((ot_df["status"].isin(["Pendiente","Agendada","En ejecución","Abierta","En proceso"])).sum())
        m1, m2 = st.columns(2)
        m1.metric("OT activas", abiertas)
        m2.metric("Total OT", len(ot_df))

    # Formulario CRUD
    with st.expander("Crear / editar OT", expanded=True):
        ot_opts = ["Nueva"] + (ot_df["ot_number"].tolist() if not ot_df.empty else [])
        ot_sel = st.selectbox("Seleccionar OT", [f'{int(r["id"])} · {r["ot_number"]}' for _, r in ot_df.iterrows()] if not ot_df.empty else ["Nueva"],
                              key="ot_form_sel")
        if ot_sel == "Nueva" or ot_df.empty:
            current = {}
            ot_id_current = None
        else:
            ot_id_current = int(ot_sel.split(" · ")[0])
            current = ot_df[ot_df["id"] == ot_id_current].iloc[0].to_dict()

        with st.form("ot_form"):
            f1, f2, f3 = st.columns(3)
            ot_number = f1.text_input("N° OT", value=str(current.get("ot_number","")) or f"OT-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M')}")
            ot_statuses = ["Pendiente","Agendada","En ejecución","Cerrada","Cancelada"]
            status = f2.selectbox("Estado", ot_statuses, index=(ot_statuses.index(str(current.get("status","Pendiente"))) if str(current.get("status","Pendiente")) in ot_statuses else 0))
            scheduled_date = f3.date_input("Fecha programada", value=date.today())
            g1, g2 = st.columns(2)
            client_name = g1.selectbox("Cliente", clients_df["name"].tolist() if not clients_df.empty else ["Sin clientes"])
            vendor_name = g2.selectbox("Técnico", vendors_df["name"].tolist() if not vendors_df.empty else ["Sin técnicos"])
            address = st.text_input("Dirección", value=str(current.get("address","") or ""))
            h1, h2, h3 = st.columns(3)
            hours_work = h1.number_input("Horas hombre", min_value=0.0, value=float(current.get("hours_work",0) or 0), step=0.5)
            labor_cost = h2.number_input("Costo mano de obra", min_value=0, value=int(current.get("labor_cost",0) or 0), step=500)
            travel_cost = h3.number_input("Viáticos", min_value=0, value=int(current.get("travel_cost",0) or 0), step=500)
            extra_mat = st.number_input("Materiales adicionales", min_value=0, value=int(current.get("extra_material_cost",0) or 0), step=500)
            notes = st.text_area("Notas", value=str(current.get("notes","") or ""), height=60)
            quote_opts = [""] + [f'{int(r["id"])} · {r["quote_number"]}' for _, r in quotes_df.iterrows()]
            quote_opt = st.selectbox("Cotización asociada (opcional)", quote_opts)

            s1, s2, s3 = st.columns(3)
            save_btn = s1.form_submit_button("💾 Guardar OT", type="primary")
            delete_btn = s2.form_submit_button("🗑️ Eliminar OT")
            _ = s3.form_submit_button("Limpiar")

            if save_btn:
                conn = get_conn()
                client_id = int(clients_df.loc[clients_df["name"]==client_name].iloc[0]["id"]) if not clients_df.empty else None
                vendor_id = int(vendors_df.loc[vendors_df["name"]==vendor_name].iloc[0]["id"]) if not vendors_df.empty else None
                quote_id = int(quote_opt.split(" · ")[0]) if quote_opt else None
                if ot_id_current is None:
                    q(conn, """INSERT INTO work_orders (ot_number,client_id,vendor_id,quote_id,status,scheduled_date,
                            address,hours_work,labor_cost,travel_cost,extra_material_cost,notes)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (ot_number, client_id, vendor_id, quote_id, status, scheduled_date.isoformat(),
                       address, float(hours_work), int(labor_cost), int(travel_cost), int(extra_mat), notes))
                else:
                    q(conn, """UPDATE work_orders SET ot_number=?,client_id=?,vendor_id=?,quote_id=?,status=?,
                            scheduled_date=?,address=?,hours_work=?,labor_cost=?,travel_cost=?,extra_material_cost=?,notes=?
                            WHERE id=?""",
                      (ot_number, client_id, vendor_id, quote_id, status, scheduled_date.isoformat(),
                       address, float(hours_work), int(labor_cost), int(travel_cost), int(extra_mat), notes, ot_id_current))
                conn.close()
                st.success("OT guardada.")
                st.rerun()
            if delete_btn and ot_id_current:
                conn = get_conn()
                q(conn, "DELETE FROM work_order_items WHERE work_order_id=?", (ot_id_current,))
                q(conn, "DELETE FROM work_orders WHERE id=?", (ot_id_current,))
                conn.close()
                st.success("OT eliminada.")
                st.rerun()

    # Materiales usados por OT
    if not ot_df.empty:
        st.markdown("### Materiales usados en OT")
        ot_choose = st.selectbox("OT para agregar materiales", [f'{int(r["id"])} · {r["ot_number"]}' for _, r in ot_df.iterrows()])
        ot_id = int(ot_choose.split(" · ")[0])
        inv_products = get_df("SELECT sku, description, cost_unit FROM inventory WHERE is_service=0 ORDER BY description")
        item_opts_list = [""] + [f'{r["sku"]} · {r["description"]}' for _, r in inv_products.iterrows()]
        with st.form("wo_item_form"):
            p1, p2 = st.columns(2)
            item = p1.selectbox("Producto usado", item_opts_list)
            qty = p2.number_input("Cantidad usada", min_value=1, value=1, step=1)
            if st.form_submit_button("➕ Agregar material") and item:
                sku, desc = item.split(" · ", 1)
                prod_row = inv_products.loc[inv_products["sku"]==sku].iloc[0]
                add_wo_item(ot_id, sku, desc, int(qty), int(prod_row["cost_unit"] or 0))
                st.success("Material agregado.")
                st.rerun()

        wo_items_df = get_df("SELECT sku, description, quantity, cost_unit, line_cost FROM work_order_items WHERE work_order_id=? ORDER BY id DESC", (ot_id,))
        if not wo_items_df.empty:
            wo_items_df["line_cost"] = wo_items_df["line_cost"].apply(money)
            st.dataframe(wo_items_df, use_container_width=True, hide_index=True)

        # Rentabilidad OT
        base_ot = ot_df.loc[ot_df["id"]==ot_id].iloc[0]
        materials_cost = int(get_df("SELECT COALESCE(SUM(line_cost),0) AS c FROM work_order_items WHERE work_order_id=?", (ot_id,)).iloc[0]["c"])
        total_ot_cost = int(base_ot["labor_cost"] or 0) + int(base_ot["travel_cost"] or 0) + int(base_ot["extra_material_cost"] or 0) + materials_cost
        quote_total = 0
        import pandas as pd
        if pd.notna(base_ot["quote_id"]):
            qrow = get_df("SELECT total FROM quotes WHERE id=?", (int(base_ot["quote_id"]),))
            if not qrow.empty:
                quote_total = int(qrow.iloc[0]["total"] or 0)
        real_margin = quote_total - total_ot_cost
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Costo materiales OT", money(materials_cost))
        r2.metric("Costo operativo total", money(total_ot_cost))
        r3.metric("Venta asociada", money(quote_total))
        r4.metric("Margen real OT", money(real_margin))

        # PDF OT
        wo_items_raw = get_df("SELECT sku, description, quantity, cost_unit, line_cost FROM work_order_items WHERE work_order_id=?", (ot_id,))
        ot_pdf = make_pdf(
            title=f"OT {base_ot['ot_number']}",
            subtitle=f"Cliente: {base_ot['cliente']} | Técnico: {base_ot['tecnico']} | Fecha: {base_ot['scheduled_date']}",
            sections=[
                ("Datos OT", [f"Estado: {base_ot['status']}", f"Dirección: {base_ot['address'] or ''}", f"Horas: {base_ot['hours_work']}", f"Mano de obra: {money(base_ot['labor_cost'] or 0)}", f"Viáticos: {money(base_ot['travel_cost'] or 0)}"]),
                ("Materiales", [f"{r['description']} | {int(r['quantity'])} | {money(r['line_cost'])}" for _, r in wo_items_raw.iterrows()] or ["Sin materiales"]),
                ("Rentabilidad", [f"Costo total: {money(total_ot_cost)}", f"Venta asociada: {money(quote_total)}", f"Margen: {money(real_margin)}"])
            ]
        )
        st.download_button("📄 PDF OT", data=ot_pdf, file_name=f"{base_ot['ot_number']}.pdf", mime="application/pdf")

    # Listado completo
    st.markdown("### Listado de OT")
    st.dataframe(ot_df, use_container_width=True, hide_index=True, column_config={
        "id": st.column_config.NumberColumn("ID", format="%d"),
        "ot_number": st.column_config.TextColumn("N° OT"),
        "cliente": st.column_config.TextColumn("Cliente"),
        "tecnico": st.column_config.TextColumn("Técnico"),
        "status": st.column_config.TextColumn("Estado"),
        "scheduled_date": st.column_config.DateColumn("Fecha"),
        "hours_work": st.column_config.NumberColumn("Horas", format="%.1f hrs"),
        "labor_cost": st.column_config.NumberColumn("Mano obra", format="$ %d"),
        "travel_cost": st.column_config.NumberColumn("Viáticos", format="$ %d"),
    }) if not ot_df.empty else st.info("No hay OT registradas.")
