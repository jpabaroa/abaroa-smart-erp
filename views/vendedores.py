import streamlit as st
from database import get_df, get_conn, q

def render():
    st.subheader("Vendedores")
    df = get_df("SELECT * FROM vendors ORDER BY name")
    opts = ["Nuevo"] + (df["name"].tolist() if not df.empty else [])
    selected = st.selectbox("Seleccionar", opts)
    current = df[df["name"]==selected].iloc[0].to_dict() if selected!="Nuevo" and not df.empty else {}
    with st.form("vendor_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Nombre *", value=str(current.get("name","")))
        role = c2.text_input("Rol", value=str(current.get("role","") or ""))
        c3, c4 = st.columns(2)
        email = c3.text_input("Correo", value=str(current.get("email","") or ""))
        phone = c4.text_input("Teléfono", value=str(current.get("phone","") or ""))
        s1, s2, s3 = st.columns(3)
        save = s1.form_submit_button("Guardar", type="primary")
        edit = s2.form_submit_button("Editar")
        dele = s3.form_submit_button("Eliminar")
        if save or edit:
            if not name.strip():
                st.error("Nombre obligatorio.")
            else:
                conn = get_conn()
                if save:
                    q(conn, "INSERT INTO vendors (name, email, phone, role) VALUES (?,?,?,?)", (name.strip(), email.strip(), phone.strip(), role.strip()))
                    st.success("Vendedor creado.")
                else:
                    q(conn, "UPDATE vendors SET name=?, email=?, phone=?, role=? WHERE id=?", (name.strip(), email.strip(), phone.strip(), role.strip(), int(current["id"])))
                    st.success("Vendedor actualizado.")
                conn.close()
                st.rerun()
        if dele and selected!="Nuevo":
            conn = get_conn()
            q(conn, "DELETE FROM vendors WHERE id=?", (int(current["id"]),))
            conn.close()
            st.success("Vendedor eliminado.")
            st.rerun()
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("Sin vendedores.")
