from datetime import date, datetime
import streamlit as st
from database import (get_df, get_conn, q, project_exists_for_quote,
                      create_project_from_quote, validate_project_completion,
                      sync_project_item_usage, close_project_workflow)
from utils import money, make_project_delivery_pdf


def render():
    st.subheader("Proyectos")
    st.caption("Proyecto, reserva de stock, checklist y acta de entrega.")

    quotes_df = get_df("""
        SELECT q.id, q.quote_number, q.quote_date, q.status, q.total, c.name AS cliente
        FROM quotes q LEFT JOIN clients c ON c.id=q.client_id ORDER BY q.id DESC
    """)
    projects_df = get_df("""
        SELECT p.id, p.project_number, p.name, p.status, p.technical_status,
               p.installation_date, p.configuration_url, c.name AS cliente, qt.quote_number,
               COALESCE(SUM(pi.reserved_quantity),0) AS reservado,
               COALESCE(SUM(pi.used_quantity),0) AS consumido
        FROM projects p
        LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN quotes qt ON qt.id=p.quotation_id
        LEFT JOIN project_items pi ON pi.project_id=p.id
        WHERE COALESCE(p.is_active,1)=1
        GROUP BY p.id,p.project_number,p.name,p.status,p.technical_status,
                 p.installation_date,p.configuration_url,c.name,qt.quote_number
        ORDER BY p.id DESC
    """)

    with st.expander("Crear proyecto desde cotización", expanded=False):
        if quotes_df.empty:
            st.info("No hay cotizaciones disponibles.")
        else:
            available = [row for _, row in quotes_df.iterrows() if not project_exists_for_quote(int(row["id"]))]
            if not available:
                st.info("Todas las cotizaciones ya tienen proyecto asociado.")
            else:
                opts = [f'{int(r["id"])} · {r["quote_number"]} · {r["cliente"]} · {r["status"]}' for r in available]
                a2, b2 = st.columns(2)
                sel_q = a2.selectbox("Cotización", opts)
                inst_date = b2.date_input("Fecha instalación", value=date.today())
                config_url = st.text_input("URL configuración / respaldo")
                proj_notes = st.text_area("Notas del proyecto", height=80)
                if st.button("🛠️ Crear proyecto desde cotización"):
                    qid = int(sel_q.split(" · ")[0])
                    ok, pid, msg = create_project_from_quote(qid, installation_date=inst_date.isoformat(), configuration_url=config_url, notes=proj_notes)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

    st.markdown("### Listado de proyectos")
    if projects_df.empty:
        st.info("No hay proyectos registrados.")
        return

    st.dataframe(projects_df, use_container_width=True, hide_index=True, column_config={
        "id": st.column_config.NumberColumn("ID", format="%d"),
        "project_number": st.column_config.TextColumn("N° Proyecto"),
        "name": st.column_config.TextColumn("Nombre"),
        "status": st.column_config.TextColumn("Estado"),
        "technical_status": st.column_config.TextColumn("Estado técnico"),
        "installation_date": st.column_config.DateColumn("Fecha inst."),
        "cliente": st.column_config.TextColumn("Cliente"),
        "quote_number": st.column_config.TextColumn("Cotización"),
        "reservado": st.column_config.NumberColumn("Reservado", format="%d"),
        "consumido": st.column_config.NumberColumn("Consumido", format="%d"),
        "configuration_url": st.column_config.LinkColumn("URL Config.", display_text="Abrir"),
    })

    sel_proj = st.selectbox("Selecciona proyecto",
                            [f'{int(r["id"])} · {r["project_number"]} · {r["cliente"]}' for _, r in projects_df.iterrows()],
                            key="proj_sel")
    project_id = int(sel_proj.split(" · ")[0]) if sel_proj else None
    if not project_id:
        return

    project = get_df("""
        SELECT p.*, c.name AS cliente, c.address, c.phone, qt.quote_number
        FROM projects p LEFT JOIN clients c ON c.id=p.client_id
        LEFT JOIN quotes qt ON qt.id=p.quotation_id WHERE p.id=?
    """, (project_id,)).iloc[0].to_dict()

    items_df = get_df("SELECT * FROM project_items WHERE project_id=? ORDER BY id", (project_id,))
    checklist_df = get_df("""
        SELECT pci.id, pci.item_text, pci.is_required, pci.is_checked, pci.evidence_note
        FROM project_checklists pc
        JOIN project_checklist_items pci ON pci.project_checklist_id=pc.id
        WHERE pc.id=(SELECT id FROM project_checklists WHERE project_id=? ORDER BY id DESC LIMIT 1)
        ORDER BY pci.id
    """, (project_id,))
    move_df = get_df("""
        SELECT created_at, sku, movement_type, quantity, notes FROM inventory_movements
        WHERE reference_type='project' AND reference_id=? ORDER BY id DESC
    """, (project_id,))

    st.markdown(f"### {project['project_number']} · {project['cliente']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Estado", str(project.get("status","")))
    m2.metric("Estado técnico", str(project.get("technical_status","")))
    m3.metric("Reservado", int(projects_df.loc[projects_df["id"]==project_id,"reservado"].iloc[0]))
    m4.metric("Consumido", int(projects_df.loc[projects_df["id"]==project_id,"consumido"].iloc[0]))
    st.caption(f"Cotización: {project.get('quote_number','')} · Instalación: {project.get('installation_date','') or '-'}")

    # Cabecera editable
    with st.expander("Editar cabecera del proyecto", expanded=True):
        with st.form(f"proj_header_{project_id}"):
            c1, c2 = st.columns(2)
            pname = c1.text_input("Nombre del proyecto", value=str(project.get("name","") or ""))
            inst_d = c2.date_input("Fecha instalación",
                value=(datetime.fromisoformat(project["installation_date"]).date() if project.get("installation_date") else date.today()))
            c3, c4 = st.columns(2)
            statuses = ["Pendiente","Aprobado","En ejecución","Cerrado","Cancelado"]
            tech_statuses = ["Pendiente","En Proceso","Pruebas","Finalizado"]
            pstatus = c3.selectbox("Estado proyecto", statuses,
                index=(statuses.index(project.get("status","Pendiente")) if project.get("status","Pendiente") in statuses else 0))
            ptech = c4.selectbox("Estado técnico", tech_statuses,
                index=(tech_statuses.index(project.get("technical_status","Pendiente")) if project.get("technical_status","Pendiente") in tech_statuses else 0))
            config_url = st.text_input("URL configuración", value=str(project.get("configuration_url","") or ""))
            pdesc = st.text_area("Descripción", value=str(project.get("description","") or ""), height=60)
            pnotes = st.text_area("Notas técnicas", value=str(project.get("notes","") or ""), height=80)
            if st.form_submit_button("Guardar cabecera"):
                conn = get_conn()
                q(conn, """UPDATE projects SET name=?,installation_date=?,status=?,technical_status=?,
                    configuration_url=?,description=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                  (pname.strip(), inst_d.isoformat(), pstatus, ptech, config_url.strip(), pdesc.strip(), pnotes.strip(), project_id))
                conn.close()
                st.success("Cabecera guardada.")
                st.rerun()

    # Ítems y uso real
    if not items_df.empty:
        with st.expander("Ítems del proyecto y uso real", expanded=False):
            st.dataframe(items_df[["item_type","sku","description","quantity","reserved_quantity","used_quantity","unit_cost"]],
                         use_container_width=True, hide_index=True)
            st.markdown("#### Registrar uso real")
            item_opts = [f'{int(r["id"])} · {r["description"]} (comprado: {int(r["quantity"])}, usado: {int(r["used_quantity"] or 0)})' for _, r in items_df.iterrows()]
            item_sel = st.selectbox("Ítem", item_opts, key=f"proj_item_sel_{project_id}")
            item_id = int(item_sel.split(" · ")[0])
            item_row = items_df[items_df["id"] == item_id].iloc[0]
            new_used = st.number_input("Cantidad usada real", min_value=0, max_value=int(item_row["quantity"] or 0),
                                       value=int(item_row["used_quantity"] or 0), step=1, key=f"proj_item_used_{item_id}")
            if st.button("Actualizar uso", key=f"proj_upd_{item_id}"):
                ok, msg = sync_project_item_usage(item_id, new_used)
                (st.success if ok else st.error)(msg)
                st.rerun()

    # Checklist
    if not checklist_df.empty:
        with st.expander("Checklist de entrega", expanded=False):
            for _, cl_item in checklist_df.iterrows():
                checked = bool(cl_item.get("is_checked", 0))
                new_checked = st.checkbox(
                    f"{'⭕ REQUERIDO' if cl_item.get('is_required',0) else '○ Opcional'} · {cl_item['item_text']}",
                    value=checked, key=f"cl_{cl_item['id']}"
                )
                if new_checked != checked:
                    conn = get_conn()
                    from datetime import datetime as dt
                    q(conn, "UPDATE project_checklist_items SET is_checked=?, checked_at=? WHERE id=?",
                      (1 if new_checked else 0, dt.now().isoformat() if new_checked else None, int(cl_item["id"])))
                    conn.close()
                    st.rerun()

    # Movimientos de inventario
    if not move_df.empty:
        with st.expander("Movimientos de inventario", expanded=False):
            st.dataframe(move_df, use_container_width=True, hide_index=True)

    # Acta y cierre
    st.markdown("### Cierre técnico")
    valid, valid_msg = validate_project_completion(project_id)
    if valid:
        st.success(valid_msg)
    else:
        st.warning(valid_msg)

    pdf_bytes = make_project_delivery_pdf(project_id)
    act1, act2 = st.columns(2)
    if pdf_bytes:
        act1.download_button("📄 Descargar acta de entrega", data=pdf_bytes,
                             file_name=f"acta_entrega_{project_id}.pdf", mime="application/pdf",
                             use_container_width=True)
    if act2.button("✅ Cerrar proyecto y OT", type="primary", use_container_width=True):
        ok, close_msg = close_project_workflow(project_id)
        (st.success if ok else st.warning)(close_msg)
        if ok:
            st.rerun()
