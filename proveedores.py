import streamlit as st
from database import get_df, get_conn, q

def render():
    st.subheader("Proveedores")
    df = get_df("SELECT * FROM suppliers ORDER BY name")
    opts = ["Nuevo"] + (df["name"].tolist() if not df.empty else [])
    selected = st.selectbox("Seleccionar proveedor", opts)
    current = df[df["name"]==selected].iloc[0].to_dict() if selected!="Nuevo" and not df.empty else {}
    with st.form("supplier_form"):
        c1,c2 = st.columns(2)
        name = c1.text_input("Nombre *", value=str(current.get("name","")))
        contact = c2.text_input("Persona de contacto", value=str(current.get("contact_person","") or ""))
        c3,c4 = st.columns(2)
        phone = c3.text_input("Teléfono", value=str(current.get("phone","") or ""))
        email = c4.text_input("Correo", value=str(current.get("email","") or ""))
        notes = st.text_area("Notas", value=str(current.get("notes","") or ""), height=80)
        s1,s2,s3 = st.columns(3)
        save = s1.form_submit_button("Guardar", type="primary")
        edit = s2.form_submit_button("Editar")
        dele = s3.form_submit_button("Eliminar")
        if save or edit:
            if not name.strip():
                st.error("Nombre obligatorio.")
            elif edit and selected == "Nuevo":
                st.error("Selecciona un proveedor existente para editar, o usa 'Guardar' para crear uno nuevo.")
            else:
                conn = get_conn()
                if save:
                    q(conn, "INSERT OR IGNORE INTO suppliers (name,phone,email,contact_person,notes) VALUES (?,?,?,?,?)",
                      (name.strip(),phone.strip(),email.strip(),contact.strip(),notes.strip()))
                    st.success("Proveedor creado.")
                else:
                    q(conn, "UPDATE suppliers SET name=?,phone=?,email=?,contact_person=?,notes=? WHERE id=?",
                      (name.strip(),phone.strip(),email.strip(),contact.strip(),notes.strip(),int(current["id"])))
                    st.success("Proveedor actualizado.")
                conn.close()
                st.rerun()
        if dele and selected!="Nuevo":
            conn = get_conn()
            q(conn, "DELETE FROM suppliers WHERE id=?", (int(current["id"]),))
            conn.close()
            st.success("Proveedor eliminado.")
            st.rerun()
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("Sin proveedores.")
