from datetime import date
import streamlit as st
from database import (get_df, get_conn, q, project_exists_for_quote,
                      create_project_from_quote, create_work_order_from_project,
                      get_workflow_ot, close_project_workflow, validate_project_completion)
from utils import make_project_delivery_pdf

STEPS = [("cliente","Cliente"),("cotizacion","Cotización"),("proyecto","Proyecto"),("ot","OT"),("cierre","Acta / Cierre")]

def _init_workflow():
    defaults = {"workflow_active":False,"workflow_step":"cliente","workflow_client_id":None,
                "workflow_quote_id":None,"workflow_project_id":None,"workflow_ot_id":None}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _go(step):
    st.session_state["workflow_active"] = True
    st.session_state["workflow_step"] = step

def _reset():
    for k, v in {"workflow_active":False,"workflow_step":"cliente","workflow_client_id":None,
                  "workflow_quote_id":None,"workflow_project_id":None,"workflow_ot_id":None}.items():
        st.session_state[k] = v


def render():
    _init_workflow()
    step = st.session_state.get("workflow_step","cliente")

    # Barra de progreso
    step_keys = [s[0] for s in STEPS]
    step_labels = [s[1] for s in STEPS]
    current_idx = step_keys.index(step) if step in step_keys else 0
    progress_html = "<div style='display:flex;gap:.5rem;margin-bottom:1rem;'>"
    for i, lbl in enumerate(step_labels):
        if i < current_idx:
            style = "background:#22c55e;color:white;"
        elif i == current_idx:
            style = "background:#3b82f6;color:white;font-weight:700;"
        else:
            style = "background:#1e293b;color:#64748b;"
        progress_html += f"<div style='flex:1;padding:.4rem .5rem;border-radius:10px;text-align:center;font-size:.8rem;{style}'>{lbl}</div>"
    progress_html += "</div>"
    st.markdown(progress_html, unsafe_allow_html=True)

    c1, c2 = st.columns([3,1])
    with c2:
        st.write(f"Cliente: {st.session_state.get('workflow_client_id') or '-'}")
        st.write(f"Cotización: {st.session_state.get('workflow_quote_id') or '-'}")
        st.write(f"Proyecto: {st.session_state.get('workflow_project_id') or '-'}")
        st.write(f"OT: {st.session_state.get('workflow_ot_id') or '-'}")
        if st.button("Reiniciar flujo", use_container_width=True):
            _reset()
            st.rerun()

    with c1:
        if step == "cliente":
            st.markdown("### 1) Seleccionar cliente")
            clients_df = get_df("SELECT id, name, phone, email FROM clients ORDER BY name")
            if clients_df.empty:
                st.warning("No hay clientes. Crea uno en el módulo **Clientes**.")
                if st.button("Ir a Clientes"):
                    st.session_state["current_tab"] = "Clientes"; st.rerun()
            else:
                opts = [f'{int(r["id"])} · {r["name"]}' for _, r in clients_df.iterrows()]
                sel = st.selectbox("Cliente", opts)
                cli_id = int(sel.split(" · ")[0])
                row = clients_df[clients_df["id"]==cli_id].iloc[0]
                st.info(f"{row['name']} · {row.get('phone','') or '-'} · {row.get('email','') or '-'}")
                if st.button("Continuar a Cotización →", type="primary"):
                    st.session_state["workflow_client_id"] = cli_id
                    _go("cotizacion"); st.rerun()

        elif step == "cotizacion":
            st.markdown("### 2) Cotización")
            client_id = st.session_state.get("workflow_client_id")
            if not client_id:
                _go("cliente"); st.rerun()
            quotes_df = get_df("SELECT id,quote_number,quote_date,status,total FROM quotes WHERE client_id=? ORDER BY id DESC", (client_id,))
            left, right = st.columns([1.2,1])
            with left:
                st.write("Crea o selecciona una cotización para este cliente.")
                if st.button("Ir a módulo Cotización", type="primary"):
                    st.session_state["current_tab"] = "Cotización"; st.rerun()
            with right:
                if quotes_df.empty:
                    st.warning("No hay cotizaciones para este cliente.")
                else:
                    q_opts = [f'{int(r["id"])} · {r["quote_number"]} · {r["status"]}' for _, r in quotes_df.iterrows()]
                    sel_q = st.selectbox("Cotización", q_opts)
                    quote_id = int(sel_q.split(" · ")[0])
                    st.session_state["workflow_quote_id"] = quote_id
                    b1, b2 = st.columns(2)
                    if b1.button("Continuar a Proyecto →", type="primary"):
                        _go("proyecto"); st.rerun()
                    if b2.button("← Volver"):
                        _go("cliente"); st.rerun()

        elif step == "proyecto":
            st.markdown("### 3) Proyecto")
            quote_id = st.session_state.get("workflow_quote_id")
            if not quote_id:
                _go("cotizacion"); st.rerun()
            existing_pid = project_exists_for_quote(quote_id)
            if existing_pid:
                st.session_state["workflow_project_id"] = existing_pid
                st.success(f"Proyecto existente: #{existing_pid}")
            else:
                st.info("No existe proyecto para esta cotización.")
                p1, p2, p3 = st.columns(3)
                inst_date = p1.date_input("Fecha instalación", value=date.today())
                cfg_url = p2.text_input("URL configuración")
                notes = p3.text_input("Notas")
                if st.button("Crear proyecto", type="primary"):
                    ok, pid, msg = create_project_from_quote(quote_id, installation_date=inst_date.isoformat(), configuration_url=cfg_url, notes=notes)
                    if ok:
                        st.session_state["workflow_project_id"] = pid
                        st.success(msg); st.rerun()
                    else:
                        st.warning(msg)
            pid = st.session_state.get("workflow_project_id")
            if pid:
                proj_df = get_df("SELECT project_number,name,status,technical_status FROM projects WHERE id=?", (pid,))
                if not proj_df.empty:
                    st.dataframe(proj_df, use_container_width=True, hide_index=True)
                p1, p2, p3 = st.columns(3)
                if p1.button("Ir a Proyectos"):
                    st.session_state["current_tab"] = "Proyectos"; st.rerun()
                if p2.button("Continuar a OT →", type="primary"):
                    _go("ot"); st.rerun()
                if p3.button("← Volver"):
                    _go("cotizacion"); st.rerun()

        elif step == "ot":
            st.markdown("### 4) Orden de Trabajo")
            pid = st.session_state.get("workflow_project_id")
            if not pid:
                _go("proyecto"); st.rerun()
            existing_ot = get_workflow_ot(pid)
            if existing_ot:
                st.session_state["workflow_ot_id"] = int(existing_ot["id"])
                st.success(f"OT disponible: {existing_ot['ot_number']}")
            else:
                st.info("No existe OT para este proyecto.")
                ot_date = st.date_input("Fecha OT", value=date.today())
                if st.button("Crear OT", type="primary"):
                    ok, ot_id, msg = create_work_order_from_project(pid, ot_date.isoformat())
                    if ok:
                        st.session_state["workflow_ot_id"] = ot_id
                        st.success(msg); st.rerun()
                    else:
                        st.warning(msg)
            o1, o2, o3 = st.columns(3)
            if o1.button("Ir a OT"):
                st.session_state["current_tab"] = "OT"; st.rerun()
            if o2.button("Continuar a Cierre →", type="primary"):
                _go("cierre"); st.rerun()
            if o3.button("← Volver"):
                _go("proyecto"); st.rerun()

        elif step == "cierre":
            st.markdown("### 5) Acta / Cierre")
            pid = st.session_state.get("workflow_project_id")
            if not pid:
                _go("proyecto"); st.rerun()
            valid, msg = validate_project_completion(pid)
            (st.success if valid else st.warning)(msg)
            pdf_bytes = make_project_delivery_pdf(pid)
            if pdf_bytes:
                st.download_button("📄 Descargar acta", data=pdf_bytes, file_name=f"acta_entrega_{pid}.pdf", mime="application/pdf")
            z1, z2, z3 = st.columns(3)
            if z1.button("Ir a Proyectos"):
                st.session_state["current_tab"] = "Proyectos"; st.rerun()
            if z2.button("✅ Cerrar proyecto y OT", type="primary"):
                ok, close_msg = close_project_workflow(pid)
                (st.success if ok else st.warning)(close_msg)
                if ok:
                    _reset(); st.rerun()
            if z3.button("← Volver"):
                _go("ot"); st.rerun()
