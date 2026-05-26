import streamlit as st
from database import (get_setting, set_setting, hash_password, verify_admin_credentials,
                      admin_logged_in, list_backups, APP_DIR, DB_PATH)

def render():
    st.subheader("Administración")
    if not admin_logged_in():
        st.warning("Debes iniciar sesión para acceder.")
        a1, _ = st.columns([1,1])
        with a1:
            user = st.text_input("Usuario", key="admin_login_user")
            pw = st.text_input("Contraseña", type="password", key="admin_login_pass")
            if st.button("Ingresar al panel"):
                if verify_admin_credentials(user, pw):
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")
            st.caption("Default: admin / admin123")
        return

    st.success(f"Sesión activa: **{get_setting('admin_username','admin')}**")
    t1, t2 = st.tabs(["Credenciales","Mantenimiento"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            new_user = st.text_input("Usuario", value=get_setting("admin_username","admin"))
            current_pass = st.text_input("Contraseña actual", type="password", key="adm_cur_pass")
            new_pass = st.text_input("Nueva contraseña", type="password", key="adm_new_pass")
            confirm_pass = st.text_input("Confirmar contraseña", type="password", key="adm_conf_pass")
            if st.button("Guardar credenciales"):
                if not verify_admin_credentials(get_setting("admin_username","admin"), current_pass):
                    st.error("La contraseña actual no es válida.")
                elif not new_user.strip():
                    st.error("El usuario no puede quedar vacío.")
                elif new_pass and new_pass != confirm_pass:
                    st.error("Las contraseñas no coinciden.")
                else:
                    set_setting("admin_username", new_user.strip())
                    if new_pass:
                        set_setting("admin_password_hash", hash_password(new_pass))
                    st.success("Credenciales actualizadas.")
        with c2:
            st.markdown("### Restablecer acceso")
            if st.button("Restablecer a admin / admin123"):
                set_setting("admin_username","admin")
                set_setting("admin_password_hash", hash_password("admin123"))
                st.success("Credenciales restablecidas.")
    with t2:
        m1, m2 = st.columns(2)
        with m1:
            if st.button("Ir a Respaldos", use_container_width=True):
                st.session_state["current_tab"] = "Respaldo y Restauración"
                st.rerun()
            if st.button("Cerrar sesión", use_container_width=True):
                st.session_state["admin_logged_in"] = False
                st.rerun()
        with m2:
            st.markdown("### Estado")
            st.write(f"Base de datos: `{DB_PATH.name}`")
            st.write(f"Respaldos detectados: {len(list_backups())}")
            exports = list(APP_DIR.glob("export_abaroa_smart_*.json"))
            st.write(f"Exportaciones JSON: {len(exports)}")
