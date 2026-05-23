import streamlit as st
from database import get_df, get_conn, q, convert_quote_to_sale
from utils import money

def render():
    st.subheader("Ventas")
    quotes_df = get_df("""
        SELECT q.id, q.quote_number, c.name AS cliente, q.total, q.status
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id ORDER BY q.id DESC
    """)
    eligible = quotes_df[quotes_df["status"].isin(["Aceptada","Facturada","Pendiente","Enviada","Borrador","Aprobada"])]
    a, b = st.columns(2)
    if not eligible.empty:
        labels = eligible.apply(lambda x: f'{x["id"]} · {x["quote_number"]} · {x["cliente"]} · {money(x["total"])}', axis=1).tolist()
        selected = a.selectbox("Convertir cotización en venta", [""] + labels)
        if a.button("💳 Registrar venta") and selected:
            quote_id = int(selected.split(" · ")[0])
            ok, msg = convert_quote_to_sale(quote_id)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
    sales_df = get_df("""
        SELECT s.id, s.sale_date, c.name AS cliente, s.total, s.material_cost, s.gross_margin, s.gross_margin_pct
        FROM sales s LEFT JOIN clients c ON c.id=s.client_id ORDER BY s.id DESC
    """)
    if not sales_df.empty:
        del_sale = b.selectbox("Eliminar venta", [""] + [f'{row["id"]} · {row["cliente"]}' for _, row in sales_df.iterrows()])
        if b.button("🗑️ Eliminar venta") and del_sale:
            sale_id = int(del_sale.split(" · ")[0])
            conn = get_conn()
            q(conn, "DELETE FROM billing WHERE sale_id=?", (sale_id,))
            q(conn, "DELETE FROM sales WHERE id=?", (sale_id,))
            conn.close()
            st.success("Venta eliminada.")
            st.rerun()
    if sales_df.empty:
        st.info("No hay ventas registradas.")
        return
    # KPIs
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total ventas", money(int(sales_df["total"].sum())))
    m2.metric("Costo materiales", money(int(sales_df["material_cost"].sum())))
    m3.metric("Margen bruto", money(int(sales_df["gross_margin"].sum())))
    m4.metric("Margen promedio", f"{float(sales_df['gross_margin_pct'].mean())*100:.1f}%")
    st.dataframe(sales_df, use_container_width=True, hide_index=True,
                 column_config={
                     "id": st.column_config.NumberColumn("ID", format="%d"),
                     "sale_date": st.column_config.DateColumn("Fecha"),
                     "cliente": st.column_config.TextColumn("Cliente"),
                     "total": st.column_config.NumberColumn("Total CLP", format="$ %d"),
                     "material_cost": st.column_config.NumberColumn("Costo mat.", format="$ %d"),
                     "gross_margin": st.column_config.NumberColumn("Margen bruto", format="$ %d"),
                     "gross_margin_pct": st.column_config.NumberColumn("Margen %", format="%.1f%%"),
                 })
