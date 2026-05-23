import streamlit as st
from database import get_df, get_conn, q
from utils import money

def render():
    st.subheader("Clientes")
    clients_df = get_df("SELECT * FROM clients ORDER BY name")
    c1, c2 = st.columns([1,2])
    opts = ["Nuevo"] + (clients_df["name"].tolist() if not clients_df.empty else [])
    selected = c1.selectbox("Seleccionar cliente", opts, key="client_sel")
    current = clients_df[clients_df["name"]==selected].iloc[0].to_dict() if selected!="Nuevo" and not clients_df.empty and selected in clients_df["name"].values else {}

    with st.form("client_form"):
        f1, f2 = st.columns(2)
        name = f1.text_input("Nombre *", value=str(current.get("name","")))
        rut = f2.text_input("RUT", value=str(current.get("rut","") or ""))
        f3, f4 = st.columns(2)
        phone = f3.text_input("Teléfono", value=str(current.get("phone","") or ""))
        email = f4.text_input("Correo", value=str(current.get("email","") or ""))
        address = st.text_input("Dirección", value=str(current.get("address","") or ""))
        notes = st.text_area("Notas", value=str(current.get("notes","") or ""), height=80)
        s1, s2, s3 = st.columns(3)
        save_btn = s1.form_submit_button("Guardar", type="primary")
        edit_btn = s2.form_submit_button("Editar")
        del_btn = s3.form_submit_button("Eliminar")
        if save_btn or edit_btn:
            if not name.strip():
                st.error("El nombre es obligatorio.")
            else:
                conn = get_conn()
                if save_btn:
                    q(conn, "INSERT INTO clients (name, phone, email, address, rut, notes) VALUES (?,?,?,?,?,?)",
                      (name.strip(), phone.strip(), email.strip(), address.strip(), rut.strip(), notes.strip()))
                    st.success("Cliente creado.")
                else:
                    q(conn, "UPDATE clients SET name=?, phone=?, email=?, address=?, rut=?, notes=? WHERE id=?",
                      (name.strip(), phone.strip(), email.strip(), address.strip(), rut.strip(), notes.strip(), int(current["id"])))
                    st.success("Cliente actualizado.")
                conn.close()
                st.rerun()
        if del_btn and selected != "Nuevo":
            conn = get_conn()
            q(conn, "DELETE FROM clients WHERE id=?", (int(current["id"]),))
            conn.close()
            st.success("Cliente eliminado.")
            st.rerun()

    if not clients_df.empty and selected != "Nuevo" and current:
        st.markdown("### Historial del cliente")
        quotes = get_df("SELECT quote_number, quote_date, status, total FROM quotes WHERE client_id=? ORDER BY id DESC", (int(current["id"]),))
        if not quotes.empty:
            quotes["total"] = quotes["total"].apply(money)
            st.dataframe(quotes, use_container_width=True, hide_index=True)

    st.markdown("### Lista de clientes")
    if clients_df.empty:
        st.info("No hay clientes registrados.")
    else:
        st.dataframe(clients_df[["id","name","rut","phone","email","address","notes"]], use_container_width=True, hide_index=True)
