import streamlit as st
from database import backup_database, list_backups, restore_backup, restore_from_uploaded_db, export_all_data_json, APP_DIR

def render():
    st.subheader("Respaldo y Restauración")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Crear respaldo")
        bk_name = st.text_input("Nombre opcional", value="abaroa_smart")
        if st.button("💾 Crear respaldo ahora"):
            bk = backup_database(bk_name.strip().replace(" ","_"))
            st.success(f"Respaldo: {bk.name}") if bk else st.error("No se encontró la base de datos.")
        backups = list_backups()
        if backups:
            st.markdown("### Descargar último respaldo")
            st.download_button("⬇️ Descargar .db", data=backups[0].read_bytes(), file_name=backups[0].name, mime="application/octet-stream")
        else:
            st.info("Aún no hay respaldos.")
    with c2:
        st.markdown("### Restaurar respaldo")
        backups = list_backups()
        sel = st.selectbox("Selecciona respaldo", [""] + [p.name for p in backups])
        if st.button("♻️ Restaurar seleccionado"):
            if not sel:
                st.error("Selecciona un respaldo.")
            else:
                ok, msg = restore_backup(sel)
                (st.success if ok else st.error)(msg)
        st.markdown("### Restaurar desde archivo .db")
        up_db = st.file_uploader("Cargar respaldo SQLite", type=["db"])
        if st.button("♻️ Restaurar desde archivo"):
            if up_db is None:
                st.error("Debes cargar un archivo .db")
            else:
                ok, msg = restore_from_uploaded_db(up_db.getvalue())
                (st.success if ok else st.error)(msg)
    st.markdown("---")
    e1, e2 = st.columns(2)
    with e1:
        if st.button("📤 Exportar datos a JSON"):
            out = export_all_data_json()
            st.success(f"Exportación: {out.name}")
        exports = sorted(APP_DIR.glob("export_abaroa_smart_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if exports:
            st.download_button("⬇️ Descargar último JSON", data=exports[0].read_bytes(), file_name=exports[0].name, mime="application/json")
    with e2:
        st.info("Consejo: crea un respaldo antes de instalar una nueva versión del ERP.")
