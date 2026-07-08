import streamlit as st
from database import get_df, get_conn, q, kit_components_df
from utils import money

def render():
    st.subheader("Kits")
    kits_df = get_df("SELECT * FROM kits ORDER BY name")
    inv_df = get_df("SELECT sku, description, sale_price, stock_current FROM inventory ORDER BY description")

    with st.expander("Crear / editar kit", expanded=True):
        opts = ["Nuevo"] + (kits_df["name"].tolist() if not kits_df.empty else [])
        selected = st.selectbox("Kit", opts)
        current = kits_df[kits_df["name"]==selected].iloc[0].to_dict() if selected!="Nuevo" and not kits_df.empty else {}
        with st.form("kit_form"):
            c1,c2,c3 = st.columns(3)
            code = c1.text_input("Código *", value=str(current.get("code","")))
            name = c2.text_input("Nombre *", value=str(current.get("name","")))
            sale_price = c3.number_input("Precio venta", min_value=0, value=int(current.get("sale_price",0) or 0), step=1000)
            notes = st.text_area("Notas", value=str(current.get("notes","") or ""), height=80)
            s1,s2,s3 = st.columns(3)
            save = s1.form_submit_button("Guardar", type="primary")
            edit = s2.form_submit_button("Editar")
            dele = s3.form_submit_button("Eliminar")
            if save or edit:
                if not code.strip() or not name.strip():
                    st.error("Código y nombre obligatorios.")
                elif edit and selected == "Nuevo":
                    st.error("Selecciona un kit existente para editar, o usa 'Guardar' para crear uno nuevo.")
                else:
                    conn = get_conn()
                    if save:
                        q(conn, "INSERT INTO kits (code,name,sale_price,notes) VALUES (?,?,?,?)", (code.strip(),name.strip(),int(sale_price),notes.strip()))
                        st.success("Kit creado.")
                    else:
                        q(conn, "UPDATE kits SET code=?,name=?,sale_price=?,notes=? WHERE id=?", (code.strip(),name.strip(),int(sale_price),notes.strip(),int(current["id"])))
                        st.success("Kit actualizado.")
                    conn.close()
                    st.rerun()
            if dele and selected!="Nuevo":
                conn = get_conn()
                q(conn, "DELETE FROM kit_items WHERE kit_id=?", (int(current["id"]),))
                q(conn, "DELETE FROM kits WHERE id=?", (int(current["id"]),))
                conn.close()
                st.success("Kit eliminado.")
                st.rerun()

    # Componentes
    if not kits_df.empty:
        st.markdown("### Componentes del kit")
        kit_sel = st.selectbox("Kit para editar componentes", kits_df["name"].tolist(), key="kit_comp_sel")
        kit_row = kits_df[kits_df["name"]==kit_sel].iloc[0]
        kit_id = int(kit_row["id"])
        if not inv_df.empty:
            c1,c2,c3 = st.columns([4,1,1])
            comp_opt = c1.selectbox("Producto", [f'{r["sku"]} · {r["description"]}' for _,r in inv_df.iterrows()], key="kit_comp_prod")
            qty = c2.number_input("Cantidad", min_value=1, value=1, step=1, key="kit_comp_qty")
            c3.write("")
            c3.write("")
            if c3.button("➕ Agregar"):
                sku = comp_opt.split(" · ")[0]
                conn = get_conn()
                q(conn, "INSERT INTO kit_items (kit_id, sku, quantity) VALUES (?,?,?)", (kit_id, sku, int(qty)))
                conn.close()
                st.success("Componente agregado.")
                st.rerun()
        comps = kit_components_df(kit_id)
        st.dataframe(comps, use_container_width=True, hide_index=True)
        if not comps.empty:
            del_comp = st.selectbox("Eliminar componente", [""] + [f'{r["sku"]} · {r["description"]}' for _,r in comps.iterrows()])
            if st.button("Eliminar componente") and del_comp:
                sku = del_comp.split(" · ")[0]
                conn = get_conn()
                q(conn, "DELETE FROM kit_items WHERE kit_id=? AND sku=? LIMIT 1", (kit_id, sku))
                conn.close()
                st.success("Componente eliminado.")
                st.rerun()

    st.markdown("### Todos los kits")
    if not kits_df.empty:
        kits_show = kits_df.copy()
        kits_show["sale_price"] = kits_show["sale_price"].apply(money)
        st.dataframe(kits_show, use_container_width=True, hide_index=True)
