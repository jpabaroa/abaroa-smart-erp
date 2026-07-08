import streamlit as st
from database import get_df, get_conn, q
from utils import money

def render():
    st.subheader("Catálogo de Insumos")
    df = get_df("SELECT * FROM supplies_catalog ORDER BY description")
    c1,c2 = st.columns([2,1])
    opts = ["Nuevo"] + (df["description"].tolist() if not df.empty else [])
    selected = c1.selectbox("Seleccionar insumo", opts)
    current = df[df["description"]==selected].iloc[0].to_dict() if selected!="Nuevo" and not df.empty else {}
    with st.form("insumo_form"):
        desc = st.text_input("Descripción *", value=str(current.get("description","")))
        price = st.number_input("Precio unitario default", min_value=0, value=int(current.get("default_unit_price",0) or 0), step=100)
        s1,s2,s3 = st.columns(3)
        save = s1.form_submit_button("Guardar", type="primary")
        edit = s2.form_submit_button("Editar")
        dele = s3.form_submit_button("Eliminar")
        if save or edit:
            if not desc.strip():
                st.error("Descripción obligatoria.")
            elif edit and selected == "Nuevo":
                st.error("Selecciona un insumo existente para editar, o usa 'Guardar' para crear uno nuevo.")
            else:
                conn = get_conn()
                if save:
                    q(conn, "INSERT OR IGNORE INTO supplies_catalog (description, default_unit_price) VALUES (?,?)", (desc.strip(), int(price)))
                    st.success("Insumo creado.")
                else:
                    q(conn, "UPDATE supplies_catalog SET description=?, default_unit_price=? WHERE id=?", (desc.strip(), int(price), int(current["id"])))
                    st.success("Insumo actualizado.")
                conn.close()
                st.rerun()
        if dele and selected!="Nuevo":
            conn = get_conn()
            q(conn, "DELETE FROM supplies_catalog WHERE id=?", (int(current["id"]),))
            conn.close()
            st.success("Insumo eliminado.")
            st.rerun()
    if not df.empty:
        df_show = df.copy()
        df_show["default_unit_price"] = df_show["default_unit_price"].apply(money)
        st.dataframe(df_show, use_container_width=True, hide_index=True)
    else:
        st.info("Sin insumos en el catálogo.")
