import streamlit as st
from database import (get_setting, set_setting, hash_password, verify_admin_credentials,
                      admin_logged_in, list_backups, APP_DIR, DB_PATH,
                      delete_project_and_reset_stock, reset_transactional_data, get_df)

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
    t1, t2, t3 = st.tabs(["Credenciales","Mantenimiento","Reset de pruebas"])
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
    with t3:
        st.markdown("### Reset total de datos de prueba")
        st.caption(
            "Borra **todos** los registros transaccionales: clientes, cotizaciones, proyectos, "
            "OT, ventas, facturación, movimientos de inventario y proveedores. "
            "Preserva inventario, kits, vendedores, plantillas de checklist y configuración. "
            "El stock de cada ítem vuelve a su valor de stock inicial."
        )
        st.warning("⚠️ Esta acción es irreversible. Asegúrate de tener un respaldo antes de continuar.")
        confirm1 = st.checkbox("Entiendo que se borrarán todos los datos transaccionales.", key="reset_confirm1")
        confirm2 = st.checkbox("He hecho un respaldo de la base de datos.", key="reset_confirm2")
        if st.button("🗑️ Ejecutar reset de pruebas", type="primary",
                     disabled=not (confirm1 and confirm2), key="btn_full_reset"):
            ok, msg, detalle = reset_transactional_data()
            if ok:
                st.success(f"✅ {msg}")
                import pandas as pd
                rows = [{"Tabla": k, "Resultado": f"{v} filas eliminadas" if isinstance(v, int) else str(v)} for k,v in detalle.items()]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.rerun()
            else:
                st.error(msg)
        st.markdown("---")
        st.markdown("### Eliminar un proyecto específico")
        st.caption("Elimina un proyecto puntual junto con su OT y cotización vinculadas, restaurando el stock.")
        projects_df = get_df("""
            SELECT p.id, p.project_number, p.status, c.name AS cliente, qt.quote_number
            FROM projects p
            LEFT JOIN clients c ON c.id=p.client_id
            LEFT JOIN quotes qt ON qt.id=p.quotation_id
            ORDER BY p.id DESC
        """)
        if projects_df.empty:
            st.info("No hay proyectos en la base de datos.")
        else:
            proj_opts = [f'{int(r["id"])} · {r["project_number"]} · {r["cliente"]} · {r["status"]}' for _, r in projects_df.iterrows()]
            sel_proj = st.selectbox("Proyecto a eliminar", proj_opts, key="admin_del_proj")
            proj_id = int(sel_proj.split(" · ")[0]) if sel_proj else None
            if proj_id:
                row = projects_df[projects_df["id"] == proj_id].iloc[0]
                st.info(f"**Proyecto:** {row['project_number']}  ·  **Cotización:** {row.get('quote_number','—')}  ·  **Estado:** {row['status']}")
            confirm_one = st.checkbox("Confirmo que quiero eliminar este proyecto y sus registros vinculados.", key="admin_del_proj_confirm")
            if st.button("🗑️ Eliminar proyecto", type="primary", disabled=not confirm_one, key="admin_del_proj_btn"):
                if proj_id:
                    ok, msg, detalle = delete_project_and_reset_stock(proj_id)
                    if ok:
                        lines = [f"✅ {msg}"]
                        if detalle.get("cotizacion"): lines.append(f"• Cotización: **{detalle['cotizacion']}**")
                        if detalle.get("ot"):         lines.append(f"• OT: **{detalle['ot']}**")
                        if detalle.get("stock_liberado"): lines.append("• Stock restaurado: " + ", ".join(detalle["stock_liberado"]))
                        st.success("\n".join(lines))
                        st.rerun()
                    else:
                        st.error(msg)
