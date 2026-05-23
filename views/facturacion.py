import streamlit as st
from database import get_df, get_conn, q
from utils import money, make_pdf

def render():
    st.subheader("Facturación")
    bill_df = get_df("""
        SELECT b.id, b.sale_id, c.name AS cliente, b.total, b.advance_50, b.balance_50, b.payment_status
        FROM billing b LEFT JOIN clients c ON c.id=b.client_id ORDER BY b.id DESC
    """)
    if bill_df.empty:
        st.info("No hay registros de facturación.")
        return
    a, b, c = st.columns(3)
    bill_sel = a.selectbox("Selecciona registro", [f'{row["id"]} · {row["cliente"]}' for _, row in bill_df.iterrows()])
    bill_id = int(bill_sel.split(" · ")[0]) if bill_sel else None
    current = bill_df[bill_df["id"] == bill_id].iloc[0].to_dict() if bill_id else {}
    states = ["Pendiente","Anticipo 50%","Pagado"]
    status = b.selectbox("Estado pago", states, index=(states.index(current.get("payment_status")) if current.get("payment_status") in states else 0))
    if c.button("Guardar estado") and bill_id:
        conn = get_conn()
        q(conn, "UPDATE billing SET payment_status=? WHERE id=?", (status, bill_id))
        conn.close()
        st.success("Estado actualizado.")
        st.rerun()
    if bill_id:
        sale_items = get_df("""
            SELECT qi.item_type, qi.description, qi.quantity, qi.unit_price, qi.line_total
            FROM sales s LEFT JOIN quotes qt ON qt.id=s.quote_id
            LEFT JOIN quote_items qi ON qi.quote_id=qt.id WHERE s.id=?
        """, (int(current.get("sale_id")),))
        service_total_pdf = int(sale_items.loc[sale_items["item_type"]=="servicio","line_total"].sum()) if not sale_items.empty else 0
        item_lines_pdf = [f"{r['description']} | Cant: {int(r['quantity'])} | Total: {money(r['line_total'])}" for _, r in sale_items[sale_items["item_type"].isin(["producto","kit","insumo"])].iterrows()] if not sale_items.empty else []
        if service_total_pdf:
            item_lines_pdf.append(f"Servicio integral | 1 | {money(service_total_pdf)}")
        bill_pdf = make_pdf(
            title=f"Facturación #{current.get('id')} — {current.get('cliente','')}",
            subtitle=f"Venta: {current.get('sale_id')}",
            sections=[
                ("Cobros", item_lines_pdf or ["Sin detalle"]),
                ("Resumen", [f"Total: {money(current.get('total',0))}", f"Anticipo 50%: {money(current.get('advance_50',0))}", f"Saldo 50%: {money(current.get('balance_50',0))}", f"Estado: {current.get('payment_status','')}"])
            ]
        )
        st.download_button("📄 PDF facturación", data=bill_pdf, file_name=f"facturacion_{bill_id}.pdf", mime="application/pdf")
        if st.button("🗑️ Eliminar registro") and bill_id:
            conn = get_conn()
            q(conn, "DELETE FROM billing WHERE id=?", (bill_id,))
            conn.close()
            st.success("Registro eliminado.")
            st.rerun()
    st.dataframe(bill_df, use_container_width=True, hide_index=True,
                 column_config={
                     "total": st.column_config.NumberColumn("Total", format="$ %d"),
                     "advance_50": st.column_config.NumberColumn("Anticipo 50%", format="$ %d"),
                     "balance_50": st.column_config.NumberColumn("Saldo 50%", format="$ %d"),
                 })
