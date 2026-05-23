from datetime import date
import streamlit as st
from database import get_df, get_conn, q, load_quote_context, duplicate_quote, delete_quote, convert_quote_to_sale, create_project_from_quote, save_quote, IVA_RATE
from utils import money, make_quote_pdf

ESTADOS = ["Borrador","Enviada","Aprobada","Rechazada","Vendida","Facturada"]

def render():
    st.subheader("Historial de Cotizaciones")
    quotes_df = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, c.name AS cliente, v.name AS vendedor,
               q.status, q.total, q.validity_days
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id LEFT JOIN vendors v ON v.id=q.vendor_id
        ORDER BY q.id DESC
    """)
    if quotes_df.empty:
        st.info("No hay cotizaciones guardadas.")
        return

    # Filtros
    f1, f2, f3 = st.columns(3)
    filter_status = f1.selectbox("Filtrar por estado", ["Todos"] + ESTADOS)
    filter_client = f2.text_input("Buscar cliente", placeholder="Nombre del cliente...")
    filter_number = f3.text_input("Buscar N° cotización", placeholder="COT-...")

    df = quotes_df.copy()
    if filter_status != "Todos":
        df = df[df["status"] == filter_status]
    if filter_client.strip():
        df = df[df["cliente"].str.contains(filter_client.strip(), case=False, na=False)]
    if filter_number.strip():
        df = df[df["quote_number"].str.contains(filter_number.strip(), case=False, na=False)]

    total_filtrado = int(df["total"].sum() if not df.empty else 0)
    m1, m2, m3 = st.columns(3)
    m1.metric("Cotizaciones", len(df))
    m2.metric("Total acumulado", money(total_filtrado))
    m3.metric("Aprobadas", int((df["status"].isin(["Aprobada","Vendida","Facturada"])).sum()) if not df.empty else 0)

    df_show = df.copy()
    df_show["total"] = df_show["total"].apply(money)
    st.dataframe(df_show, use_container_width=True, hide_index=True,
                 column_config={
                     "id": st.column_config.NumberColumn("ID", format="%d"),
                     "quote_number": st.column_config.TextColumn("N° Cotización"),
                     "quote_date": st.column_config.DateColumn("Fecha"),
                     "cliente": st.column_config.TextColumn("Cliente"),
                     "vendedor": st.column_config.TextColumn("Vendedor"),
                     "status": st.column_config.TextColumn("Estado"),
                     "total": st.column_config.TextColumn("Total"),
                     "validity_days": st.column_config.NumberColumn("Validez", format="%d días"),
                 })

    if df.empty:
        return

    st.markdown("### Acciones sobre cotización")
    sel_opts = [f'{row["id"]} · {row["quote_number"]} · {row["cliente"]} · {row["status"]}' for _, row in df.iterrows()]
    sel = st.selectbox("Seleccionar cotización", sel_opts, key="hist_sel")
    quote_id = int(sel.split(" · ")[0])

    ctx = load_quote_context(quote_id)
    if not ctx:
        return

    h = ctx["header"]
    st.info(f"**{h['quote_number']}** · {h.get('client_name','')} · **{h['status']}** · {money(h['total'])}")

    # Cambiar estado
    st.markdown("#### Cambiar estado")
    sc1, sc2 = st.columns(2)
    new_status = sc1.selectbox("Nuevo estado", ESTADOS, index=(ESTADOS.index(h["status"]) if h["status"] in ESTADOS else 0))
    if sc2.button("Actualizar estado", use_container_width=True):
        conn = get_conn()
        extra = {}
        if new_status == "Enviada" and not h.get("sent_date"):
            extra["sent_date"] = date.today().isoformat()
        if new_status == "Aprobada" and not h.get("approved_date"):
            extra["approved_date"] = date.today().isoformat()
        set_clauses = "status=?"
        params = [new_status]
        for k, v in extra.items():
            set_clauses += f", {k}=?"
            params.append(v)
        params.append(quote_id)
        q(conn, f"UPDATE quotes SET {set_clauses} WHERE id=?", params)
        conn.close()
        st.success(f"Estado actualizado a **{new_status}**.")
        st.rerun()

    # PDF
    client_row = ctx["client_row"]
    vendor_name = ctx.get("vendor_name","")
    pdf_bytes = make_quote_pdf(
        quote_number=h["quote_number"], quote_date=h["quote_date"],
        client_row=client_row, vendor_name=vendor_name,
        product_lines=ctx["product_lines"], kit_lines=ctx["kit_lines"],
        service_lines=ctx["service_lines"], supply_lines=ctx["supply_lines"],
        notes=h.get("notes",""),
        subtotal_products=int(h.get("subtotal_products",0)),
        subtotal_kits=0, subtotal_services=int(h.get("subtotal_services_exempt",0)),
        subtotal_supplies=0, vat_products=int(h.get("vat_products",0)),
        total=int(h.get("total",0)),
    )

    a1, a2, a3, a4 = st.columns(4)
    a1.download_button("📄 Descargar PDF", data=pdf_bytes,
                       file_name=f"{h['quote_number']}.pdf", mime="application/pdf",
                       use_container_width=True)
    if a2.button("📋 Duplicar", use_container_width=True):
        ok, msg = duplicate_quote(quote_id)
        (st.success if ok else st.error)(msg)
        if ok:
            st.rerun()
    if a3.button("💳 Convertir en venta", use_container_width=True):
        ok, msg = convert_quote_to_sale(quote_id)
        (st.success if ok else st.error)(msg)
        if ok:
            st.rerun()
    if a4.button("🛠️ Crear proyecto", use_container_width=True):
        ok, pid, msg = create_project_from_quote(quote_id)
        (st.success if ok else st.warning)(msg)
        if ok:
            st.session_state["current_tab"] = "Proyectos"
            st.rerun()

    with st.expander("Ver ítems de esta cotización"):
        items_df = get_df("SELECT item_type, sku, description, quantity, unit_price, line_total FROM quote_items WHERE quote_id=? ORDER BY id", (quote_id,))
        if not items_df.empty:
            items_df["unit_price"] = items_df["unit_price"].apply(money)
            items_df["line_total"] = items_df["line_total"].apply(money)
            st.dataframe(items_df, use_container_width=True, hide_index=True)
